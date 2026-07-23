from __future__ import annotations

import importlib

import nico.express_async_api as api
import nico.express_status_liveness_patch as liveness
import nico.lifecycle_status_hardening as hardening
from nico.storage import MemoryAdapter


def _request() -> dict:
    return {
        "repository": "owner/repository",
        "customer_id": "customer_terminal",
        "project_id": "project_terminal",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _reports() -> dict:
    return {
        "report_id": "express_report_terminal_reconciliation",
        "markdown": "# Express report",
        "html": "<!doctype html><html><body>Express report</body></html>",
        "pdf_base64": "JVBERi0xLjQK",
    }


def test_outer_liveness_wrapper_reconciles_verified_terminal_progress(monkeypatch) -> None:
    store = MemoryAdapter()
    request = _request()
    run_id = "express_run_outer_liveness_terminal"
    stale = api._response(
        run_id,
        request,
        "running",
        "Applying final truth and review gates",
        stage="truth_and_review_gates",
        progress_percent=94,
    )
    stale.update(
        {
            "worker_started": True,
            "heartbeat_at": "2099-07-23T00:00:00Z",
            "reports": _reports(),
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
            "created_at": "2099-07-22T23:50:00Z",
            "updated_at": "2099-07-23T00:00:00Z",
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
            "progress": api._stage_progress("complete", "complete", "Complete"),
            "terminal": True,
            "terminal_success_ready": True,
            "report_formats_ready": True,
            "report_generation_status": "complete",
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
    )

    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)

    def base_status(run_id_value: str, customer_id: str, project_id: str) -> dict:
        record = store.get("assessment_runs", run_id_value)
        assert isinstance(record, dict)
        assert hardening._scope_matches(record, customer_id, project_id)
        return hardening._safe_retained_response(record)

    monkeypatch.setattr(hardening, "_express_status_response", base_status)
    module = importlib.reload(liveness)
    installed = module.install_express_status_liveness_patch()

    response = hardening._express_status_response(
        run_id,
        request["customer_id"],
        request["project_id"],
    )

    assert installed["independent_terminal_progress_reconciliation"] is True
    assert getattr(
        hardening._express_status_response,
        "_nico_express_independent_progress_reconciliation_v1",
        False,
    ) is True
    assert response["status"] == "complete"
    assert response["current_stage"] == "complete"
    assert response["progress_percent"] == 100
    assert response["reports"]["report_id"] == "express_report_terminal_reconciliation"
    assert response["technical_score"] == 78
    assert response["progress_reconciliation"]["terminal_success_recovered"] is True
    assert response["lifecycle_status"]["independent_terminal_progress_reconciliation"] is True
    assert response["lifecycle_status"]["status_read_is_terminal_write"] is False
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
    assert response["client_delivery_allowed"] is False


def test_outer_liveness_wrapper_does_not_promote_incomplete_progress(monkeypatch) -> None:
    store = MemoryAdapter()
    request = _request()
    run_id = "express_run_outer_liveness_incomplete"
    stale = api._response(
        run_id,
        request,
        "running",
        "Applying final truth and review gates",
        stage="truth_and_review_gates",
        progress_percent=94,
    )
    stale.update({"worker_started": True, "heartbeat_at": "2099-07-23T00:00:00Z"})
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
            "created_at": "2099-07-22T23:50:00Z",
            "updated_at": "2099-07-23T00:00:00Z",
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
            "progress": [],
            "terminal": True,
            "terminal_success_ready": False,
            "report_formats_ready": False,
        },
    )

    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)

    def base_status(run_id_value: str, customer_id: str, project_id: str) -> dict:
        record = store.get("assessment_runs", run_id_value)
        assert isinstance(record, dict)
        assert hardening._scope_matches(record, customer_id, project_id)
        return hardening._safe_retained_response(record)

    monkeypatch.setattr(hardening, "_express_status_response", base_status)
    module = importlib.reload(liveness)
    module.install_express_status_liveness_patch()

    response = hardening._express_status_response(
        run_id,
        request["customer_id"],
        request["project_id"],
    )

    assert response["status"] == "running"
    assert response["current_stage"] == "truth_and_review_gates"
    assert response["progress_percent"] == 94
    assert "progress_reconciliation" not in response
