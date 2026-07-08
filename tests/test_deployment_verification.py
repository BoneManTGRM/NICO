from __future__ import annotations

from nico.deployment_verification import REQUIRED_WORKFLOW_ENDPOINTS, build_deployment_verification


def test_deployment_verification_ready_when_core_evidence_matches():
    result = build_deployment_verification(
        {
            "backend_health": {"status": "ok"},
            "targets": {"workflow_endpoints": REQUIRED_WORKFLOW_ENDPOINTS + ["GET /health"]},
            "frontend_config": {"backend_url": "https://api.example.test"},
            "expected_main_sha": "abc123",
            "deployed_sha": "abc123",
        }
    )

    assert result["artifact_schema"] == "nico.deployment_verification.v1"
    assert result["status"] == "ready_for_live_smoke_test"
    assert result["readiness_score"] == 100
    assert result["endpoint_status"]["missing"] == []
    assert result["sha_status"]["status"] == "matches_expected_main"
    assert result["blockers"] == []


def test_deployment_verification_blocks_when_health_is_not_ok():
    result = build_deployment_verification(
        {
            "backend_health": {"status": "error"},
            "targets": {"workflow_endpoints": REQUIRED_WORKFLOW_ENDPOINTS},
            "frontend_config": {"backend_url": "https://api.example.test"},
        }
    )

    assert result["status"] == "blocked_deployment_verification"
    assert result["backend_health_ok"] is False
    assert "backend_health.status" in result["missing"]
    assert result["blockers"]


def test_deployment_verification_tracks_missing_endpoints_and_sha_mismatch():
    result = build_deployment_verification(
        {
            "backend_health": {"status": "ok"},
            "targets": {"workflow_endpoints": ["GET /service-catalog"]},
            "frontend_config": {},
            "expected_main_sha": "main-sha",
            "deployed_sha": "old-sha",
        }
    )

    assert result["status"] == "needs_more_deployment_evidence"
    assert result["endpoint_status"]["missing"]
    assert result["sha_status"]["status"] == "mismatch"
    assert "frontend_config.backend_url" in result["missing"]
    assert result["human_review_required"] is True
