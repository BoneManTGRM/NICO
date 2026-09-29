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
from nico import comprehensive_run_storage_dedup_v1 as dedup


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def noisy(size=128 * 1024):
    return base64.b64encode(random.Random(197).randbytes(size)).decode()


def record():
    evidence = {"source": noisy(), "failure": "target_test_failed", "coverage": [1, 2, 3]}
    return {"stage_results": [deepcopy(evidence) for _ in range(6)],
            "report": {"json": evidence}, "human_review_required": True,
            "client_delivery_allowed": False, "status": "blocked"}


def lower_cap(monkeypatch):
    monkeypatch.setattr(codec, "MAX_COMPRESSED_BYTES", 256 * 1024)
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1024)


def envelope(frame, raw):
    return {codec.ENVELOPE_KEY: {
        "schema": codec._TOKEN_SCHEMA, "encoding": codec._TOKEN_ENCODING,
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "data": base64.b64encode(zlib.compress(frame)).decode(),
    }}


def test_real_legacy_overflow_round_trips_exact_json_and_evidence(monkeypatch):
    lower_cap(monkeypatch)
    original = record()
    before = deepcopy(original)
    with pytest.raises(ValueError, match="run_storage_compressed_size_limit"):
        codec._encode_legacy_run_storage(original)
    packed = json.loads(codec.encode_run_storage(original))
    body = packed[codec.ENVELOPE_KEY]
    assert body["schema"] == codec._TOKEN_SCHEMA
    assert len(base64.b64decode(body["data"])) < codec.MAX_COMPRESSED_BYTES
    assert body["sha256"] == hashlib.sha256(canonical(original)).hexdigest()
    assert body["size_bytes"] == len(canonical(original))
    restored = codec.decode_run_storage(packed)
    assert canonical(restored) == canonical(original)
    assert restored == original == before
    assert restored["status"] == "blocked"
    assert restored["client_delivery_allowed"] is False
    assert codec.encode_run_storage(original) == codec.encode_run_storage(original)


def test_legacy_small_and_existing_compressed_records_are_unchanged(monkeypatch):
    small = {"text": "á 東京", "literal": {"R": [0]}, "delivery": False}
    assert codec.encode_run_storage(small).encode() == canonical(small)
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    packed = json.loads(codec.encode_run_storage(small))
    assert packed[codec.ENVELOPE_KEY]["schema"] == codec.STORAGE_SCHEMA
    assert codec.decode_run_storage(packed) == small


@pytest.mark.parametrize("value", [
    {"text": "á東京\\\"\n" * 1000, "n": -0.0, "v": [None, True, False, 42]},
    {"text": "x" * 65537, "duplicate": "x" * 65537},
    {"a": ["\x00\n\t\r" * 2000] * 5, "b": {"__ref__": 0}},
    {"large_key_" + "k" * 4096: ["s" * 4096] * 10},
])
def test_token_encoding_preserves_unicode_escape_lists_keys_and_numbers(value):
    raw = canonical(value)
    size, sha, packed = dedup.encode_tokens(
        json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False).iterencode(value),
        max_uncompressed=codec.MAX_UNCOMPRESSED_BYTES, max_compressed=codec.MAX_COMPRESSED_BYTES,
    )
    assert dedup.decode_tokens(packed, size=size, sha256=sha) == raw


def test_unique_oversize_data_still_fails_closed(monkeypatch):
    lower_cap(monkeypatch)
    with pytest.raises(ValueError, match="run_storage_compressed_size_limit"):
        codec.encode_run_storage({"unique": noisy(512 * 1024)})


def test_expanded_limit_is_not_relaxed_by_references(monkeypatch):
    lower_cap(monkeypatch)
    monkeypatch.setattr(codec, "MAX_UNCOMPRESSED_BYTES", 800 * 1024)
    with pytest.raises(ValueError, match="run_storage_uncompressed_size_limit"):
        codec.encode_run_storage(record())


def test_dictionary_exhaustion_keeps_literal_evidence(monkeypatch):
    monkeypatch.setattr(dedup, "MAX_DICTIONARY_BYTES", 5000)
    monkeypatch.setattr(dedup, "MAX_DICTIONARY_ENTRIES", 1)
    value = {"a": "x" * 4500, "b": noisy(), "c": "x" * 4500, "d": noisy()}
    raw = canonical(value)
    size, sha, packed = dedup.encode_tokens(
        json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False).iterencode(value),
        max_uncompressed=2 * 1024 * 1024, max_compressed=1024 * 1024,
    )
    assert dedup.decode_tokens(packed, size=size, sha256=sha) == raw


@pytest.mark.parametrize("kind", ["truncated", "concatenated", "trailing", "corrupt"])
def test_v2_requires_one_complete_compression_stream(monkeypatch, kind):
    lower_cap(monkeypatch)
    packed = json.loads(codec.encode_run_storage(record()))
    body = packed[codec.ENVELOPE_KEY]
    stream = base64.b64decode(body["data"])
    if kind == "truncated": stream = stream[:-1]
    elif kind == "concatenated": stream += zlib.compress(b"extra")
    elif kind == "trailing": stream += b"extra"
    else: stream = b"not a zlib stream"
    body["data"] = base64.b64encode(stream).decode()
    with pytest.raises(ValueError, match="run_storage_"):
        codec.decode_run_storage(packed)


