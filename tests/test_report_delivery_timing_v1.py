import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from nico.report_delivery_timing_v1 import report_delivery_phase, report_delivery_timing


@report_delivery_phase("fixture_phase")
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
    assert all(r["phases"]["fixture_phase"]["calls"] == 1 for r in records)
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
    assert all(r["phases"]["fixture_phase"]["calls"] == 1 for r in records)


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
