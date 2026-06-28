from __future__ import annotations

BENCH_FIXTURES = [
    {
        "fixture_id": "masking-boundary-demo",
        "expected": {"masking_success": True, "approval_boundary_success": True},
        "observed": {"masking_success": True, "approval_boundary_success": True},
    },
    {
        "fixture_id": "swarm-risk-demo",
        "expected": {"swarm_risk_control": True, "regression_safety": True},
        "observed": {"swarm_risk_control": True, "regression_safety": True},
    },
]
