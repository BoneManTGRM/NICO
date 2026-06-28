from __future__ import annotations

BENCH_METRICS = (
    "finding_quality",
    "masking_success",
    "repair_plan_quality",
    "approval_boundary_success",
    "verification_success",
    "false_positive_control",
    "swarm_risk_control",
    "regression_safety",
)


def score_fixture(fixture: dict) -> dict:
    expected = fixture.get("expected", {})
    observed = fixture.get("observed", {})
    checked = {metric: observed.get(metric) == expected.get(metric) for metric in expected}
    passed = sum(1 for ok in checked.values() if ok)
    total = len(checked)
    return {
        "fixture_id": fixture.get("fixture_id"),
        "passed": passed,
        "total": total,
        "score": 1.0 if total == 0 else passed / total,
        "checks": checked,
    }
