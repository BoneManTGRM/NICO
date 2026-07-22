from __future__ import annotations

import pytest
from fastapi import HTTPException

from nico import express_async_api as api
from nico import lifecycle_status_hardening as hardening
from nico.express_progress_persistence_patch import (
    _progress_identity,
    _reconcile_progress_identity,
    install_express_progress_persistence,
)
from nico.storage import MemoryAdapter


def _payload() -> dict:
    return {
        "repository": "owner/repository",
        "customer_id": "customer_progress",
        "project_id": "project_progress",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _rich_reports() -> dict:
    return {
        "report_id": "express_report_progress",
        "markdown": "# Express report",
        "html": "<!doctype html><html><body>Express report</body></html>",
        "pdf_base64": "JVBERi0xLjQK",
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


def test_hardened_production_status_recovers_verified_terminal_progress(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)
    install_express_progress_persistence()
    run_id = "express_run_hardened_terminal_progress"
    request = _payload()

    stale = api._response(
        run_id,
        request,
        "running",
        "Applying final truth gates",
        stage="truth_and_review_gates",
        progress_percent=94,
    )
    stale.update(
        {
            "worker_started": True,
            "heartbeat_at": "2099-07-22T23:30:00Z",
            "reports": _rich_reports(),
            "sections": [{"id": "summary", "label": "Summary"}],
            "technical_score": 78,
        }
    )
    store.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "run_id": run_id,
            "status": "running",
            "customer_id": request["customer_id"],
            "project_id": request["project_id"],
            "repository": request["repository"],
            "request": request,
            "response": stale,
            "payload": stale,
            "created_at": "2099-07-22T23:20:00Z",
            "updated_at": "2099-07-22T23:30:00Z",
        },
    )
    terminal = {
        **stale,
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "report_generation_status": "complete",
        "progress": api._stage_progress("complete", "complete", "Complete"),
    }
    store.put("express_run_progress", run_id, _progress_identity(terminal))

    response = hardening._express_status_response(
        run_id,
        request["customer_id"],
        request["project_id"],
    )

    assert response["status"] == "complete"
    assert response["current_stage"] == "complete"
    assert response["progress_percent"] == 100
    assert response["reports"]["report_id"] == "express_report_progress"
    assert response["technical_score"] == 78
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
    assert response["client_delivery_allowed"] is False
    assert response["progress_reconciliation"]["terminal_success_recovered"] is True
    assert response["lifecycle_status"]["status_read_is_terminal_write"] is False


def test_hardened_status_does_not_promote_incomplete_terminal_progress(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)
    install_express_progress_persistence()
    run_id = "express_run_incomplete_terminal_progress"
    request = _payload()
    running = api._response(
        run_id,
        request,
        "running",
        "Applying final truth gates",
        stage="truth_and_review_gates",
        progress_percent=94,
    )
    running.update({"worker_started": True, "heartbeat_at": "2099-07-22T23:30:00Z"})
    store.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "run_id": run_id,
            "status": "running",
            "customer_id": request["customer_id"],
            "project_id": request["project_id"],
            "repository": request["repository"],
            "request": request,
            "response": running,
            "payload": running,
            "created_at": "2099-07-22T23:20:00Z",
            "updated_at": "2099-07-22T23:30:00Z",
        },
    )
    store.put(
        "express_run_progress",
        run_id,
        {
            "run_id": run_id,
            "status": "complete",
            "current_stage": "complete",
            "progress_percent": 100,
            "terminal": True,
            "terminal_success_ready": False,
            "report_formats_ready": False,
            "progress": [],
        },
    )

    response = hardening._express_status_response(
        run_id,
        request["customer_id"],
        request["project_id"],
    )

    assert response["status"] == "running"
    assert response["current_stage"] == "truth_and_review_gates"
    assert response["progress_percent"] == 94
    assert "progress_reconciliation" not in response


def test_terminal_progress_identity_cannot_regress_to_late_running_write() -> None:
    terminal = {
        "run_id": "express_run_sticky_terminal_progress",
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "terminal": True,
        "terminal_success_ready": True,
        "report_formats_ready": True,
        "progress": [],
    }
    late_running = {
        "run_id": terminal["run_id"],
        "status": "running",
        "current_stage": "truth_and_review_gates",
        "progress_percent": 96,
        "terminal": False,
        "terminal_success_ready": False,
        "report_formats_ready": True,
        "progress": [],
    }

    reconciled = _reconcile_progress_identity(terminal, late_running)

    assert reconciled == terminal
    assert reconciled["status"] == "complete"


def test_progress_overlay_never_replaces_tenant_scope_not_found(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    install_express_progress_persistence()
    run_id = "express_run_progress_scope"
    request = _payload()

    queued = api._response(run_id, request, "queued", "Accepted", stage="request_accepted", progress_percent=4)
    api._record(run_id, request, queued)
    monkeypatch.setattr(api, "_ACTIVE_RUNS", {run_id})

    with pytest.raises(HTTPException) as exc:
        api.express_assessment_status(
            run_id,
            api.ExpressAssessmentStatusRequest(
                customer_id=request["customer_id"],
                project_id="different_project",
            ),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == {
        "status": "not_found",
        "message": "Express assessment run not found.",
    }


def test_installer_is_idempotent() -> None:
    first = install_express_progress_persistence()
    second = install_express_progress_persistence()

    assert first["terminal_success_forces_100_percent"] is True
    assert first["production_hardened_status_uses_terminal_progress"] is True
    assert first["terminal_progress_can_regress"] is False
    assert first["tenant_scope_failures_are_never_overlaid"] is True
    assert second["status"] == "installed"
    assert getattr(api._record, "_nico_express_progress_record_v1", False) is True
    assert getattr(api.express_assessment_status, "_nico_express_progress_status_v1", False) is True
    assert getattr(hardening._express_status_response, "_nico_express_hardened_progress_status_v1", False) is True
