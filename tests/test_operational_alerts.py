from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.operational_alerts as operational_alerts
from nico.operational_alerts import (
    FAILURE_RATE_P1,
    FAILURE_RATE_P2,
    MIN_RATE_SAMPLE,
    OPERATIONS_ALERT_ROUTES,
    OPERATIONAL_ALERTS_SCHEMA,
    QUEUE_AGE_P1_SECONDS,
    QUEUE_AGE_P2_SECONDS,
    REQUIRED_OPERATION_ALERT_ROUTE,
    SCANNER_QUEUE_P1,
    SCANNER_QUEUE_P2,
    TIMEOUT_RATE_P1,
    TIMEOUT_RATE_P2,
    evaluate_operational_alerts,
    install_operational_alert_routes,
)
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


BACKEND_SHA = "a" * 40
FRONTEND_SHA = "a" * 40
OTHER_SHA = "b" * 40


def _observability() -> dict:
    return {
        "artifact_schema": "nico.operational_observability.v1",
        "status": "ok",
        "generated_at": "2026-07-12T19:45:00Z",
        "event_window": 500,
        "events_observed": 25,
        "request_metrics": {
            "request_count": 100,
            "failure_count": 0,
            "failure_rate": 0.0,
            "timeout_count": 0,
            "timeout_rate": 0.0,
            "latency_ms": {"p50": 10.0, "p95": 40.0, "max": 70.0},
            "severity_counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0, "info": 25},
        },
        "workloads": {
            "assessment_runs": {
                "total": 5,
                "active": 1,
                "queued": 0,
                "oldest_queue_age_seconds": 0.0,
                "status_counts": {"completed": 4, "running": 1},
            },
            "scanner_runs": {
                "total": 4,
                "active": 1,
                "queued": 0,
                "oldest_queue_age_seconds": 0.0,
                "status_counts": {"completed": 3, "running": 1},
            },
            "scanner_duration_seconds": {"sample_count": 3, "p50": 30.0, "p95": 55.0, "max": 60.0},
            "report_generation_seconds": {"sample_count": 3, "p50": 20.0, "p95": 35.0, "max": 40.0},
        },
        "event_pipeline": {
            "status": "ok",
            "write_failures": 0,
            "read_failures": 0,
            "storage_adapter": "postgres",
            "persistence_available": True,
            "durability": "durable",
        },
        "storage": {
            "adapter": "postgres",
            "persistence_available": True,
            "database_configured": True,
        },
        "deployment": {
            "status": "ok",
            "deployed_commit": BACKEND_SHA,
            "matches_expected_build": True,
            "build_marker": "production",
        },
        "semantic_readiness": {
            "status": "ready",
            "operational_ready": True,
            "blockers": [],
            "warnings": [],
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _codes(result: dict) -> set[str]:
    return {str(item.get("code")) for item in result.get("alerts", [])}


def test_healthy_exact_release_has_no_alerts_and_is_deterministic() -> None:
    first = evaluate_operational_alerts(_observability(), frontend_commit=FRONTEND_SHA)
    second = evaluate_operational_alerts(_observability(), frontend_commit=FRONTEND_SHA)

    assert first["artifact_schema"] == OPERATIONAL_ALERTS_SCHEMA
    assert first["status"] == "clear"
    assert first["alert_count"] == 0
    assert first["alerts"] == []
    assert first["highest_severity"] == "info"
    assert first["source_observability_sha256"] == second["source_observability_sha256"]
    assert first["alert_set_sha256"] == second["alert_set_sha256"]
    assert first["automatic_remediation_performed"] is False
    assert first["client_delivery_allowed"] is False


def test_p0_and_p1_events_are_alerted_without_auto_remediation() -> None:
    payload = _observability()
    payload["request_metrics"]["severity_counts"]["p0"] = 1
    payload["request_metrics"]["severity_counts"]["p1"] = 3

    result = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)

    assert result["highest_severity"] == "p0"
    assert {"p0_events_active", "p1_events_active"} <= _codes(result)
    assert all(item["auto_remediation_eligible"] is False for item in result["alerts"])
    assert all(item["destructive_action_allowed"] is False for item in result["alerts"])


@pytest.mark.parametrize(
    ("failure_rate", "expected_severity"),
    [
        (FAILURE_RATE_P2, "p2"),
        (FAILURE_RATE_P1, "p1"),
    ],
)
def test_failure_rate_thresholds_require_a_sufficient_sample(failure_rate: float, expected_severity: str) -> None:
    payload = _observability()
    payload["request_metrics"]["failure_rate"] = failure_rate
    payload["request_metrics"]["failure_count"] = int(payload["request_metrics"]["request_count"] * failure_rate)

    result = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    alert = next(item for item in result["alerts"] if item["code"] == "http_failure_rate_elevated")
    assert alert["severity"] == expected_severity

    payload["request_metrics"]["request_count"] = MIN_RATE_SAMPLE - 1
    payload["request_metrics"]["failure_count"] = MIN_RATE_SAMPLE - 1
    below_sample = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    assert "http_failure_rate_elevated" not in _codes(below_sample)


@pytest.mark.parametrize(
    ("timeout_rate", "expected_severity"),
    [
        (TIMEOUT_RATE_P2, "p2"),
        (TIMEOUT_RATE_P1, "p1"),
    ],
)
def test_timeout_rate_thresholds(timeout_rate: float, expected_severity: str) -> None:
    payload = _observability()
    payload["request_metrics"]["timeout_rate"] = timeout_rate
    payload["request_metrics"]["timeout_count"] = int(payload["request_metrics"]["request_count"] * timeout_rate)

    result = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    alert = next(item for item in result["alerts"] if item["code"] == "http_timeout_rate_elevated")
    assert alert["severity"] == expected_severity


@pytest.mark.parametrize(
    ("queue_age", "expected_severity"),
    [
        (QUEUE_AGE_P2_SECONDS, "p2"),
        (QUEUE_AGE_P1_SECONDS, "p1"),
    ],
)
def test_assessment_queue_age_thresholds(queue_age: float, expected_severity: str) -> None:
    payload = _observability()
    payload["workloads"]["assessment_runs"]["queued"] = 1
    payload["workloads"]["assessment_runs"]["oldest_queue_age_seconds"] = queue_age

    result = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    alert = next(item for item in result["alerts"] if item["code"] == "assessment_queue_age_elevated")
    assert alert["severity"] == expected_severity


@pytest.mark.parametrize(
    ("queued", "expected_severity"),
    [
        (SCANNER_QUEUE_P2, "p2"),
        (SCANNER_QUEUE_P1, "p1"),
    ],
)
def test_scanner_queue_thresholds(queued: int, expected_severity: str) -> None:
    payload = _observability()
    payload["workloads"]["scanner_runs"]["queued"] = queued

    result = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    alert = next(item for item in result["alerts"] if item["code"] == "scanner_queue_elevated")
    assert alert["severity"] == expected_severity


def test_pipeline_storage_readiness_and_release_mismatch_are_fail_closed() -> None:
    payload = _observability()
    payload["event_pipeline"]["write_failures"] = 2
    payload["event_pipeline"]["read_failures"] = 1
    payload["storage"]["persistence_available"] = False
    payload["storage"]["adapter"] = "memory"
    payload["semantic_readiness"] = {
        "status": "blocked",
        "operational_ready": False,
        "blockers": ["durable_storage"],
        "warnings": [],
    }

    result = evaluate_operational_alerts(payload, frontend_commit=OTHER_SHA)
    codes = _codes(result)

    assert {
        "event_pipeline_write_failures",
        "event_pipeline_read_failures",
        "durable_storage_unavailable",
        "semantic_readiness_blocked",
        "frontend_backend_release_mismatch",
    } <= codes
    assert result["highest_severity"] == "p1"


def test_missing_required_metrics_are_not_treated_as_clean() -> None:
    payload = _observability()
    payload["request_metrics"] = {}
    payload["workloads"] = {}
    payload["event_pipeline"] = {}
    payload["storage"] = {}
    payload["semantic_readiness"] = {}
    payload["deployment"] = {}

    result = evaluate_operational_alerts(payload, frontend_commit="")
    codes = _codes(result)

    assert {
        "incident_severity_counts_unavailable",
        "request_reliability_metrics_unavailable",
        "assessment_queue_age_unavailable",
        "scanner_queue_metrics_unavailable",
        "event_pipeline_metrics_unavailable",
        "durable_storage_unavailable",
        "semantic_readiness_blocked",
        "backend_release_identity_unavailable",
        "frontend_release_identity_unavailable",
    } <= codes
    assert all(item["status"] == "active" for item in result["alerts"])


def test_alert_identity_changes_only_when_alert_evidence_changes() -> None:
    payload = _observability()
    payload["request_metrics"]["failure_rate"] = FAILURE_RATE_P2
    payload["request_metrics"]["failure_count"] = 5

    first = evaluate_operational_alerts(payload, frontend_commit=FRONTEND_SHA)
    second = evaluate_operational_alerts(deepcopy(payload), frontend_commit=FRONTEND_SHA)
    changed_payload = deepcopy(payload)
    changed_payload["request_metrics"]["failure_rate"] = FAILURE_RATE_P1
    changed_payload["request_metrics"]["failure_count"] = 20
    changed = evaluate_operational_alerts(changed_payload, frontend_commit=FRONTEND_SHA)

    assert first["alert_set_sha256"] == second["alert_set_sha256"]
    assert first["alerts"][0]["alert_id"] == second["alerts"][0]["alert_id"]
    assert first["alert_set_sha256"] != changed["alert_set_sha256"]


def test_admin_endpoint_requires_auth_validates_commit_and_returns_bounded_result(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    monkeypatch.setattr(operational_alerts, "build_operational_observability", lambda app, event_window=500: _observability())
    app = FastAPI()
    install_operational_alert_routes(app)
    client = TestClient(app)

    denied = client.get("/operations/alerts")
    assert denied.status_code == 403

    invalid = client.get(
        "/operations/alerts?frontend_commit=short",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_frontend_commit"

    allowed = client.get(
        f"/operations/alerts?frontend_commit={FRONTEND_SHA}&event_window=100",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "clear"

    oversized = client.get(
        f"/operations/alerts?frontend_commit={FRONTEND_SHA}&event_window=2001",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert oversized.status_code == 422


def test_alert_route_registration_and_readiness_requirement_are_idempotent() -> None:
    app = FastAPI()
    first = install_operational_alert_routes(app)
    second = install_operational_alert_routes(app)

    route_pairs = {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert first["installed"] is True
    assert first["route_reused"] is False
    assert second["route_reused"] is True
    assert OPERATIONS_ALERT_ROUTES <= route_pairs
    assert REQUIRED_OPERATION_ALERT_ROUTE in REQUIRED_OPERATION_ROUTES
