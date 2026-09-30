from __future__ import annotations

import json

import pytest

from nico import comprehensive_run_storage_capacity_v1 as capacity
from nico import comprehensive_run_storage_codec_v1 as codec
from nico.comprehensive_run_store import ComprehensiveRunStore


def test_complete_counter_matches_independent_unicode_serialization_without_content():
    value = {"identity": {"private": "credential-do-not-retain"}, "evidence": ["東京ñ", 1, True]}
    expected = len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
    result = capacity.measure_rejected_run(value, storage_limit_bytes=512)
    assert result["measurement_complete"] is True
    assert result["canonical_size_bytes"] == expected
    assert result["canonical_size_lower_bound_bytes"] == expected
    assert result["storage_limits_changed"] is False
    assert "credential-do-not-retain" not in json.dumps(result)
    assert "東京" not in json.dumps(result)


def test_byte_boundary_reports_only_lower_bound(monkeypatch):
    monkeypatch.setattr(capacity, "MEASUREMENT_LIMIT_BYTES", 25)
    result = capacity.measure_rejected_run({"value": "x" * 100}, storage_limit_bytes=20)
    assert result["canonical_size_bytes"] is None
    assert result["canonical_size_lower_bound_bytes"] > 25
    assert result["measurement_stop_reason"] == "byte_limit"
    assert result["measurement_complete"] is False


def test_time_boundary_reports_only_lower_bound(monkeypatch):
    clock = iter([0.0, 50.0, 51.0])
    monkeypatch.setattr(capacity.time, "monotonic", lambda: next(clock))
    result = capacity.measure_rejected_run({"value": "private"}, storage_limit_bytes=20)
    assert result["canonical_size_bytes"] is None
    assert result["measurement_stop_reason"] == "time_limit"


def test_bad_input_does_not_log_exception_content():
    value = {"secret": object()}
    result = capacity.measure_rejected_run(value, storage_limit_bytes=20)
    assert result["measurement_complete"] is False
    assert result["measurement_stop_reason"] == "measurement_failed"
    assert "secret" not in json.dumps(result)


def test_rejected_save_logs_measurement_and_preserves_original_error(monkeypatch, capsys):
    monkeypatch.setattr(codec, "MAX_UNCOMPRESSED_BYTES", 40)
    value = {"identity": {"run_id": "private-run"}, "evidence": "secret" * 100}
    store = ComprehensiveRunStore(lambda: None)
    with pytest.raises(ValueError, match="^run_storage_uncompressed_size_limit$"):
        store._row_values(value)
    output = capsys.readouterr().out
    assert output.startswith("NICO_RUN_STORAGE_CAPACITY ")
    result = json.loads(output.split(" ", 1)[1])
    assert result["canonical_size_bytes"] > 40
    assert result["measurement_complete"] is True
    assert "secret" not in output and "private-run" not in output


def test_observer_failure_cannot_replace_rejection(monkeypatch):
    monkeypatch.setattr(codec, "MAX_UNCOMPRESSED_BYTES", 10)
    def fail(*args, **kwargs):
        raise RuntimeError("private-observer-error")
    monkeypatch.setattr(capacity, "measure_rejected_run", fail)
    with pytest.raises(ValueError, match="^run_storage_uncompressed_size_limit$"):
        ComprehensiveRunStore(lambda: None)._row_values({"identity": {}, "evidence": "x" * 100})


def test_successful_save_does_not_run_observer(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise AssertionError("observer must be failure-only")
    monkeypatch.setattr(capacity, "measure_rejected_run", fail)
    # A complete valid record is exercised by the existing store roundtrip tests.
    from nico.comprehensive_run_record import create_comprehensive_run_record
    value = create_comprehensive_run_record(run_id="capacity-unit", repository="owner/repo",
        commit_sha="a" * 40, evidence_ledger_id="ledger", customer_id="customer",
        project_id="project", authorized=True)
    assert ComprehensiveRunStore(lambda: None)._row_values(value)[-1]
    assert capsys.readouterr().out == ""
