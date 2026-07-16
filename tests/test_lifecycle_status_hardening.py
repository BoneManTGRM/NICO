from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.lifecycle_status_hardening as hardening
from nico.storage import MemoryAdapter


def _express_record() -> dict:
    return {
        "run_id": "express_run_status_hardening",
        "workflow": "express",
        "status": "queued",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "repository": "owner/repository",
        "created_at": "2099-07-15T18:59:55Z",
        "updated_at": "2099-07-15T19:00:00Z",
        "request": {
            "repository": "owner/repository",
            "customer_id": "default_customer",
            "project_id": "default_project",
        },
        "response": {
            "status": "queued",
            "run_id": "express_run_status_hardening",
            "assessment_type": "express",
            "service_tier": "express",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "current_stage": "request_accepted",
            "progress_percent": 4,
            "created_at": "2099-07-15T18:59:55Z",
            "updated_at": "2099-07-15T19:00:00Z",
            "human_review_required": True,
            "client_ready": False,
        },
    }


def _mid_store() -> MemoryAdapter:
    store = MemoryAdapter()
    store.put(
        "assessment_runs",
        "midrun_status_hardening",
        {
            "run_id": "midrun_status_hardening",
            "workflow": "mid_assessment",
            "status": "running",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "repository": "owner/repository",
            "scan_id": "scan_snapshot_status_hardening",
            "request": {
                "repository": "owner/repository",
                "customer_id": "default_customer",
                "project_id": "default_project",
                "scan_id": "scan_snapshot_status_hardening",
            },
            "response": {
                "status": "running",
                "run_id": "midrun_status_hardening",
                "assessment_type": "mid",
                "service_tier": "mid",
                "current_stage": "scanner_worker",
                "progress_percent": 47,
                "human_review_required": True,
                "client_ready": False,
            },
        },
    )
    store.put(
        "scanner_runs",
        "scan_snapshot_status_hardening",
        {
            "scan_id": "scan_snapshot_status_hardening",
            "run_id": "midrun_status_hardening",
            "status": "running",
            "current_stage": "scanner_suite",
            "progress_percent": 67,
            "active_tool": "trufflehog",
            "heartbeat_at": "2099-07-15T19:00:00Z",
            "updated_at": "2099-07-15T19:00:00Z",
            "customer_id": "default_customer",
            "project_id": "default_project",
        },
    )
    return store


def _client(store: MemoryAdapter) -> TestClient:
    app = FastAPI()
    app.add_api_route(hardening.EXPRESS_STATUS_PATH, hardening.express_status_endpoint, methods=["POST"])
    return TestClient(app)


