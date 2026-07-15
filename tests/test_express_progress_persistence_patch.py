from __future__ import annotations

from nico import express_async_api as api
from nico.express_progress_persistence_patch import install_express_progress_persistence
from nico.storage import MemoryAdapter


def _payload() -> dict:
    return {
        "repository": "owner/repository",
        "customer_id": "customer_progress",
        "project_id": "project_progress",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_progress_record_survives_main_report_record_overwrite(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    install_express_progress_persistence()
    run_id = "express_run_progress_persistence"
    request = _payload()

    api._record(
        run_id,
        request,
        api._response(run_id, request, "queued", "Accepted", stage="request_accepted", progress_percent=4),
    )
    api._record_stage(run_id, request, "scanner_reconciliation", "Scanning")

    stale_complete = {
        "status": "complete",
        "run_id": run_id,
        "repository": request["repository"],
        "customer_id": request["customer_id"],
        "project_id": request["project_id"],
        "current_stage": "request_accepted",
        "progress_percent": 4,
        "progress": [],
        "reports": {"pdf_base64": "cGRm"},
    }
    store.put("assessment_runs", run_id, {
        "run_id": run_id,
        "customer_id": request["customer_id"],
        "project_id": request["project_id"],
        "repository": request["repository"],
        "status": "complete",
        "request": request,
        "response": stale_complete,
        "payload": stale_complete,
    })

    response = api.express_assessment_status(
        run_id,
        api.ExpressAssessmentStatusRequest(customer_id=request["customer_id"], project_id=request["project_id"]),
    )

    assert response["status"] == "complete"
    assert response["current_stage"] == "complete"
    assert response["progress_percent"] == 100
    assert all(item["status"] == "complete" for item in response["progress"])
    assert response["human_review_required"] is True
    assert response["client_ready"] is False


def test_running_status_uses_independent_latest_stage(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    install_express_progress_persistence()
    run_id = "express_run_progress_running"
    request = _payload()

    queued = api._response(run_id, request, "queued", "Accepted", stage="request_accepted", progress_percent=4)
    store.put("assessment_runs", run_id, {
        "run_id": run_id,
        "customer_id": request["customer_id"],
        "project_id": request["project_id"],
        "repository": request["repository"],
        "status": "running",
        "request": request,
        "response": queued,
        "payload": queued,
    })
    latest = api._response(run_id, request, "running", "Generating report", stage="report_generation", progress_percent=82)
    store.put("express_run_progress", run_id, {
        "run_id": run_id,
        "status": "running",
        "current_stage": "report_generation",
        "progress_percent": 82,
        "progress": latest["progress"],
        "updated_at": latest["updated_at"],
    })
    monkeypatch.setattr(api, "_ACTIVE_RUNS", {run_id})

    response = api.express_assessment_status(
        run_id,
        api.ExpressAssessmentStatusRequest(customer_id=request["customer_id"], project_id=request["project_id"]),
    )

    assert response["status"] == "running"
    assert response["current_stage"] == "report_generation"
    assert response["progress_percent"] == 82
    assert next(item for item in response["progress"] if item["step"] == "report_generation")["status"] == "running"


def test_installer_is_idempotent() -> None:
    first = install_express_progress_persistence()
    second = install_express_progress_persistence()

    assert first["terminal_success_forces_100_percent"] is True
    assert second["status"] == "installed"
    assert getattr(api._record, "_nico_express_progress_record_v1", False) is True
    assert getattr(api.express_assessment_status, "_nico_express_progress_status_v1", False) is True
