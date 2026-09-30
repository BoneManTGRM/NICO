"""Lossless storage transport for large Comprehensive run records.

PostgreSQL limits the cumulative elements of one JSONB object to 256 MiB.
Complete source evidence and the report's public aliases can legitimately exceed
that limit. This codec changes only the database representation: readers recover
the exact canonical JSON before existing integrity and review-history validation.
Small records retain their legacy representation. No evidence is projected away.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import zlib
from typing import Any

ENVELOPE_KEY = "__nico_comprehensive_run_storage_v1__"
STORAGE_SCHEMA = "nico.comprehensive_run_storage.v1"
_TOKEN_SCHEMA = "nico.comprehensive_run_storage.v2"
_TOKEN_ENCODING = "zlib+json-token-refs-v1+base64"
_CHUNK_SCHEMA = "nico.comprehensive_run_storage.v3"
_CHUNK_ENCODING = "zlib+json-chunk-refs-v1+base64"
COMPRESSION_THRESHOLD_BYTES = 8 * 1024 * 1024
# A bounded decoder admits the observed ~295 MiB complete diagnostic record.
# The storage object remains comfortably below PostgreSQL's 256 MiB limit.
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSED_BYTES = 128 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
_ENVELOPE_FIELDS = {"schema", "encoding", "size_bytes", "sha256", "data"}


def encode_run_storage(record: dict[str, Any]) -> str:
    """Keep legacy transport unless lossless long-range references are needed."""
    try:
        return _encode_legacy_run_storage(record)
    except ValueError as exc:
        if str(exc) != "run_storage_compressed_size_limit":
            raise
    # Leave the exception scope to release the old compressor and its traceback.
    # The fallback preserves BOTH existing caps and the exact canonical JSON hash.
    from nico.comprehensive_run_storage_dedup_v1 import encode_tokens

    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded = None
    try:
        encoded = encode_tokens(
            encoder.iterencode(record),
            max_uncompressed=MAX_UNCOMPRESSED_BYTES,
            max_compressed=MAX_COMPRESSED_BYTES,
        )
    except ValueError as exc:
        if str(exc) != "run_storage_compressed_size_limit":
            raise
    schema, encoding = _TOKEN_SCHEMA, _TOKEN_ENCODING
    if encoded is None:
        # Release the token encoder's failed buffers before the bounded retry.
        # Chunk references also cover repeated collections of short JSON values.
        from nico.comprehensive_run_storage_chunks_v1 import encode_chunks

        encoded = encode_chunks(
            encoder.iterencode(record),
            max_uncompressed=MAX_UNCOMPRESSED_BYTES,
            max_compressed=MAX_COMPRESSED_BYTES,
        )
        schema, encoding = _CHUNK_SCHEMA, _CHUNK_ENCODING
    size, sha256, packed = encoded
    return json.dumps({ENVELOPE_KEY: {
        "schema": schema,
        "encoding": encoding,
        "size_bytes": size,
        "sha256": sha256,
        "data": base64.b64encode(packed).decode("ascii"),
    }}, sort_keys=True, separators=(",", ":"))


def _encode_legacy_run_storage(record: dict[str, Any]) -> str:
    """Return canonical JSON or a versioned, length/hash-bound zlib envelope."""
    if ENVELOPE_KEY in record:
        raise ValueError("run_storage_reserved_envelope_key")
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    pending = bytearray()
    compressed = bytearray()
    compressor: Any = None
    digest = hashlib.sha256()
    size = 0

    def retain_compressed(data: bytes) -> None:
        if len(compressed) + len(data) > MAX_COMPRESSED_BYTES:
            raise ValueError("run_storage_compressed_size_limit")
        compressed.extend(data)

    for text in encoder.iterencode(record):
        chunk = text.encode("utf-8")
        size += len(chunk)
        if size > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("run_storage_uncompressed_size_limit")
        digest.update(chunk)
        pending.extend(chunk)
        if compressor is None and size > COMPRESSION_THRESHOLD_BYTES:
            compressor = zlib.compressobj()
        if compressor is not None and len(pending) >= _CHUNK_BYTES:
            retain_compressed(compressor.compress(pending))
            pending.clear()

    if compressor is None:
        return pending.decode("utf-8")
    retain_compressed(compressor.compress(pending))
    retain_compressed(compressor.flush())
    envelope = {
        ENVELOPE_KEY: {
            "schema": STORAGE_SCHEMA,
            "encoding": "zlib+base64",
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "data": base64.b64encode(compressed).decode("ascii"),
        }
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


def decode_run_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """Decode only the reserved envelope; reject corruption and expansion abuse."""
    if ENVELOPE_KEY not in payload:
        return payload
    if set(payload) != {ENVELOPE_KEY}:
        raise ValueError("run_storage_envelope_shape_invalid")
    envelope = payload[ENVELOPE_KEY]
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
        raise ValueError("run_storage_envelope_shape_invalid")
    token_encoding = (envelope["schema"], envelope["encoding"]) == (_TOKEN_SCHEMA, _TOKEN_ENCODING)
    chunk_encoding = (envelope["schema"], envelope["encoding"]) == (_CHUNK_SCHEMA, _CHUNK_ENCODING)
    if not token_encoding and not chunk_encoding and (envelope["schema"] != STORAGE_SCHEMA or envelope["encoding"] != "zlib+base64"):
        raise ValueError("run_storage_envelope_version_invalid")
    size = envelope["size_bytes"]
    if type(size) is not int or not 0 < size <= MAX_UNCOMPRESSED_BYTES:
        raise ValueError("run_storage_uncompressed_size_invalid")
    claimed_digest = envelope["sha256"]
    if not isinstance(claimed_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", claimed_digest):
        raise ValueError("run_storage_sha256_invalid")
    data = envelope["data"]
    maximum_encoded = 4 * ((MAX_COMPRESSED_BYTES + 2) // 3)
    if not isinstance(data, str) or len(data) > maximum_encoded:
        raise ValueError("run_storage_compressed_size_limit")
    try:
        packed = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("run_storage_base64_invalid") from exc
    if len(packed) > MAX_COMPRESSED_BYTES:
        raise ValueError("run_storage_compressed_size_limit")
    if token_encoding or chunk_encoding:
        if chunk_encoding:
            from nico.comprehensive_run_storage_chunks_v1 import decode_chunks as decode_references
        else:
            from nico.comprehensive_run_storage_dedup_v1 import decode_tokens as decode_references

        decoded_payload = json.loads(decode_references(packed, size=size, sha256=claimed_digest))
        if not isinstance(decoded_payload, dict) or ENVELOPE_KEY in decoded_payload:
            raise ValueError("run_storage_decoded_record_invalid")
        return decoded_payload
    decoder = zlib.decompressobj()
    output = io.BytesIO()
    digest = hashlib.sha256()
    decoded_size = 0
    try:
        for start in range(0, len(packed), _CHUNK_BYTES):
            chunk = packed[start : start + _CHUNK_BYTES]
            while chunk:
                decoded = decoder.decompress(chunk, min(_CHUNK_BYTES, size - decoded_size + 1))
                decoded_size += len(decoded)
                if decoded_size > size:
                    raise ValueError("run_storage_uncompressed_size_mismatch")
                digest.update(decoded)
                output.write(decoded)
                if decoder.unused_data:
                    raise ValueError("run_storage_trailing_compressed_data")
                chunk = decoder.unconsumed_tail
    except zlib.error as exc:
        raise ValueError("run_storage_zlib_invalid") from exc
    if not decoder.eof:
        raise ValueError("run_storage_zlib_incomplete")
    if decoded_size != size:
        raise ValueError("run_storage_uncompressed_size_mismatch")
    if digest.hexdigest() != claimed_digest:
        raise ValueError("run_storage_sha256_mismatch")
    decoded_payload = json.loads(output.getvalue())
    if not isinstance(decoded_payload, dict) or ENVELOPE_KEY in decoded_payload:
        raise ValueError("run_storage_decoded_record_invalid")
    return decoded_payload
