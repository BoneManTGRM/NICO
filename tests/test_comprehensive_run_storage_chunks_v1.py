from __future__ import annotations

import base64
import hashlib
import json
import random
import struct
import zlib
from copy import deepcopy

import pytest

from nico import comprehensive_run_storage_codec_v1 as codec
from nico import comprehensive_run_storage_chunks_v1 as chunks
from nico import comprehensive_run_storage_dedup_v1 as tokens


def encoder():
    return json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical(value):
    return encoder().encode(value).encode("utf-8")


def short_values(count=16000):
    rng = random.Random(2011)
    return [base64.b64encode(rng.randbytes(24)).decode() for _ in range(count)]


def repeated_record():
    values = short_values()
    return {"first": values, "second": {"padding": "prefix shifts chunk offsets", "values": values},
            "third": [values], "status": "blocked", "client_delivery_allowed": False}


def lower_cap(monkeypatch):
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1024)
    monkeypatch.setattr(codec, "MAX_COMPRESSED_BYTES", 700 * 1024)


def test_short_values_overflow_both_previous_encoders_then_round_trip(monkeypatch):
    lower_cap(monkeypatch)
    value = repeated_record()
    before = deepcopy(value)
    assert max(map(len, encoder().iterencode(value))) < 4096
    with pytest.raises(ValueError, match="run_storage_compressed_size_limit"):
        codec._encode_legacy_run_storage(value)
    with pytest.raises(ValueError, match="run_storage_compressed_size_limit"):
        tokens.encode_tokens(encoder().iterencode(value), max_uncompressed=codec.MAX_UNCOMPRESSED_BYTES,
                             max_compressed=codec.MAX_COMPRESSED_BYTES)
    stored = json.loads(codec.encode_run_storage(value))
    body = stored[codec.ENVELOPE_KEY]
    assert body["schema"] == codec._CHUNK_SCHEMA
    assert len(base64.b64decode(body["data"])) < codec.MAX_COMPRESSED_BYTES
    assert body["sha256"] == hashlib.sha256(canonical(value)).hexdigest()
    assert body["size_bytes"] == len(canonical(value))
    assert codec.decode_run_storage(stored) == before == value
    assert canonical(codec.decode_run_storage(stored)) == canonical(value)
    assert codec.encode_run_storage(value) == codec.encode_run_storage(value)


@pytest.mark.parametrize("prefix", ["", "x", "東京" * 29, "q" * 5000])
def test_short_numeric_arrays_and_shifted_container_boundaries(prefix):
    rng = random.Random(317)
    values = [rng.randrange(256) for _ in range(150000)]
    value = {"a": values, "b": {"prefix": prefix, "values": values}, "c": values}
    size, digest, packed = chunks.encode_chunks(encoder().iterencode(value),
        max_uncompressed=4 * 1024 * 1024, max_compressed=1024 * 1024)
    raw = chunks.decode_chunks(packed, size=size, sha256=digest)
    assert raw == canonical(value)
    assert len(packed) < len(zlib.compress(raw)) * 0.65


@pytest.mark.parametrize("value", [
    {}, {"text": "a東京\x00\n\\\"" * 40000, "same": "a東京\x00\n\\\"" * 40000},
    {"values": [None, True, False, 0.0, -0.0, 1e-30, 123456789]},
    {"key" + "k" * 70000: ["x" * 65537, "y" * 4095, [[], {}]]},
])
def test_arbitrary_canonical_values(value):
    size, digest, packed = chunks.encode_chunks(encoder().iterencode(value),
        max_uncompressed=2 * 1024 * 1024, max_compressed=2 * 1024 * 1024)
    assert chunks.decode_chunks(packed, size=size, sha256=digest) == canonical(value)


def test_existing_small_and_v1_writes_unchanged(monkeypatch):
    value = {"label": "still blocked", "client_delivery_allowed": False}
    assert codec.encode_run_storage(value) == canonical(value).decode()
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    assert codec.encode_run_storage(value) == codec._encode_legacy_run_storage(value)
    assert codec.decode_run_storage(json.loads(codec.encode_run_storage(value))) == value


def test_existing_v2_transport_remains_readable_and_selected(monkeypatch):
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    monkeypatch.setattr(codec, "MAX_COMPRESSED_BYTES", 200000)
    text = "".join(short_values(3000))
    value = {"a": text, "b": text, "c": text, "d": text}
    stored = json.loads(codec.encode_run_storage(value))
    assert stored[codec.ENVELOPE_KEY]["schema"] == codec._TOKEN_SCHEMA
    assert codec.decode_run_storage(stored) == value


def test_exhausted_index_is_lossless_literals(monkeypatch):
    monkeypatch.setattr(chunks, "MAX_INDEX_ENTRIES", 1)
    value = repeated_record()
    size, digest, packed = chunks.encode_chunks(encoder().iterencode(value),
        max_uncompressed=4 * 1024 * 1024, max_compressed=4 * 1024 * 1024)
    assert chunks.decode_chunks(packed, size=size, sha256=digest) == canonical(value)


def test_hash_collision_never_replaces_different_bytes(monkeypatch):
    actual = hashlib.sha256
    class Collision:
        def digest(self): return b"0" * 32
    monkeypatch.setattr(chunks.hashlib, "sha256", lambda *a: Collision() if a else actual())
    value = {"a": short_values(5000)}
    size, digest, packed = chunks.encode_chunks(encoder().iterencode(value),
        max_uncompressed=1024 * 1024, max_compressed=1024 * 1024)
    assert chunks.decode_chunks(packed, size=size, sha256=digest) == canonical(value)


