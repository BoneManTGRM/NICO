from __future__ import annotations

import inspect

from nico import comprehensive_final_report_process_isolation_v1 as isolation


def test_process_isolation_response_wrapper_accepts_and_forwards_browser_projection(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def original_response(
        record: dict[str, object],
        *,
        operation: str,
        browser_projection: bool = False,
    ) -> dict[str, object]:
        observed["record"] = record
        observed["operation"] = operation
        observed["browser_projection"] = browser_projection
        return {
            "record": {},
            "response_projection": {"browser_projection": browser_projection},
        }

    monkeypatch.setattr(isolation, "_ORIGINAL_CONTROLLER_RESPONSE", original_response)

    signature = inspect.signature(isolation._controller_response_with_execution)
    assert signature.parameters["browser_projection"].default is False

    record = {
        "active_stage_execution": {
            "state": "rendering",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    }
    response = isolation._controller_response_with_execution(
        record,
        operation="status",
        browser_projection=True,
    )

    assert observed == {
        "record": record,
        "operation": "status",
        "browser_projection": True,
    }
    assert response["response_projection"]["browser_projection"] is True
    assert response["active_stage_execution"]["state"] == "rendering"
    assert response["record"]["active_stage_execution"]["state"] == "rendering"


def test_process_isolation_response_wrapper_preserves_non_browser_default(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def original_response(
        record: dict[str, object],
        *,
        operation: str,
        browser_projection: bool = False,
    ) -> dict[str, object]:
        observed["browser_projection"] = browser_projection
        return {"record": {}}

    monkeypatch.setattr(isolation, "_ORIGINAL_CONTROLLER_RESPONSE", original_response)

    isolation._controller_response_with_execution({}, operation="status")
    assert observed["browser_projection"] is False
