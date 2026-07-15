from __future__ import annotations

import nico.express_async_api as express
from nico.storage import MemoryAdapter


def payload() -> dict:
    return {
        "repository": "owner/repository",
        "customer_id": "customer_progress",
        "project_id": "project_progress",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_queued_response_exposes_full_stage_plan_and_real_percentage() -> None:
    response = express._response(
        "express_run_progress",
        payload(),
        "queued",
        "Accepted",
        stage="request_accepted",
        progress_percent=4,
    )

    assert response["current_stage"] == "request_accepted"
    assert response["progress_percent"] == 4
    assert len(response["progress"]) == 8
    assert response["progress"][0]["status"] == "queued"
    assert response["progress"][1]["status"] == "pending"
    assert response["progress"][-1]["step"] == "complete"


def test_recorded_stage_marks_prior_stages_complete_and_future_stages_pending(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)

    response = express._record_stage(
        "express_run_progress",
        payload(),
        "report_generation",
        "Generating reports",
        evidence={"score_reconciled": True},
    )

    by_step = {item["step"]: item for item in response["progress"]}
    assert response["progress_percent"] == 82
    assert by_step["score_reconciliation"]["status"] == "complete"
    assert by_step["report_generation"]["status"] == "running"
    assert by_step["report_generation"]["evidence"]["score_reconciled"] is True
    assert by_step["truth_and_review_gates"]["status"] == "pending"
    assert store.get("assessment_runs", "express_run_progress")["response"]["current_stage"] == "report_generation"


def test_complete_progress_is_terminal_and_human_review_bound() -> None:
    response = express._response(
        "express_run_progress",
        payload(),
        "complete",
        "Complete",
        stage="complete",
        progress_percent=100,
    )

    assert response["progress_percent"] == 100
    assert all(item["status"] == "complete" for item in response["progress"])
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