def test_unique_oversize_and_expansion_still_fail_closed(monkeypatch):
    lower_cap(monkeypatch)
    with pytest.raises(ValueError, match="run_storage_compressed_size_limit"):
        codec.encode_run_storage({"unique": short_values(40000)})
    with pytest.raises(ValueError, match="uncompressed_size_limit"):
        chunks.encode_chunks(iter(["a" * 101]), max_uncompressed=100, max_compressed=1000)


def decode_frame(frame, raw=b"x" * 8192, *, size=None, digest=None):
    return chunks.decode_chunks(zlib.compress(frame), size=len(raw) if size is None else size,
                                sha256=hashlib.sha256(raw).hexdigest() if digest is None else digest)


@pytest.mark.parametrize("frame,error", [
    (b"wrong magic", "magic_invalid"),
    (chunks.MAGIC + b"X", "tag_invalid"),
    (chunks.MAGIC + b"L" + struct.pack(">I", 0), "literal_size_invalid"),
    (chunks.MAGIC + b"L" + struct.pack(">I", 65537), "literal_size_invalid"),
    (chunks.MAGIC + b"L" + struct.pack(">I", 4096) + b"x", "frame_incomplete"),
    (chunks.MAGIC + b"R" + struct.pack(">QI", 0, 4096), "reference_invalid"),
    (chunks.MAGIC + b"R" + struct.pack(">QI", (1 << 64) - 1, 4096), "reference_invalid"),
    (chunks.MAGIC + b"R" + struct.pack(">QI", 0, 1), "reference_invalid"),
])
def test_invalid_frames_fail_closed(frame, error):
    with pytest.raises(ValueError, match=error):
        decode_frame(frame)


def test_backward_reference_valid_but_overlap_rejected():
    literal = chunks.MAGIC + b"L" + struct.pack(">I", 4096) + b"x" * 4096
    assert decode_frame(literal + b"R" + struct.pack(">QI", 0, 4096)) == b"x" * 8192
    with pytest.raises(ValueError, match="reference_invalid"):
        decode_frame(literal + b"R" + struct.pack(">QI", 1, 4096))
    with pytest.raises(ValueError, match="uncompressed_size_mismatch"):
        decode_frame(literal + b"R" + struct.pack(">QI", 0, 4096), size=8191)
    with pytest.raises(ValueError, match="sha256_mismatch"):
        decode_frame(literal + b"R" + struct.pack(">QI", 0, 4096), digest="0" * 64)


@pytest.mark.parametrize("kind", ["truncated", "concatenated", "trailing", "corrupt"])
def test_exactly_one_complete_compressed_stream(kind):
    raw = b"{}"
    frame = chunks.MAGIC + b"L" + struct.pack(">I", len(raw)) + raw
    packed = zlib.compress(frame)
    if kind == "truncated": packed = packed[:-1]
    elif kind == "concatenated": packed += zlib.compress(b"extra")
    elif kind == "trailing": packed += b"extra"
    else: packed = b"invalid"
    with pytest.raises(ValueError, match="run_storage_"):
        chunks.decode_chunks(packed, size=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def test_frame_inflation_bound_rejects_many_empty_literals():
    frame = chunks.MAGIC + (b"L" + struct.pack(">I", 1) + b"x") * 2000
    with pytest.raises(ValueError, match="frame_size_limit"):
        decode_frame(frame, raw=b"x" * 2000)


def test_v3_envelope_still_requires_exact_valid_record():
    for raw in (b"[]", b"null", b'{"__nico_comprehensive_run_storage_v1__":{}}'):
        size, digest, packed = chunks.encode_chunks([raw.decode()], max_uncompressed=1000, max_compressed=1000)
        value = {codec.ENVELOPE_KEY: {"schema":codec._CHUNK_SCHEMA,"encoding":codec._CHUNK_ENCODING,
            "size_bytes":size,"sha256":digest,"data":base64.b64encode(packed).decode()}}
        with pytest.raises(ValueError, match="decoded_record_invalid"):
            codec.decode_run_storage(value)


def test_store_chunk_transport_keeps_revision_and_review_history(tmp_path, monkeypatch):
    import sqlite3
    from nico.comprehensive_run_record import create_comprehensive_run_record
    from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunStore
    lower_cap(monkeypatch)
    db = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(db))
    store.ensure_schema()
    record = create_comprehensive_run_record(run_id="comprun_chunk_storage", repository="owner/repo",
        commit_sha="a" * 40, evidence_ledger_id="ledger_chunks", customer_id="customer",
        project_id="project", authorized=True)
    record["storage_fixture"] = repeated_record()
    original = store.create(record)
    assert store.load(original["identity"]["run_id"]) == original
    with sqlite3.connect(db) as connection:
        value = json.loads(connection.execute("SELECT payload FROM nico_comprehensive_runs").fetchone()[0])
        assert value[codec.ENVELOPE_KEY]["schema"] == codec._CHUNK_SCHEMA
    with pytest.raises(ComprehensiveRunConflict, match="stale_revision"):
        store.save(original, expected_revision=original["revision"] - 1)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE nico_comprehensive_review_history_commitments SET event_count = 1")
    with pytest.raises(ValueError, match="review_history_commitment_cannot_be_truncated"):
        store.load(original["identity"]["run_id"])
