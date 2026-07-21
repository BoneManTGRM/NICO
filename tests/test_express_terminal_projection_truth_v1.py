from __future__ import annotations

from nico.express_terminal_projection_truth_v1 import normalize_terminal_express_projection


def _reports() -> dict:
    return {
        "markdown": "# Express report\n" + "evidence\n" * 100,
        "html": "<!doctype html><html><body>Express report</body></html>",
        "pdf_base64": "JVBERi0xLjQK" * 20,
    }


def test_active_projection_with_terminal_artifacts_cannot_show_running_and_complete() -> None:
    response = {
        "status": "running",
        "current_stage": "scanner_reconciliation",
        "progress_percent": 53,
        "reports": _reports(),
        "scanner": {"status": "complete"},
        "progress": [
            {"step": "truth_and_review_gates", "status": "running", "message": "Applying gates."},
            {"step": "complete", "status": "complete", "message": "Artifacts ready."},
        ],
    }

    projected = normalize_terminal_express_projection(response)

    assert projected["status"] == "complete"
    assert projected["current_stage"] == "complete"
    assert projected["progress_percent"] == 100
    assert projected["terminal_state"] == "human_review_pending"
    assert projected["human_review_status"] == "pending"
    assert projected["client_delivery_allowed"] is False
    assert all(item["status"] == "complete" for item in projected["progress"])
    assert projected["express_terminal_projection_truth"]["artifact_terminal_recovered"] is True
    assert projected["express_terminal_projection_truth"]["running_and_complete_steps_can_coexist"] is False


def test_active_projection_without_complete_scanner_remains_active() -> None:
    response = {
        "status": "running",
        "current_stage": "scanner_reconciliation",
        "progress_percent": 53,
        "reports": _reports(),
        "scanner": {"status": "running"},
        "progress": [{"step": "complete", "status": "complete"}],
    }

    projected = normalize_terminal_express_projection(response)

    assert projected["status"] == "running"
    assert projected["current_stage"] == "scanner_reconciliation"
    assert projected["progress_percent"] == 53
    assert "express_terminal_projection_truth" not in projected


def test_explicit_terminal_response_is_always_normalized() -> None:
    response = {
        "status": "completed",
        "current_stage": "truth_and_review_gates",
        "progress_percent": 94,
        "reports": _reports(),
        "scanner": {"status": "complete"},
        "progress": [{"step": "truth_and_review_gates", "status": "running"}],
    }

    projected = normalize_terminal_express_projection(response)

    assert projected["status"] == "complete"
    assert projected["current_stage"] == "complete"
    assert projected["progress_percent"] == 100
    assert all(item["status"] == "complete" for item in projected["progress"])
    assert projected["express_terminal_projection_truth"]["explicit_terminal"] is True
