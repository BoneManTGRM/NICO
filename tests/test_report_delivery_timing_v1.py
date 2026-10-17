import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from nico.report_delivery_timing_v1 import report_delivery_phase, report_delivery_timing


@report_delivery_phase("controller_status")
def _phase(value):
    if isinstance(value, Exception):
        raise value
    return value


def _records(caplog):
    return [json.loads(record.getMessage().split("=", 1)[1])
            for record in caplog.records if record.getMessage().startswith("NICO_REPORT_TIMING=")]


def test_timing_preserves_result_exception_and_context_without_logging_payload(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    sensitive = {"private": "CREDENTIAL_OR_REPORT_TEXT"}
    assert _phase(sensitive) is sensitive
    assert not _records(caplog)
    run = "comprun_" + "a" * 32
    with report_delivery_timing(run, "en"):
        assert _phase(sensitive) is sensitive
    error = ValueError("CREDENTIAL_OR_REPORT_TEXT")
    with pytest.raises(ValueError) as caught:
        with report_delivery_timing(run, "es-MX"):
            _phase(error)
    assert caught.value is error
    assert _phase(sensitive) is sensitive
    records = _records(caplog)
    assert len(records) == 2
    assert records[0]["outcome"] == "completed"
    assert records[1]["outcome"] == "failed"
    assert records[1]["error_type"] == "ValueError"
    assert all(r["phases"]["controller_status"]["calls"] == 1 for r in records)
    assert all(r["http_transfer_completion_inferred"] is False for r in records)
    assert "CREDENTIAL_OR_REPORT_TEXT" not in caplog.text


def test_concurrent_route_contexts_remain_separate(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    barrier = Barrier(2)
    def request(index):
        run = "comprun_" + str(index) * 32
        with report_delivery_timing(run, "en"):
            barrier.wait(timeout=2)
            assert _phase(index) == index
        return index
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, [1, 2])) == [1, 2]
    records = _records(caplog)
    assert {r["run_id"] for r in records} == {"comprun_" + "1" * 32, "comprun_" + "2" * 32}
    assert all(r["phases"]["controller_status"]["calls"] == 1 for r in records)


def test_invalid_request_fields_do_not_enter_logs(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with report_delivery_timing("PRIVATE_TOKEN", "PRIVATE_TOKEN"):
        _phase(True)
    record = _records(caplog)[0]
    assert record["run_id"] == "invalid_or_fixture_run_id"
    assert record["report_language"] == "unsupported"
    assert "PRIVATE_TOKEN" not in caplog.text


def test_logger_failure_does_not_change_delivery_or_original_error(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("logging transport unavailable")
    monkeypatch.setattr("nico.report_delivery_timing_v1._LOGGER.info", unavailable)
    with report_delivery_timing("comprun_" + "a" * 32, "en"):
        assert _phase(7) == 7
    original = ValueError("original delivery error")
    with pytest.raises(ValueError) as caught:
        with report_delivery_timing("comprun_" + "a" * 32, "en"):
            _phase(original)
    assert caught.value is original


def _progress_records(caplog):
    return [json.loads(record.getMessage().split("=", 1)[1])
            for record in caplog.records if record.getMessage().startswith("NICO_REPORT_PROGRESS=")]


def test_progress_is_visible_before_handler_exit_and_final_stays_compatible(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with report_delivery_timing("comprun_" + "a" * 32, "es-MX"):
        assert [r["event"] for r in _progress_records(caplog)] == ["route_started"]
        assert not _records(caplog)
        assert _phase(7) == 7
        progress = _progress_records(caplog)
        assert [r["event"] for r in progress] == ["route_started", "phase_completed"]
        assert progress[1]["phase"] == "controller_status"
        assert progress[1]["outcome"] == "completed"
        assert progress[1]["calls"] == 1
        assert progress[1]["elapsed_ms"] >= 0
        assert progress[1]["thread_cpu_ms"] >= 0
        assert not _records(caplog)
    final, = _records(caplog)
    assert final["schema"] == "nico.report-delivery-timing.v1"
    assert {r["request_id"] for r in [*progress, final]} == {final["request_id"]}
    assert len(final["request_id"]) == 32
    assert final["phases"]["controller_status"]["calls"] == 1


def test_failed_phase_logs_class_without_message_before_outer_exit(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    original = ValueError("SECRET_REPORT_CONTENT")
    with report_delivery_timing("PRIVATE_TOKEN", "PRIVATE_TOKEN"):
        with pytest.raises(ValueError) as caught:
            _phase(original)
        assert caught.value is original
        failed = _progress_records(caplog)[-1]
        assert failed["outcome"] == "failed"
        assert failed["error_type"] == "ValueError"
        assert not _records(caplog)
    assert "SECRET_REPORT_CONTENT" not in caplog.text
    assert "PRIVATE_TOKEN" not in caplog.text


def test_strict_log_cap_reserves_final_and_keeps_all_aggregate_calls(caplog):
    from nico.report_delivery_timing_v1 import _MAX_RECORDS_PER_REQUEST, _PHASE_NAMES, report_delivery_phase_scope
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with report_delivery_timing("comprun_" + "a" * 32, "en"):
        for _ in range(100):
            _phase(True)
        for name in sorted(_PHASE_NAMES):
            with report_delivery_phase_scope(name):
                pass
    progress = _progress_records(caplog)
    final, = _records(caplog)
    assert len(progress) + 1 == _MAX_RECORDS_PER_REQUEST
    assert [r["sequence"] for r in progress] == list(range(1, len(progress) + 1))
    assert len([r for r in progress if r.get("phase") == "controller_status"]) == 1
    assert final["phases"]["controller_status"]["calls"] == 101
    assert set(final["phases"]) == _PHASE_NAMES
    assert final["progress_records"] == len(progress)
    assert final["progress_suppressed"] == 1 + 100 + len(_PHASE_NAMES) - len(progress)


def test_unknown_phase_names_cannot_leak_and_no_context_emits_nothing(caplog):
    from nico.report_delivery_timing_v1 import report_delivery_phase_scope
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with report_delivery_phase_scope("SECRET_PHASE_NAME"):
        pass
    assert not caplog.records
    with report_delivery_timing("comprun_" + "a" * 32, "en"):
        with report_delivery_phase_scope("SECRET_PHASE_NAME"):
            pass
    assert "SECRET_PHASE_NAME" not in caplog.text
    assert _progress_records(caplog)[-1]["phase"] == "unknown_phase"
    assert set(_records(caplog)[0]["phases"]) == {"unknown_phase"}


def test_same_run_concurrent_progress_has_distinct_request_ids(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    barrier = Barrier(2)
    def request(index):
        with report_delivery_timing("comprun_" + "a" * 32, "en"):
            barrier.wait(timeout=2)
            return _phase(index)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, [1, 2])) == [1, 2]
    finals = _records(caplog)
    assert len({r["request_id"] for r in finals}) == 2
    for final in finals:
        progress = [r for r in _progress_records(caplog) if r["request_id"] == final["request_id"]]
        assert [r["event"] for r in progress] == ["route_started", "phase_completed"]
