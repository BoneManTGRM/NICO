from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.operational_observability as observability
from nico.operational_observability import (
    CORRELATION_HEADER,
    OPERATIONAL_EVENT_SCHEMA,
    OPERATIONS_OBSERVABILITY_ROUTES,
    REQUIRED_OPERATION_ROUTE_STRINGS,
    build_operational_observability,
    classify_http_outcome,
    classify_http_severity,
    extract_operational_identifiers,
    install_operational_observability,
    normalize_correlation_id,
    recent_operational_events,
    redact_operational_value,
    valid_correlation_id,
)
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


def _route_pairs(app: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), str(getattr(route, "path", ""))))
    return pairs


def test_correlation_validation_and_generation_are_bounded() -> None:
    supplied = "trace-12345678"
    assert valid_correlation_id(supplied)
    assert normalize_correlation_id(supplied) == supplied

    generated = normalize_correlation_id("bad value with spaces")
    assert generated.startswith("corr_")
    assert len(generated) == 37
    assert valid_correlation_id(generated)

    oversized = normalize_correlation_id("a" * 200)
    assert oversized.startswith("corr_")
    assert oversized != "a" * 200


def test_redaction_removes_secret_bearing_keys_and_auth_strings() -> None:
    payload = {
        "authorization": "Bearer top-secret",
        "cookie": "session=hidden",
        "nested": {
            "api_key": "provider-secret",
            "password": "password-value",
            "note": "Basic abc123",
            "safe": "retained",
        },
        "items": [{"token": "hidden"}, {"value": "visible"}],
    }

    redacted = redact_operational_value(payload)
    rendered = repr(redacted)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["note"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "retained"
    assert "top-secret" not in rendered
    assert "provider-secret" not in rendered
    assert "password-value" not in rendered


def test_http_classification_keeps_expected_blockers_distinct() -> None:
    assert classify_http_severity(200) == "info"
    assert classify_http_severity(404) == "p3"
    assert classify_http_severity(429) == "p2"
    assert classify_http_severity(503) == "p2"
    assert classify_http_severity(500) == "p1"
    assert classify_http_severity(200, unhandled_exception=True) == "p1"

    assert classify_http_outcome(200) == "succeeded"
    assert classify_http_outcome(404) == "client_error"
    assert classify_http_outcome(429) == "limited"
    assert classify_http_outcome(503) == "server_error"
    assert classify_http_outcome(200, unhandled_exception=True) == "exception"


def test_identifier_extraction_is_allowlisted_deduplicated_and_bounded() -> None:
    path = (
        "/assessment/midrun_123456789abc/report/approval_abcdef123456/"
        "scan_123456789abc?token=not-an-identifier&repeat=midrun_123456789abc"
    )
    identifiers = extract_operational_identifiers(path)

    assert identifiers == [
        "midrun_123456789abc",
        "approval_abcdef123456",
        "scan_123456789abc",
    ]
    assert all("token" not in item for item in identifiers)


def test_middleware_propagates_correlation_and_persists_safe_request_event() -> None:
    app = FastAPI()
    install_operational_observability(app)

    @app.post("/work/{run_id}")
    def work(run_id: str) -> dict[str, str]:
        return {"run_id": run_id}

    correlation_id = "trace-12345678"
    run_id = "midrun_123456789abc"
    client = TestClient(app)
    response = client.post(
        f"/work/{run_id}?token=query-secret",
        headers={
            CORRELATION_HEADER: correlation_id,
            "Authorization": "Bearer header-secret",
            "Cookie": "session=cookie-secret",
        },
        json={"password": "body-secret"},
    )

    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER] == correlation_id

    events = recent_operational_events(limit=10, correlation_id=correlation_id)
    assert events
    event = events[0]
    assert event["artifact_schema"] == OPERATIONAL_EVENT_SCHEMA
    assert event["event_name"] == "http.request.completed"
    assert event["outcome"] == "succeeded"
    assert event["metadata"]["route"] == "/work/{run_id}"
    assert event["metadata"]["status_code"] == 200
    assert event["metadata"]["identifiers"] == [run_id]

    rendered = repr(event)
    assert "query-secret" not in rendered
    assert "header-secret" not in rendered
    assert "cookie-secret" not in rendered
    assert "body-secret" not in rendered
    assert "Authorization" not in rendered
    assert "Cookie" not in rendered


