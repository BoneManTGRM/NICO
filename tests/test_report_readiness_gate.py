from __future__ import annotations

from nico.deployment_verification import REQUIRED_WORKFLOW_ENDPOINTS
from nico.hosted_smoke_test import SMOKE_TESTS
from nico.report_readiness_gate import build_report_readiness_gate


def _ready_payload():
    smoke_evidence = {case["evidence_key"]: {"status": case.get("required_status") or "ok"} for case in SMOKE_TESTS}
    return {
        "deployment": {
            "backend_health": {"status": "ok"},
            "targets": {"workflow_endpoints": REQUIRED_WORKFLOW_ENDPOINTS},
            "frontend_config": {"backend_url": "https://api.example.test"},
            "expected_main_sha": "abc123",
            "deployed_sha": "abc123",
        },
        "smoke_test": {"evidence": smoke_evidence},
        "assessment_request": {
            "authorized": True,
            "repository": "owner/repo",
            "client_name": "Client",
        },
    }


def test_report_readiness_gate_allows_fresh_report_when_ready():
    result = build_report_readiness_gate(_ready_payload())

    assert result["artifact_schema"] == "nico.report_readiness_gate.v1"
    assert result["status"] == "ready_for_fresh_express_report"
    assert result["report_delivery_allowed"] is True
    assert result["missing"] == []
    assert result["blockers"] == []


def test_report_readiness_gate_blocks_without_authorization():
    payload = _ready_payload()
    payload["assessment_request"]["authorized"] = False

    result = build_report_readiness_gate(payload)

    assert result["status"] == "blocked_report_readiness"
    assert result["report_delivery_allowed"] is False
    assert "assessment_request.authorized" in result["missing"]
    assert any("authorization" in item for item in result["blockers"])


def test_report_readiness_gate_blocks_failed_smoke_test():
    payload = _ready_payload()
    payload["smoke_test"]["evidence"]["health"] = {"status": "error"}

    result = build_report_readiness_gate(payload)

    assert result["status"] == "blocked_report_readiness"
    assert result["hosted_smoke_test"]["status"] == "failed_smoke_test"
    assert "smoke_test:health" in result["blockers"]


def test_report_readiness_gate_tracks_missing_deployment_evidence():
    payload = _ready_payload()
    payload["deployment"]["frontend_config"] = {}

    result = build_report_readiness_gate(payload)

    assert result["report_delivery_allowed"] is False
    assert any(item.startswith("deployment:") for item in result["missing"])
