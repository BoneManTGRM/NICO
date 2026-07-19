from __future__ import annotations

import threading

from nico import express_repository_stage_watchdog as watchdog


class _Api:
    def __init__(self) -> None:
        self.records: list[tuple] = []

    def _record_stage(self, *args, **kwargs) -> None:
        self.records.append((args, kwargs))


def test_authoritative_repository_task_runs_in_calling_thread(monkeypatch) -> None:
    api = _Api()
    calling_thread = threading.get_ident()
    observed: list[int] = []
    monkeypatch.setattr(watchdog, "_context", lambda: ("express_run_test", {"repository": "BoneManTGRM/NICO"}))

    def assessment(payload: dict) -> dict:
        observed.append(threading.get_ident())
        return {"status": "ok", "payload": payload}

    result = watchdog._run_with_watchdog(api, assessment, {"authorized": True})

    assert result["status"] == "ok"
    assert observed == [calling_thread]


def test_assessment_exception_is_not_hidden_or_replaced(monkeypatch) -> None:
    api = _Api()
    monkeypatch.setattr(watchdog, "_context", lambda: ("express_run_test", {"repository": "BoneManTGRM/NICO"}))

    def assessment(_payload: dict) -> dict:
        raise ValueError("authoritative failure")

    try:
        watchdog._run_with_watchdog(api, assessment, {})
    except ValueError as exc:
        assert str(exc) == "authoritative failure"
    else:  # pragma: no cover
        raise AssertionError("authoritative exception was swallowed")


def test_heartbeat_failure_never_aborts_assessment(monkeypatch) -> None:
    class BrokenApi:
        def _record_stage(self, *_args, **_kwargs) -> None:
            raise RuntimeError("storage unavailable")

    monkeypatch.setattr(watchdog, "_context", lambda: ("express_run_test", {"repository": "BoneManTGRM/NICO"}))
    monkeypatch.setattr(watchdog, "_HEARTBEAT_SECONDS", 0.001)

    result = watchdog._run_with_watchdog(BrokenApi(), lambda payload: {"status": "ok", **payload}, {"value": 1})

    assert result == {"status": "ok", "value": 1}
