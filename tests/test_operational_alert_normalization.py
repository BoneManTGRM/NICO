from __future__ import annotations

from nico.operational_alert_normalization import (
    evaluate_operational_alerts,
    install_operational_alert_normalization,
)
from nico.operations_readiness import REQUIRED_OPERATION_ROUTES


SHA = "a" * 40


def _payload(severity_counts: dict) -> dict:
    return {
        "request_metrics": {
            "request_count": 1,
            "failure_count": 0,
            "failure_rate": 0.0,
            "timeout_count": 0,
            "timeout_rate": 0.0,
            "severity_counts": severity_counts,
        },
        "workloads": {
            "assessment_runs": {"queued": 0, "active": 0, "total": 0, "oldest_queue_age_seconds": 0.0},
            "scanner_runs": {"queued": 0, "active": 0, "total": 0, "oldest_queue_age_seconds": 0.0},
        },
        "event_pipeline": {"status": "ok", "write_failures": 0, "read_failures": 0, "durability": "durable"},
        "storage": {"persistence_available": True, "adapter": "postgres", "database_configured": True},
        "deployment": {"deployed_commit": SHA, "status": "ok", "matches_expected_build": True},
        "semantic_readiness": {"status": "ready", "operational_ready": True, "blockers": [], "warnings": []},
    }


def test_absent_severity_keys_in_a_present_counter_mean_zero_not_unavailable() -> None:
    result = evaluate_operational_alerts(_payload({"info": 1}), frontend_commit=SHA)
    codes = {item["code"] for item in result["alerts"]}

    assert "incident_severity_counts_unavailable" not in codes
    assert result["status"] == "clear"


def test_missing_severity_counter_remains_unavailable() -> None:
    payload = _payload({"info": 1})
    payload["request_metrics"].pop("severity_counts")
    result = evaluate_operational_alerts(payload, frontend_commit=SHA)

    assert "incident_severity_counts_unavailable" in {item["code"] for item in result["alerts"]}


def test_normalization_install_is_idempotent_and_registers_readiness_requirement() -> None:
    first = install_operational_alert_normalization()
    second = install_operational_alert_normalization()

    assert first["installed"] is True
    assert second["installed"] is True
    assert second["idempotent_reuse"] is True
    assert "GET /operations/alerts" in REQUIRED_OPERATION_ROUTES