@pytest.mark.parametrize(("field", "value"), [
    ("size_bytes", True), ("size_bytes", 0), ("size_bytes", -1),
    ("size_bytes", codec.MAX_UNCOMPRESSED_BYTES + 1), ("size_bytes", 10),
    ("sha256", "0" * 64), ("sha256", "invalid"),
    ("schema", "future"), ("encoding", "future"),
    ("data", "not valid base64"), ("data", None),
])
def test_v2_envelope_corruption_is_rejected(monkeypatch, field, value):
    lower_cap(monkeypatch)
    packed = json.loads(codec.encode_run_storage(record()))
    packed[codec.ENVELOPE_KEY][field] = value
    with pytest.raises(ValueError, match="run_storage_"):
        codec.decode_run_storage(packed)


@pytest.mark.parametrize("frame", [
    b"bad magic", dedup.MAGIC + b"Q", dedup.MAGIC + b"L\x00\x00",
    dedup.MAGIC + b"R" + struct.pack(">I", 0),
    dedup.MAGIC + b"L" + struct.pack(">I", 0),
    dedup.MAGIC + b"L" + struct.pack(">I", dedup.CHUNK_BYTES + 1),
    dedup.MAGIC + b"D" + struct.pack(">I", dedup.MAX_DICTIONARY_BYTES + 1),
    dedup.MAGIC + b"D" + struct.pack(">I", 1) + b"x",
])
def test_v2_malformed_frames_cannot_allocate_or_reference_arbitrary_data(frame):
    with pytest.raises(ValueError, match="run_storage_"):
        codec.decode_run_storage(envelope(frame, b"{}"))


def test_reference_expansion_is_bounded_before_output_allocation():
    value = b'"' + b"x" * 4096 + b'"'
    frame = dedup.MAGIC + b"D" + struct.pack(">I", len(value)) + value + b"R" + struct.pack(">I", 0)
    with pytest.raises(ValueError, match="uncompressed_size_mismatch"):
        dedup.decode_tokens(zlib.compress(frame), size=len(value), sha256=hashlib.sha256(value).hexdigest())


def test_dictionary_total_is_bounded_before_reading_definition(monkeypatch):
    monkeypatch.setattr(dedup, "MAX_DICTIONARY_BYTES", 5000)
    frame = dedup.MAGIC + b"D" + struct.pack(">I", 4096) + b"x" * 4096 + b"D" + struct.pack(">I", 4096)
    with pytest.raises(ValueError, match="dictionary_limit"):
        dedup.decode_tokens(zlib.compress(frame), size=8192, sha256="0" * 64)


@pytest.mark.parametrize("raw", [b"null", b"[]", b'"x"', b'{"__nico_comprehensive_run_storage_v1__":{}}'])
def test_v2_still_requires_a_non_envelope_run_object(raw):
    frame = dedup.MAGIC + b"L" + struct.pack(">I", len(raw)) + raw
    with pytest.raises(ValueError, match="decoded_record_invalid"):
        codec.decode_run_storage(envelope(frame, raw))


def test_v2_oversized_outer_payload_is_rejected_before_inflation(monkeypatch):
    monkeypatch.setattr(codec, "MAX_COMPRESSED_BYTES", 2)
    with pytest.raises(ValueError, match="compressed_size_limit"):
        codec.decode_run_storage(envelope(dedup.MAGIC, b"{}"))


def test_canonical_envelope_key_stays_reserved():
    with pytest.raises(ValueError, match="reserved_envelope_key"):
        codec.encode_run_storage({codec.ENVELOPE_KEY: {}})


def test_durable_store_preserves_revision_integrity_and_review_history(tmp_path, monkeypatch):
    # Integration runs in the normal repository CI with the actual store classes.
    import sqlite3
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_run_record import apply_comprehensive_stage_result, create_comprehensive_run_record
    from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunStore

    lower_cap(monkeypatch)
    database = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    original = store.create(create_comprehensive_run_record(
        run_id="comprun_token_storage", repository="owner/repo", commit_sha="a" * 40,
        evidence_ledger_id="ledger_token_storage", customer_id="customer",
        project_id="project", authorized=True,
    ))
    advanced = apply_comprehensive_stage_result(
        original, stage_id=COMPREHENSIVE_STAGES[0], result={"status": "complete", "evidence": record()},
    )
    saved = store.save(advanced, expected_revision=original["revision"])
    with sqlite3.connect(database) as connection:
        packed = json.loads(connection.execute("SELECT payload FROM nico_comprehensive_runs").fetchone()[0])
    assert packed[codec.ENVELOPE_KEY]["schema"] == codec._TOKEN_SCHEMA
    assert store.load(saved["identity"]["run_id"]) == saved
    assert store.list_recent(customer_id="customer", project_id="project") == [saved]
    with pytest.raises(ComprehensiveRunConflict, match="stale_revision"):
        store.save(advanced, expected_revision=original["revision"])
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE nico_comprehensive_review_history_commitments SET event_count = 1")
    with pytest.raises(ValueError, match="review_history_commitment_cannot_be_truncated"):
        store.load(saved["identity"]["run_id"])
