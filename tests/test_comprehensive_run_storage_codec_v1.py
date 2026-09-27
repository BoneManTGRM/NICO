from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
import zlib
from pathlib import Path

import pytest

from nico import comprehensive_run_storage_codec_v1 as codec
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
)
from nico.comprehensive_run_store import (
    ComprehensiveRunConflict,
    ComprehensiveRunStore,
    _decode_json_object_payload,
    _decode_run_payload,
)


def _envelope(raw: bytes) -> dict:
    return {
        codec.ENVELOPE_KEY: {
            "schema": codec.STORAGE_SCHEMA,
            "encoding": "zlib+base64",
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "data": base64.b64encode(zlib.compress(raw)).decode("ascii"),
        }
    }


def _record() -> dict:
    return create_comprehensive_run_record(
        run_id="comprun_storage_codec",
        repository="owner/repo",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_storage_codec",
        customer_id="customer",
        project_id="project",
        authorized=True,
    )


def test_small_record_retains_exact_legacy_json_bytes() -> None:
    record = _record()
    record["unicode"] = "evidencia íntegra 東京"
    expected = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert codec.encode_run_storage(record) == expected
    assert codec.decode_run_storage(record) is record


def test_large_repeated_aliases_round_trip_without_field_or_hash_changes(monkeypatch) -> None:
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1024)
    assessment = {"finding": "retained evidence á" * 2000, "findings": [1, 2, 3]}
    canonical = {"assessment": assessment, "stage_summaries": [{"status": "blocked"}]}
    record = _record()
    record["stage_results"]["final_comprehensive_report_generation"] = {
        "status": "blocked",
        "report_package": {"json": canonical},
        "canonical_report": canonical,
        "assessment": assessment,
        "stage_summaries": canonical["stage_summaries"],
    }
    expected = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    packed = json.loads(codec.encode_run_storage(record))
    envelope = packed[codec.ENVELOPE_KEY]
    assert envelope["size_bytes"] == len(expected)
    assert envelope["sha256"] == hashlib.sha256(expected).hexdigest()
    assert len(json.dumps(packed)) < len(expected)
    assert codec.decode_run_storage(packed) == record
    assert _decode_run_payload(json.dumps(packed)) == record
    assert _decode_run_payload(packed) == record


@pytest.mark.parametrize("size", [1, 64 * 1024 - 3, 64 * 1024, 3 * 64 * 1024 + 11])
def test_decoder_handles_chunk_boundaries_and_unicode(size: int) -> None:
    raw = json.dumps({"value": "ñ" * size}, ensure_ascii=False).encode()
    assert codec.decode_run_storage(_envelope(raw)) == {"value": "ñ" * size}


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema", "future", "version_invalid"),
        ("encoding", "other", "version_invalid"),
        ("size_bytes", True, "size_invalid"),
        ("size_bytes", 0, "size_invalid"),
        ("size_bytes", -1, "size_invalid"),
        ("size_bytes", codec.MAX_UNCOMPRESSED_BYTES + 1, "size_invalid"),
        ("size_bytes", "10", "size_invalid"),
        ("sha256", "x" * 64, "sha256_invalid"),
        ("sha256", "0" * 64, "sha256_mismatch"),
        ("data", "not base64", "base64_invalid"),
        ("data", None, "compressed_size_limit"),
    ],
)
def test_malformed_envelope_fails_closed(field, value, error) -> None:
    packed = _envelope(b'{"value":"retained"}')
    packed[codec.ENVELOPE_KEY][field] = value
    with pytest.raises(ValueError, match=error):
        codec.decode_run_storage(packed)


@pytest.mark.parametrize("delta", [-1, 1])
def test_declared_length_must_equal_actual_length(delta) -> None:
    packed = _envelope(b'{"value":"retained"}')
    packed[codec.ENVELOPE_KEY]["size_bytes"] += delta
    with pytest.raises(ValueError, match="size_mismatch"):
        codec.decode_run_storage(packed)


@pytest.mark.parametrize("kind", ["truncated", "concatenated", "trailing", "corrupt"])
def test_zlib_stream_must_be_exactly_one_complete_stream(kind) -> None:
    packed = _envelope(b'{"value":"retained"}')
    envelope = packed[codec.ENVELOPE_KEY]
    stream = base64.b64decode(envelope["data"])
    if kind == "truncated":
        stream = stream[:-1]
    elif kind == "concatenated":
        stream += zlib.compress(b"extra")
    elif kind == "trailing":
        stream += b"extra"
    else:
        stream = b"invalid"
    envelope["data"] = base64.b64encode(stream).decode()
    with pytest.raises(ValueError, match="run_storage_"):
        codec.decode_run_storage(packed)


def test_declared_length_bounds_decompression_of_high_expansion_input() -> None:
    packed = _envelope(b"x" * 1024 * 1024)
    packed[codec.ENVELOPE_KEY]["size_bytes"] = 20
    with pytest.raises(ValueError, match="size_mismatch"):
        codec.decode_run_storage(packed)


