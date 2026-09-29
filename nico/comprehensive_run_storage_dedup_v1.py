"""Bounded, lossless long-range token references for oversized run transport.

This is a storage encoding, never a report projection. JSON encoder pieces are
retained byte-for-byte; only repeated pieces are replaced in the transport. The
expanded canonical bytes must still satisfy the existing length and SHA-256.
No pickle, filesystem references, recursive references, or executable payloads.
"""
from __future__ import annotations

import hashlib
import io
import struct
import zlib
from collections.abc import Iterable, Iterator

MAGIC = b"NICO-JTOK1\x00"
MIN_TOKEN_BYTES = 4096
MAX_DICTIONARY_BYTES = 64 * 1024 * 1024
MAX_DICTIONARY_ENTRIES = 16384
CHUNK_BYTES = 64 * 1024
_U32 = struct.Struct(">I")


def _frame_limit(size: int) -> int:
    # At most one reference/definition per MIN_TOKEN_BYTES of canonical output,
    # one literal flush beside each such piece, plus full literal chunks.
    return size + 10 * (size // MIN_TOKEN_BYTES + 1) + 5 * (size // CHUNK_BYTES + 1) + len(MAGIC)


def encode_tokens(
    tokens: Iterable[str], *, max_uncompressed: int, max_compressed: int,
) -> tuple[int, str, bytes]:
    compressor = zlib.compressobj()
    packed = bytearray()
    pending = bytearray()
    dictionary: dict[bytes, int] = {}
    dictionary_bytes = 0
    size = 0
    framed_size = 0
    digest = hashlib.sha256()

    def retain(data: bytes) -> None:
        if len(packed) + len(data) > max_compressed:
            raise ValueError("run_storage_compressed_size_limit")
        packed.extend(data)

    def write(data: bytes) -> None:
        nonlocal framed_size
        framed_size += len(data)
        if framed_size > _frame_limit(max_uncompressed):
            raise ValueError("run_storage_token_frame_size_limit")
        # Large JSON pieces must not turn into unbounded compressor input chunks.
        for start in range(0, len(data), CHUNK_BYTES):
            retain(compressor.compress(data[start:start + CHUNK_BYTES]))

    def flush_literal() -> None:
        if pending:
            write(b"L" + _U32.pack(len(pending)))
            write(bytes(pending))
            pending.clear()

    write(MAGIC)
    for text in tokens:
        value = text.encode("utf-8")
        size += len(value)
        if size > max_uncompressed:
            raise ValueError("run_storage_uncompressed_size_limit")
        digest.update(value)
        if len(value) >= MIN_TOKEN_BYTES:
            index = dictionary.get(value)
            if index is not None:
                flush_literal()
                write(b"R" + _U32.pack(index))
                continue
            if (len(dictionary) < MAX_DICTIONARY_ENTRIES
                    and dictionary_bytes + len(value) <= MAX_DICTIONARY_BYTES):
                flush_literal()
                dictionary[value] = len(dictionary)
                dictionary_bytes += len(value)
                write(b"D" + _U32.pack(len(value)))
                write(value)
                continue
        # Dictionary exhaustion never drops evidence: it becomes bounded literals.
        for start in range(0, len(value), CHUNK_BYTES):
            part = value[start:start + CHUNK_BYTES]
            if len(pending) + len(part) > CHUNK_BYTES:
                flush_literal()
            pending.extend(part)
    flush_literal()
    retain(compressor.flush())
    if framed_size > _frame_limit(size):
        raise ValueError("run_storage_token_frame_size_limit")
    return size, digest.hexdigest(), bytes(packed)


def _inflate(packed: bytes, limit: int) -> Iterator[bytes]:
    decoder = zlib.decompressobj()
    total = 0
    try:
        for start in range(0, len(packed), CHUNK_BYTES):
            chunk = packed[start:start + CHUNK_BYTES]
            while chunk:
                value = decoder.decompress(chunk, min(CHUNK_BYTES, limit - total + 1))
                total += len(value)
                if total > limit:
                    raise ValueError("run_storage_token_frame_size_limit")
                if decoder.unused_data:
                    raise ValueError("run_storage_trailing_compressed_data")
                if value:
                    yield value
                chunk = decoder.unconsumed_tail
    except zlib.error as exc:
        raise ValueError("run_storage_zlib_invalid") from exc
    if not decoder.eof:
        raise ValueError("run_storage_zlib_incomplete")


def decode_tokens(packed: bytes, *, size: int, sha256: str) -> bytes:
    chunks = iter(_inflate(packed, _frame_limit(size)))
    pending = bytearray()
    dictionary: list[bytes] = []
    dictionary_bytes = 0
    output = io.BytesIO()
    digest = hashlib.sha256()
    expanded = 0

    def read(count: int, *, eof_allowed: bool = False) -> bytes | None:
        while len(pending) < count:
            try:
                pending.extend(next(chunks))
            except StopIteration:
                if eof_allowed and not pending:
                    return None
                raise ValueError("run_storage_token_frame_incomplete") from None
        value = bytes(pending[:count])
        del pending[:count]
        return value

    def emit(value: bytes) -> None:
        nonlocal expanded
        if expanded + len(value) > size:
            raise ValueError("run_storage_uncompressed_size_mismatch")
        expanded += len(value)
        digest.update(value)
        output.write(value)

    if read(len(MAGIC)) != MAGIC:
        raise ValueError("run_storage_token_magic_invalid")
    while True:
        tag = read(1, eof_allowed=True)
        if tag is None:
            break
        if tag not in (b"L", b"D", b"R"):
            raise ValueError("run_storage_token_tag_invalid")
        number = _U32.unpack(read(4))[0]
        if tag == b"R":
            if number >= len(dictionary):
                raise ValueError("run_storage_token_reference_invalid")
            emit(dictionary[number])
            continue
        if tag == b"L":
            if not 0 < number <= CHUNK_BYTES:
                raise ValueError("run_storage_token_literal_size_invalid")
        else:
            if (number < MIN_TOKEN_BYTES
                    or dictionary_bytes + number > MAX_DICTIONARY_BYTES
                    or len(dictionary) >= MAX_DICTIONARY_ENTRIES):
                raise ValueError("run_storage_token_dictionary_limit")
        # Reject expansion before allocating the declared literal/definition.
        if expanded + number > size:
            raise ValueError("run_storage_uncompressed_size_mismatch")
        value = read(number)
        if tag == b"D":
            dictionary.append(value)
            dictionary_bytes += number
        emit(value)
    if expanded != size:
        raise ValueError("run_storage_uncompressed_size_mismatch")
    if digest.hexdigest() != sha256:
        raise ValueError("run_storage_sha256_mismatch")
    return output.getvalue()
