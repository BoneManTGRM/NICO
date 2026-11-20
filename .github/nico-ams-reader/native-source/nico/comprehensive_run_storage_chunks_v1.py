"""Bounded long-range references across canonical JSON token boundaries.

Unlike token-only references, content-defined chunks also cover repeated arrays
and objects containing only short values. References address already-emitted
bytes, never paths, executable values, future bytes, or recursive objects.
"""
from __future__ import annotations

import hashlib
import io
import struct
import tempfile
import zlib
from collections.abc import Iterable, Iterator

MAGIC = b"NICO-JCHK1\x00"
MIN_CHUNK_BYTES = 4096
CHUNK_BYTES = 64 * 1024
MAX_INDEX_ENTRIES = 131072
MAX_GEAR_ENTRIES = 1024
_MASK64 = (1 << 64) - 1
_U32 = struct.Struct(">I")
_REF = struct.Struct(">QI")


def _frame_limit(size: int) -> int:
    return size + 13 * (size // MIN_CHUNK_BYTES + 2) + len(MAGIC)


def _chunks(tokens: Iterable[str], maximum: int) -> Iterator[bytes]:
    """Content anchors forget prefix differences after 64 encoder pieces."""
    pending = bytearray()
    gears: dict[bytes, int] = {}
    fingerprint = 0
    total = 0
    for token in tokens:
        value = token.encode("utf-8")
        total += len(value)
        if total > maximum:
            raise ValueError("run_storage_uncompressed_size_limit")
        gear = gears.get(value) if len(value) <= 32 else None
        if gear is None:
            gear = ((zlib.crc32(value) + 1) * 0x9E3779B185EBCA87) & _MASK64
            if len(value) <= 32 and len(gears) < MAX_GEAR_ENTRIES:
                gears[value] = gear
        fingerprint = ((fingerprint << 1) + gear) & _MASK64
        start = 0
        while start < len(value):
            count = min(CHUNK_BYTES - len(pending), len(value) - start)
            pending.extend(value[start:start + count])
            start += count
            if len(pending) == CHUNK_BYTES:
                yield bytes(pending)
                pending.clear()
        if len(pending) >= MIN_CHUNK_BYTES and fingerprint & 1023 == 0:
            yield bytes(pending)
            pending.clear()
    if pending:
        yield bytes(pending)


def encode_chunks(
    tokens: Iterable[str], *, max_uncompressed: int, max_compressed: int,
) -> tuple[int, str, bytes]:
    compressor = zlib.compressobj()
    packed = bytearray()
    digest = hashlib.sha256()
    index: dict[bytes, tuple[int, int, int]] = {}
    size = 0
    framed = 0
    spool_size = 0

    def retain(value: bytes) -> None:
        if len(packed) + len(value) > max_compressed:
            raise ValueError("run_storage_compressed_size_limit")
        packed.extend(value)

    def write(value: bytes) -> None:
        nonlocal framed
        framed += len(value)
        if framed > _frame_limit(max_uncompressed):
            raise ValueError("run_storage_chunk_frame_size_limit")
        retain(compressor.compress(value))

    write(MAGIC)
    # A private, automatically removed temporary file avoids a second full-size
    # in-memory dictionary. Only unique chunks are spooled, bounded by input size.
    with tempfile.TemporaryFile(mode="w+b", prefix="nico-run-chunks-") as spool:
        for chunk in _chunks(tokens, max_uncompressed):
            count = len(chunk)
            digest.update(chunk)
            key = hashlib.sha256(chunk).digest()
            previous = index.get(key)
            matched = False
            if previous is not None and previous[2] == count:
                spool.seek(previous[1])
                matched = spool.read(count) == chunk  # Never trust a hash collision.
            if matched:
                write(b"R" + _REF.pack(previous[0], count))
            else:
                write(b"L" + _U32.pack(count))
                write(chunk)
                if (count >= MIN_CHUNK_BYTES and previous is None
                        and len(index) < MAX_INDEX_ENTRIES):
                    if spool_size + count > max_uncompressed:
                        raise ValueError("run_storage_chunk_spool_size_limit")
                    spool.seek(spool_size)
                    written = spool.write(chunk)
                    if written != count:
                        raise OSError("run_storage_chunk_spool_short_write")
                    index[key] = (size, spool_size, count)
                    spool_size += count
            size += count
    retain(compressor.flush())
    if framed > _frame_limit(size):
        raise ValueError("run_storage_chunk_frame_size_limit")
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
                    raise ValueError("run_storage_chunk_frame_size_limit")
                if decoder.unused_data:
                    raise ValueError("run_storage_trailing_compressed_data")
                if value:
                    yield value
                chunk = decoder.unconsumed_tail
    except zlib.error as exc:
        raise ValueError("run_storage_zlib_invalid") from exc
    if not decoder.eof:
        raise ValueError("run_storage_zlib_incomplete")


def decode_chunks(packed: bytes, *, size: int, sha256: str) -> bytes:
    chunks = iter(_inflate(packed, _frame_limit(size)))
    pending = bytearray()
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
                raise ValueError("run_storage_chunk_frame_incomplete") from None
        value = bytes(pending[:count])
        del pending[:count]
        return value

    if read(len(MAGIC)) != MAGIC:
        raise ValueError("run_storage_chunk_magic_invalid")
    while True:
        tag = read(1, eof_allowed=True)
        if tag is None:
            break
        if tag == b"L":
            count = _U32.unpack(read(4))[0]
            if not 0 < count <= CHUNK_BYTES:
                raise ValueError("run_storage_chunk_literal_size_invalid")
            offset = None
        elif tag == b"R":
            offset, count = _REF.unpack(read(_REF.size))
            if (not MIN_CHUNK_BYTES <= count <= CHUNK_BYTES
                    or offset + count > expanded):
                raise ValueError("run_storage_chunk_reference_invalid")
        else:
            raise ValueError("run_storage_chunk_tag_invalid")
        if expanded + count > size:
            raise ValueError("run_storage_uncompressed_size_mismatch")
        if offset is None:
            value = read(count)
        else:
            output.seek(offset)
            value = output.read(count)
            output.seek(0, io.SEEK_END)
            if len(value) != count:
                raise ValueError("run_storage_chunk_reference_invalid")
        digest.update(value)
        output.write(value)
        expanded += count
    if expanded != size:
        raise ValueError("run_storage_uncompressed_size_mismatch")
    if digest.hexdigest() != sha256:
        raise ValueError("run_storage_sha256_mismatch")
    return output.getvalue()
