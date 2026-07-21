from __future__ import annotations

from nico.post_release_observability import (
    MetricPoint,
    OperationalThresholds,
    alert_conditions,
    build_health_snapshot,
    redact_log_text,
    verify_log_redaction,
)


def _points(**overrides):
    values = {
        "storage_available": 1,
        "storage_latency_ms": 40,
        "queue_depth": 2,
        "provider_collection_failures": 0,
        "report_generation_failures": 0,
        "delivery_gate_blocks": 3,
        "delivery_failures": 0,
        "active_runs": 1,
        "stale_runs": 0,
    }
    values.update(overrides)
    return tuple(
        MetricPoint(name=key, value=float(value), timestamp="2026-07-21T00:00:00Z")
        for key, value in values.items()
    )


def test_healthy_snapshot_has_complete_digest_and_no_alerts() -> None:
    snapshot = build_health_snapshot(
        exact_sha="a" * 40,
        points=_points(),
        log_samples=("request complete", "Authorization: Bearer secret"),
        forbidden_log_values=("secret",),
        captured_at="2026-07-21T00:00:00Z",
    )
    assert snapshot.status == "healthy"
    assert snapshot.issues == ()
    assert snapshot.log_redaction_verified is True
    assert snapshot.metrics_digest.startswith("sha256:")
    assert alert_conditions(snapshot) == ()


def test_degraded_metrics_emit_actionable_alerts() -> None:
    snapshot = build_health_snapshot(
        exact_sha="a" * 40,
        points=_points(
            storage_available=0,
            storage_latency_ms=900,
            queue_depth=200,
            provider_collection_failures=7,
            report_generation_failures=2,
            delivery_failures=2,
            stale_runs=1,
        ),
        log_samples=("safe",),
        thresholds=OperationalThresholds(),
    )
    assert snapshot.status == "degraded"
    assert "storage_unavailable" in snapshot.issues
    assert "queue_depth_exceeded" in snapshot.issues
    alerts = alert_conditions(snapshot)
    assert any(item["alert_key"] == "operational:storage_unavailable" for item in alerts)
    assert any(item["severity"] == "critical" for item in alerts)


def test_missing_metrics_fail_closed() -> None:
    snapshot = build_health_snapshot(
        exact_sha="a" * 40,
        points=(MetricPoint("storage_available", 1, "2026-07-21T00:00:00Z"),),
        log_samples=(),
    )
    assert snapshot.status == "degraded"
    assert "metric_missing:queue_depth" in snapshot.issues


def test_log_redaction_covers_provider_and_database_secrets() -> None:
    sample = "Authorization: Bearer abc PRIVATE-TOKEN=def database_url=postgres://user:pass@host/db"
    redacted = redact_log_text(sample)
    assert "abc" not in redacted
    assert "def" not in redacted
    assert "postgres://" not in redacted
    assert redacted.count("<redacted>") >= 3
    assert verify_log_redaction((sample,), forbidden_values=("abc", "def", "postgres://")) is True
