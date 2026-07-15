from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.mid_live_status_api as live
from nico.storage import MemoryAdapter


def _assessment_record() -> dict:
    return {
        "run_id": "midrun_live_status_test",
        "workflow": "mid_assessment",
        "status": "running",
        "repository": "owner/repository",
        "customer_id": "customer_live",
        "project_id": "project_live",
        "scan_id": "scan_snapshot_live_status",
        "request": {
            "repository": "owner/repository",
            "customer_id": "customer_live",
            "project_id": "project_live",
            "scan_id": "scan_snapshot_live_status",
        },
        "response": {
            "status": "running",
            "run_id": "midrun_live_status_test",
            "repository": "owner/repository",
            "customer_id": "customer_live",
            "project_id": "project_live",
            "assessment_type": "mid",
            "service_tier": "mid",
            "report_generation_status": "mid_report_generation_pending",
            "progress": [
                {"step": "repo_evidence", "status": "complete", "message": "Repository evidence attached."},
                {"step": "scanner_worker", "status": "running", "message": "Scanner running."},
                {"step": "evidence_attachment", "status": "pending", "message": "Waiting for scanner."},
            ],
            "human_review_required": True,
            "client_ready": False,
        },
    }


def _scanner_record(status: str = "running") -> dict:
    return {
        "scan_id": "scan_snapshot_live_status",
        "run_id": "midrun_live_status_test",
        "repository": "owner/repository",
        "customer_id": "customer_live",
        "project_id": "project_live",
        "status": status,
        "current_stage": "scanner_suite",
        "progress_percent": 67 if status == "running" else 100,
        "active_tool": "trufflehog" if status == "running" else "",
        "tools_requested": ["pip-audit", "bandit", "gitleaks", "trufflehog"],
        "tools_run": ["pip-audit", "bandit", "gitleaks"],
        "snapshot_id": "snapshot_live_status",
        "snapshot_commit_sha": "a" * 40,
        "created_at": "2026-07-15T22:00:00Z",
        "updated_at": "2026-07-15T22:05:00Z",
    }


def _store() -> MemoryAdapter:
    store = MemoryAdapter()
    assessment = _assessment_record()
    scanner = _scanner_record()
    store.put("assessment_runs", assessment["run_id"], assessment)
    store.put("scanner_runs", scanner["scan_id"], scanner)
    return store


def test_live_status_reads_retained_records_without_canonical_orchestration(monkeypatch) -> None:
    store = _store()
    monkeypatch.setattr(live, "STORE", store)
    monkeypatch.setattr(live, "scanner_is_stale", lambda _scan: False)

    result = live.mid_live_status_response(
        "midrun_live_status_test",
        customer_id="customer_live",
        project_id="project_live",
    )

    assert result["status"] == "running"
    assert result["run_id"] == "midrun_live_status_test"
    assert result["scanner"]["status"] == "running"
    assert result["scanner"]["active_tool"] == "trufflehog"
    assert result["scanner_progress_percent"] == 67
    assert result["progress_percent"] == 47
    assert result["continuation_required"] is False
    assert result["status_read_path"]["mode"] == "durable_live_status"
    assert result["status_read_path"]["orchestrator_reentered"] is False
    assert result["status_read_path"]["repository_recaptured"] is False
    assert result["status_read_path"]["assessment_run_rewritten"] is False


def test_terminal_scanner_requests_one_canonical_continuation(monkeypatch) -> None:
    store = _store()
    scanner = _scanner_record("complete")
    store.put("scanner_runs", scanner["scan_id"], scanner)
    monkeypatch.setattr(live, "STORE", store)

    result = live.mid_live_status_response(
        "midrun_live_status_test",
        customer_id="customer_live",
        project_id="project_live",
    )

    assert result["status"] == "running"
    assert result["continuation_required"] is True
    assert result["current_stage"] == "scanner_reconciliation"
    assert result["progress_percent"] >= 62
    assert result["status_read_path"]["mode"] == "terminal_scanner_handoff"


def test_stale_scanner_is_atomically_marked_recovery_required(monkeypatch) -> None:
    store = _store()
    monkeypatch.setattr(live, "STORE", store)
    monkeypatch.setattr(live, "scanner_is_stale", lambda _scan: True)
    monkeypatch.setattr(live, "scanner_age_seconds", lambda _scan: 901.0)

    result = live.mid_live_status_response(
        "midrun_live_status_test",
        customer_id="customer_live",
        project_id="project_live",
    )

    durable = store.get("scanner_runs", "scan_snapshot_live_status")
    assert durable["status"] == "recovery_required"
    assert result["status"] == "interrupted"
    assert result["recovery_required"] is True
    assert result["recovery_path"] == "/operations/recovery"
    assert result["continuation_required"] is False


def test_live_status_route_is_registered_once() -> None:
    app = FastAPI()
    first = live.register_mid_live_status_routes(app)
    second = live.register_mid_live_status_routes(app)
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "") == live.MID_LIVE_STATUS_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert first["route_count"] == 1
    assert second["route_count"] == 1
    assert len(routes) == 1


def test_live_status_http_contract_is_get_and_scope_bound(monkeypatch) -> None:
    store = _store()
    monkeypatch.setattr(live, "STORE", store)
    monkeypatch.setattr(live, "scanner_is_stale", lambda _scan: False)
    app = FastAPI()
    live.register_mid_live_status_routes(app)
    client = TestClient(app)

    response = client.get(
        "/assessment/mid-run/midrun_live_status_test/live-status",
        params={"customer_id": "customer_live", "project_id": "project_live"},
    )
    wrong_scope = client.get(
        "/assessment/mid-run/midrun_live_status_test/live-status",
        params={"customer_id": "other_customer", "project_id": "project_live"},
    )

    assert response.status_code == 200
    assert response.json()["status_read_path"]["mode"] == "durable_live_status"
    assert wrong_scope.status_code == 404