def test_express_status_accepts_empty_body_without_framework_422(monkeypatch) -> None:
    store = MemoryAdapter()
    record = _express_record()
    store.put("assessment_runs", record["run_id"], record)
    monkeypatch.setattr(hardening, "STORE", store)
    client = _client(store)

    response = client.post("/assessment/express-run/express_run_status_hardening/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "express_run_status_hardening"
    assert payload["progress_percent"] == 4
    assert payload["lifecycle_status"]["request_validation_422_possible"] is False
    assert payload["lifecycle_status"]["worker_started"] is False


def test_express_status_preserves_worker_stage_and_scanner_projection(monkeypatch) -> None:
    store = MemoryAdapter()
    record = _express_record()
    record["status"] = "running"
    record["response"].update(
        {
            "status": "running",
            "current_stage": "scanner_reconciliation",
            "progress_percent": 48,
            "worker_started": True,
            "worker_started_at": "2099-07-15T19:00:00Z",
            "worker_process_id": 321,
            "worker_thread": "nico-express_0",
            "backend_stage": "attach_existing_worker_evidence",
            "status_truth": "durable_worker_stage",
            "heartbeat_at": "2099-07-15T19:00:05Z",
            "scanner": {
                "status": "reconciling",
                "current_stage": "scanner_reconciliation",
                "progress_percent": 0,
                "active_tool": "dependency_reconciliation",
            },
        }
    )
    store.put("assessment_runs", record["run_id"], record)
    monkeypatch.setattr(hardening, "STORE", store)
    client = _client(store)

    response = client.post("/assessment/express-run/express_run_status_hardening/status", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_stage"] == "scanner_reconciliation"
    assert payload["progress_percent"] == 48
    assert payload["worker_started"] is True
    assert payload["backend_stage"] == "attach_existing_worker_evidence"
    assert payload["scanner"]["status"] == "reconciling"
    assert payload["scanner"]["active_tool"] == "dependency_reconciliation"
    assert payload["lifecycle_status"]["worker_started"] is True
    assert payload["lifecycle_status"]["scanner_status"] == "reconciling"


def test_express_completed_status_preserves_report_and_review_payload(monkeypatch) -> None:
    store = MemoryAdapter()
    record = _express_record()
    record["status"] = "complete"
    record["response"] = {
        "status": "complete",
        "run_id": record["run_id"],
        "assessment_type": "express",
        "service_tier": "express",
        "repository": "owner/repository",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "current_stage": "complete",
        "progress_percent": 100,
        "worker_started": True,
        "reports": {
            "report_id": "express_report_status_hardening",
            "markdown": "# Express report",
            "html": "<html><body>Express report</body></html>",
            "pdf_base64": "JVBERi0xLjQK",
        },
        "sections": [{"id": "summary", "label": "Summary", "truth_status": "verified"}],
        "report_quality_manifest": {"status": "ready_for_human_review", "quality_score": 96},
        "human_review_required": True,
        "client_ready": False,
    }
    store.put("assessment_runs", record["run_id"], record)
    monkeypatch.setattr(hardening, "STORE", store)
    client = _client(store)

    response = client.post("/assessment/express-run/express_run_status_hardening/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reports"]["report_id"] == "express_report_status_hardening"
    assert payload["reports"]["pdf_base64"] == "JVBERi0xLjQK"
    assert payload["sections"][0]["id"] == "summary"
    assert payload["report_quality_manifest"]["quality_score"] == 96
    assert payload["human_review_required"] is True
    assert payload["client_ready"] is False


def test_express_accepted_run_without_worker_handshake_becomes_recovery_evidence(monkeypatch) -> None:
    store = MemoryAdapter()
    record = _express_record()
    record["created_at"] = "2020-01-01T00:00:00Z"
    record["updated_at"] = "2099-07-15T19:00:00Z"
    record["response"]["created_at"] = "2020-01-01T00:00:00Z"
    record["response"]["updated_at"] = "2099-07-15T19:00:00Z"
    store.put("assessment_runs", record["run_id"], record)
    monkeypatch.setattr(hardening, "STORE", store)
    monkeypatch.setattr(hardening.express_async_api, "STORE", store)
    client = _client(store)

    response = client.post("/assessment/express-run/express_run_status_hardening/status")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "interrupted"
    assert detail["code"] == "express_worker_start_timeout"
    assert detail["progress_percent"] == 100
    assert detail["recovery_required"] is True
    retained = store.get("assessment_runs", record["run_id"])
    assert retained["response"]["code"] == "express_worker_start_timeout"


def test_express_status_wrong_scope_fails_as_not_found_not_validation_error(monkeypatch) -> None:
    store = MemoryAdapter()
    record = _express_record()
    store.put("assessment_runs", record["run_id"], record)
    monkeypatch.setattr(hardening, "STORE", store)
    client = _client(store)

    response = client.post(
        "/assessment/express-run/express_run_status_hardening/status",
        json={"customer_id": "wrong_customer", "project_id": "default_project"},
    )

    assert response.status_code == 404
    assert response.status_code != 422


def test_mid_live_status_returns_bounded_projection_instead_of_generic_500(monkeypatch) -> None:
    store = _mid_store()
    monkeypatch.setattr(hardening, "STORE", store)

    def fail_projection(*args, **kwargs):
        raise RuntimeError("internal projection failure")

    monkeypatch.setattr(hardening, "mid_live_status_response", fail_projection)
    app = FastAPI()
    app.add_api_route(
        hardening.MID_LIVE_STATUS_PATH,
        hardening.mid_live_status_endpoint,
        methods=["GET"],
    )
    client = TestClient(app)

    response = client.get(
        "/assessment/mid-run/midrun_status_hardening/live-status",
        params={"customer_id": "default_customer", "project_id": "default_project"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["code"] == "mid_live_status_projection_degraded"
    assert payload["live_status_degraded"] is True
    assert payload["scanner"]["active_tool"] == "trufflehog"
    assert payload["heartbeat_at"] == "2099-07-15T19:00:00Z"
    assert payload["progress_percent"] == 47
    assert payload["status_read_path"]["repository_recaptured"] is False


def test_route_installer_replaces_typed_express_status_and_mid_live_route_once(monkeypatch) -> None:
    store = MemoryAdapter()
    express = _express_record()
    store.put("assessment_runs", express["run_id"], express)
    monkeypatch.setattr(hardening, "STORE", store)
    app = FastAPI()

    def old_express_status(run_id: str, required_body: dict) -> dict:
        return {"run_id": run_id, **required_body}

    def old_mid_live(run_id: str) -> dict:
        return {"run_id": run_id}

    app.add_api_route(hardening.EXPRESS_STATUS_PATH, old_express_status, methods=["POST"])
    app.add_api_route(hardening.MID_LIVE_STATUS_PATH, old_mid_live, methods=["GET"])

    installed = hardening.install_lifecycle_status_hardening(app)
    client = TestClient(app)
    response = client.post("/assessment/express-run/express_run_status_hardening/status")
    express_routes = [
        route for route in app.routes
        if getattr(route, "path", "") == hardening.EXPRESS_STATUS_PATH
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    mid_routes = [
        route for route in app.routes
        if getattr(route, "path", "") == hardening.MID_LIVE_STATUS_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert installed["express_request_validation_422_possible"] is False
    assert installed["express_worker_start_handshake"] is True
    assert installed["express_scanner_projection_preserved"] is True
    assert installed["express_final_report_payload_preserved"] is True
    assert installed["mid_generic_http_500_possible"] is False
    assert response.status_code == 200
    assert len(express_routes) == 1
    assert len(mid_routes) == 1
