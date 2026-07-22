from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class _Page:
    def __init__(self) -> None:
        self.waits: list[int] = []

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


def _module():
    sys.path.insert(0, str(SCRIPTS))
    try:
        for name in (
            "two_service_live_acceptance_v3",
            "two_service_live_acceptance_v2",
            "two_service_live_acceptance",
        ):
            sys.modules.pop(name, None)
        return importlib.import_module("two_service_live_acceptance_v3")
    finally:
        sys.path.remove(str(SCRIPTS))


def _payload(status: str, *, terminal: bool = False, stage: str = "truth_and_review_gates") -> dict:
    return {
        "run_id": "express_run_terminal_race",
        "status": status,
        "current_stage": stage,
        "progress_percent": 100 if terminal else 94,
        "terminal": terminal,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "record": {
            "status": status,
            "current_stage": stage,
            "progress_percent": 100 if terminal else 94,
            "terminal": terminal,
        },
    }


def test_terminal_ui_reconciles_stale_running_sample_to_exact_terminal_record(monkeypatch) -> None:
    module = _module()
    page = _Page()
    state = {"phase_label": "Complete", "run_id": "express_run_terminal_race"}
    history: list[dict] = []
    responses = [_payload("running"), _payload("complete", terminal=True)]

    monkeypatch.setattr(
        module,
        "_original_wait_for_service_terminal",
        lambda **_: ({}, state, True),
    )

    def backend_status(_page, _service, _identity):
        payload = responses.pop(0)
        return payload, module.runtime._status_summary(payload, http_status=200)

    monkeypatch.setattr(module.runtime, "_backend_status", backend_status)
    monkeypatch.setattr(module, "UI_BACKEND_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(module, "UI_BACKEND_RECONCILIATION_SECONDS", 5.0)

    final, observed_state, ui_terminal = module._wait_for_service_terminal(
        page=page,
        service="express",
        identity_payload={"run_id": "express_run_terminal_race"},
        timeout_ms=600_000,
        status_history=history,
    )

    assert final["status"] == "complete"
    assert final["terminal"] is True
    assert observed_state == state
    assert ui_terminal is True
    assert [item["status"] for item in history] == ["running", "complete"]


def test_terminal_ui_does_not_convert_persisted_failure_into_success(monkeypatch) -> None:
    module = _module()
    page = _Page()
    state = {"phase_label": "Complete", "run_id": "express_run_terminal_race"}
    failed = _payload("failed", terminal=True, stage="truth_and_review_gates")

    monkeypatch.setattr(
        module,
        "_original_wait_for_service_terminal",
        lambda **_: ({}, state, True),
    )
    monkeypatch.setattr(
        module.runtime,
        "_backend_status",
        lambda *_: (failed, module.runtime._status_summary(failed, http_status=200)),
    )

    final, _, ui_terminal = module._wait_for_service_terminal(
        page=page,
        service="express",
        identity_payload={"run_id": "express_run_terminal_race"},
        timeout_ms=600_000,
        status_history=[],
    )

    assert final["status"] == "failed"
    assert ui_terminal is False


def test_nonterminal_observer_result_is_preserved(monkeypatch) -> None:
    module = _module()
    page = _Page()
    running = _payload("running")
    state = {"phase_label": "Running automatically", "run_id": "express_run_terminal_race"}

    monkeypatch.setattr(
        module,
        "_original_wait_for_service_terminal",
        lambda **_: (running, state, False),
    )

    final, observed_state, ui_terminal = module._wait_for_service_terminal(
        page=page,
        service="express",
        identity_payload={"run_id": "express_run_terminal_race"},
        timeout_ms=600_000,
        status_history=[],
    )

    assert final is running
    assert observed_state == state
    assert ui_terminal is False