def test_middleware_returns_generic_correlated_500_without_raw_exception() -> None:
    app = FastAPI()
    install_operational_observability(app)

    @app.get("/explode/{scan_id}")
    def explode(scan_id: str) -> dict[str, str]:
        raise RuntimeError("raw secret failure detail must never be retained")

    correlation_id = "failure-12345678"
    client = TestClient(app)
    response = client.get(
        "/explode/scan_123456789abc",
        headers={CORRELATION_HEADER: correlation_id},
    )

    assert response.status_code == 500
    assert response.headers[CORRELATION_HEADER] == correlation_id
    assert response.json() == {
        "status": "error",
        "code": "internal_server_error",
        "message": "The request failed inside the production service.",
        "correlation_id": correlation_id,
    }

    events = recent_operational_events(limit=10, correlation_id=correlation_id)
    assert events
    event = events[0]
    assert event["event_name"] == "http.request.failed"
    assert event["severity"] == "p1"
    assert event["outcome"] == "exception"
    assert event["metadata"]["error_class"] == "RuntimeError"
    assert "raw secret failure detail" not in repr(event)


def test_admin_event_endpoints_require_auth_and_apply_bounded_filters(monkeypatch) -> None:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    app = FastAPI()
    install_operational_observability(app)
    client = TestClient(app)

    denied = client.get("/operations/events")
    assert denied.status_code == 403
    assert denied.headers.get(CORRELATION_HEADER)

    allowed = client.get(
        "/operations/events?limit=5&severity=info",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["artifact_schema"] == "nico.operational_events.v1"
    assert payload["limit"] == 5
    assert payload["filters"]["severity"] == "info"
    assert len(payload["events"]) <= 5
    assert allowed.headers.get(CORRELATION_HEADER)

    invalid = client.get(
        "/operations/events?correlation_id=contains%20spaces",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert invalid.status_code == 400

    oversized = client.get(
        "/operations/events?limit=501",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert oversized.status_code == 422


class _FakeStore:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.adapter = None

    def list(
        self,
        table: str,
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self.tables.get(table, []))
        if customer_id:
            items = [item for item in items if item.get("customer_id") == customer_id]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        return items

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "postgres",
            "persistence_available": True,
            "database_url_configured": True,
        }

    def audit(
        self,
        action: str,
        payload: dict[str, Any],
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "action": action,
            "payload": payload,
            "customer_id": customer_id,
            "project_id": project_id,
            "created_at": payload.get("occurred_at"),
        }
        self.tables.setdefault("audit_log", []).append(record)
        return record


def _event(
    event_id: str,
    *,
    status_code: int,
    duration_ms: float,
    severity: str,
    outcome: str,
    occurred_at: str,
) -> dict[str, Any]:
    return {
        "action": "operational_event",
        "created_at": occurred_at,
        "payload": {
            "artifact_schema": OPERATIONAL_EVENT_SCHEMA,
            "event_id": event_id,
            "correlation_id": f"corr_{event_id}_12345678",
            "event_name": "http.request.completed",
            "severity": severity,
            "outcome": outcome,
            "metadata": {
                "method": "GET",
                "route": "/test",
                "status_code": status_code,
                "duration_ms": duration_ms,
                "identifiers": [],
            },
            "occurred_at": occurred_at,
        },
    }


def test_observability_summary_tracks_failures_latency_queue_and_workload_duration(monkeypatch) -> None:
    base = datetime(2026, 7, 12, 17, 0, tzinfo=timezone.utc)
    timestamp = lambda seconds: (base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    fake_store = _FakeStore(
        {
            "audit_log": [
                _event("one", status_code=200, duration_ms=10, severity="info", outcome="succeeded", occurred_at=timestamp(1)),
                _event("two", status_code=200, duration_ms=30, severity="info", outcome="succeeded", occurred_at=timestamp(2)),
                _event("three", status_code=500, duration_ms=100, severity="p1", outcome="server_error", occurred_at=timestamp(3)),
                _event("four", status_code=504, duration_ms=200, severity="p2", outcome="server_error", occurred_at=timestamp(4)),
            ],
            "assessment_runs": [
                {
                    "run_id": "midrun_completed123",
                    "status": "completed",
                    "created_at": timestamp(0),
                },
                {
                    "run_id": "midrun_queued12345",
                    "status": "queued",
                    "created_at": timestamp(10),
                },
            ],
            "scanner_runs": [
                {
                    "scan_id": "scan_complete1234",
                    "status": "completed",
                    "created_at": timestamp(0),
                    "updated_at": timestamp(60),
                },
                {
                    "scan_id": "scan_running1234",
                    "status": "running",
                    "created_at": timestamp(20),
                    "updated_at": timestamp(30),
                },
            ],
            "reports": [
                {
                    "report_id": "report_12345678",
                    "run_id": "midrun_completed123",
                    "created_at": timestamp(30),
                }
            ],
        }
    )
    monkeypatch.setattr(observability, "STORE", fake_store)
    monkeypatch.setattr(observability, "_now", lambda: base + timedelta(seconds=600))
    monkeypatch.setattr(
        observability,
        "deployment_diagnostics",
        lambda: {
            "status": "ok",
            "deployed_commit": "a" * 40,
            "matches_expected_build": True,
            "build_marker": "test-build",
        },
    )
    monkeypatch.setattr(
        observability,
        "build_operations_readiness",
        lambda routes: {
            "status": "ready",
            "operational_ready": True,
            "blockers": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(observability, "_EVENT_WRITE_FAILURES", 0)
    monkeypatch.setattr(observability, "_EVENT_READ_FAILURES", 0)

    app = FastAPI()
    result = build_operational_observability(app, event_window=10)

    assert result["artifact_schema"] == "nico.operational_observability.v1"
    assert result["status"] == "ok"
    assert result["request_metrics"]["request_count"] == 4
    assert result["request_metrics"]["failure_count"] == 2
    assert result["request_metrics"]["failure_rate"] == 0.5
    assert result["request_metrics"]["timeout_count"] == 1
    assert result["request_metrics"]["timeout_rate"] == 0.25
    assert result["request_metrics"]["latency_ms"]["p50"] == 65.0
    assert result["request_metrics"]["latency_ms"]["p95"] == 185.0
    assert result["workloads"]["assessment_runs"]["queued"] == 1
    assert result["workloads"]["assessment_runs"]["oldest_queue_age_seconds"] == 590.0
    assert result["workloads"]["scanner_runs"]["active"] == 1
    assert result["workloads"]["scanner_duration_seconds"]["p50"] == 60.0
    assert result["workloads"]["report_generation_seconds"]["p50"] == 30.0
    assert result["storage"]["persistence_available"] is True
    assert result["semantic_readiness"]["operational_ready"] is True
    assert result["client_delivery_allowed"] is False


def test_installation_and_required_route_registration_are_idempotent() -> None:
    app = FastAPI()

    first = install_operational_observability(app)
    second = install_operational_observability(app)

    assert first["installed"] is True
    assert first["middleware_reused"] is False
    assert second["middleware_reused"] is True
    assert OPERATIONS_OBSERVABILITY_ROUTES <= _route_pairs(app)
    assert REQUIRED_OPERATION_ROUTE_STRINGS <= REQUIRED_OPERATION_ROUTES
    for method, path in OPERATIONS_OBSERVABILITY_ROUTES:
        assert sum(1 for pair in _route_pairs(app) if pair == (method, path)) == 1
