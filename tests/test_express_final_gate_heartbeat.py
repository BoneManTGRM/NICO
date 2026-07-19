from __future__ import annotations

import time

from nico import express_final_gate_heartbeat as heartbeat


class FakeApi:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def _record_stage(self, run_id, request_payload, stage, message, *, progress_percent=None, evidence=None):
        self.events.append(
            {
                "run_id": run_id,
                "request_payload": request_payload,
                "stage": stage,
                "message": message,
                "progress_percent": progress_percent,
                "evidence": evidence or {},
            }
        )
        return self.events[-1]


def test_final_gate_publishes_same_run_heartbeat_without_changing_result() -> None:
    api = FakeApi()
    heartbeat._CONTEXT.run_id = "express_run_test"
    heartbeat._CONTEXT.request_payload = {"repository": "BoneManTGRM/NICO"}

    expected = {"status": "complete", "reports": {"pdf_base64": "pdf"}}

    def slow_gate(payload):
        time.sleep(0.06)
        return expected

    try:
        result = heartbeat._run_with_heartbeat(
            api,
            slow_gate,
            {"run_id": "express_run_test"},
            operation="evidence_bundle",
            heartbeat_seconds=0.01,
        )
    finally:
        heartbeat._CONTEXT.run_id = ""
        heartbeat._CONTEXT.request_payload = None

    assert result is expected
    assert api.events
    assert all(event["stage"] == "truth_and_review_gates" for event in api.events)
    assert all(event["progress_percent"] == 96 for event in api.events)
    assert all(event["evidence"]["same_run_continuation"] is True for event in api.events)
    assert all(event["evidence"]["backend_task_active"] is True for event in api.events)


def test_final_gate_without_exact_run_context_calls_function_directly() -> None:
    api = FakeApi()
    heartbeat._CONTEXT.run_id = ""
    heartbeat._CONTEXT.request_payload = None
    payload = {"status": "running"}

    result = heartbeat._run_with_heartbeat(
        api,
        lambda value: value,
        payload,
        operation="acceptance_gate",
        heartbeat_seconds=0.01,
    )

    assert result is payload
    assert api.events == []
