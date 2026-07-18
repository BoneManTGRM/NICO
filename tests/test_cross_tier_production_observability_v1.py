from nico.cross_tier_production_observability_v1 import evaluate_production_observability

SHA = "a" * 40


def record(**overrides):
    value = {"commit_sha": SHA, "request_success_rate": 1.0, "status_lookup_success_rate": 1.0, "artifact_delivery_success_rate": 1.0, "p95_status_latency_ms": 500, "stuck_runs": 0, "orphaned_runs": 0, "cross_tier_mismatches": 0, "unhandled_errors": 0, "alerting_enabled": True, "dashboard_healthy": True}
    value.update(overrides)
    return value


def evidence():
    return {"express": record(), "mid": record(), "full": record()}


def test_healthy_release():
    assert evaluate_production_observability(evidence(), exact_sha=SHA)["release_allowed"] is True


def test_missing_and_unhealthy_signals_block():
    data = evidence()
    del data["mid"]
    data["express"] = record(status_lookup_success_rate=0.98, stuck_runs=1)
    data["full"] = record(commit_sha="b" * 40, p95_status_latency_ms=1501, alerting_enabled=False)
    result = evaluate_production_observability(data, exact_sha=SHA)
    assert result["release_allowed"] is False
    assert "mid:missing_observability" in result["failures"]
    assert "express:stuck_runs:nonzero" in result["failures"]
    assert "full:sha_mismatch" in result["failures"]
    assert "full:p95_status_latency_ms:limit_exceeded" in result["failures"]


def test_prior_block_is_preserved():
    result = evaluate_production_observability(evidence(), exact_sha=SHA, prior_release_allowed=False)
    assert "prior_release_block" in result["failures"]