@pytest.mark.parametrize("raw", [b"[]", b"null", b'"text"', b'{"__nico_comprehensive_run_storage_v1__":{}}'])
def test_envelope_requires_one_non_envelope_object(raw) -> None:
    with pytest.raises(ValueError, match="decoded_record_invalid"):
        codec.decode_run_storage(_envelope(raw))


def test_reserved_key_and_extra_envelope_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="reserved_envelope_key"):
        codec.encode_run_storage({codec.ENVELOPE_KEY: {}})
    packed = _envelope(b"{}")
    packed["extra"] = True
    with pytest.raises(ValueError, match="shape_invalid"):
        codec.decode_run_storage(packed)
    del packed["extra"]
    packed[codec.ENVELOPE_KEY]["extra"] = True
    with pytest.raises(ValueError, match="shape_invalid"):
        codec.decode_run_storage(packed)


def test_non_run_payload_decoder_does_not_interpret_storage_envelopes() -> None:
    packed = _envelope(b'{"value":"retained"}')
    assert _decode_json_object_payload(json.dumps(packed)) == packed


def test_encoder_and_decoder_enforce_size_limits(monkeypatch) -> None:
    monkeypatch.setattr(codec, "MAX_UNCOMPRESSED_BYTES", 20)
    with pytest.raises(ValueError, match="uncompressed_size_limit"):
        codec.encode_run_storage({"value": "a" * 100})
    monkeypatch.setattr(codec, "MAX_UNCOMPRESSED_BYTES", 1024)
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    monkeypatch.setattr(codec, "MAX_COMPRESSED_BYTES", 1)
    with pytest.raises(ValueError, match="compressed_size_limit"):
        codec.encode_run_storage({"value": "a" * 100})
    with pytest.raises(ValueError, match="compressed_size_limit"):
        codec.decode_run_storage(_envelope(b'{"value":"retained"}'))


def test_store_compressed_round_trip_cas_and_legacy_backfill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    database = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    original = store.create(_record())
    with sqlite3.connect(database) as connection:
        payload = json.loads(connection.execute("SELECT payload FROM nico_comprehensive_runs").fetchone()[0])
        assert set(payload) == {codec.ENVELOPE_KEY}
        connection.execute("DELETE FROM nico_comprehensive_review_history_commitments")
    assert store.load(original["identity"]["run_id"]) == original
    advanced = apply_comprehensive_stage_result(
        original, stage_id=COMPREHENSIVE_STAGES[0], result={"status": "complete", "evidence": {"all": "x" * 10000}}
    )
    assert store.save(advanced, expected_revision=original["revision"]) == advanced
    assert store.load(original["identity"]["run_id"]) == advanced
    assert store.list_recent(customer_id="customer", project_id="project") == [advanced]
    with pytest.raises(ComprehensiveRunConflict, match="stale_revision"):
        store.save(advanced, expected_revision=original["revision"])


def test_envelope_digest_does_not_replace_run_integrity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    database = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    record = store.create(_record())
    record["client_delivery_allowed"] = True
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE nico_comprehensive_runs SET payload = ?", (codec.encode_run_storage(record),))
    with pytest.raises(ValueError):
        store.load(record["identity"]["run_id"])


@pytest.mark.parametrize("lease_status", ["running", "superseded"])
def test_compressed_final_publication_remains_atomic_with_lease(tmp_path: Path, monkeypatch, lease_status) -> None:
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    database = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    record = _record()
    stage_id = "final_comprehensive_report_generation"
    for prior_stage in COMPREHENSIVE_STAGES:
        if prior_stage == stage_id:
            break
        record = apply_comprehensive_stage_result(record, stage_id=prior_stage, result={"status": "complete"})
    store.create(record)
    store.create_final_report_job(
        lease_id="lease-storage-codec", run_id=record["identity"]["run_id"],
        started_epoch=time.time(), heartbeat_epoch=time.time(), updated_at=record["updated_at"], status=lease_status,
    )
    updated = apply_comprehensive_stage_result(
        record, stage_id=stage_id,
        result={"status": "blocked", "reason": "retained-failure", "stage_execution": {"publication_lease_id": "lease-storage-codec"}},
    )
    if lease_status == "running":
        store.save(updated, expected_revision=record["revision"], publication_lease_id="lease-storage-codec")
        assert store.load(record["identity"]["run_id"]) == updated
    else:
        with pytest.raises(ComprehensiveRunConflict, match="publication_lease_inactive"):
            store.save(updated, expected_revision=record["revision"], publication_lease_id="lease-storage-codec")
        assert store.load(record["identity"]["run_id"]) == record
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM nico_comprehensive_final_report_jobs").fetchone()[0] == ("blocked" if lease_status == "running" else "superseded")


def test_compressed_run_still_checks_external_review_history_commitment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(codec, "COMPRESSION_THRESHOLD_BYTES", 1)
    database = tmp_path / "runs.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    record = store.create(_record())
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE nico_comprehensive_review_history_commitments SET event_count = 1")
    with pytest.raises(ValueError, match="review_history_commitment_cannot_be_truncated"):
        store.load(record["identity"]["run_id"])
