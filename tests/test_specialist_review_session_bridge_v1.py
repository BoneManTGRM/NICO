from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import comprehensive_api_routes as routes
from nico.specialist_access_v1 import (
    PRODUCTION_PROOF_SCOPE,
    install_specialist_access,
    issue_specialist_session,
)
from nico.specialist_review_session_bridge_v1 import (
    install_specialist_review_session_bridge,
)


def _proof_claims() -> dict[str, str]:
    return {
        "repository": "BoneManTGRM/NICO",
        "repository_id": "1282576027",
        "release_sha": "a" * 40,
        "workflow_ref": "BoneManTGRM/NICO/.github/workflows/spanish-comprehensive-production-proof.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "workflow_file": ".github/workflows/spanish-comprehensive-production-proof.yml",
        "run_id": "123456789",
        "run_attempt": "1",
    }


def test_signed_specialist_session_reaches_review_but_proof_session_cannot(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "review-session-bridge-test-signing-secret",
    )
    original = routes.require_comprehensive_operator
    prior_v1 = getattr(routes, "_nico_specialist_review_session_bridge_v1", False)
    prior_v2 = getattr(routes, "_nico_specialist_review_session_bridge_v2", False)
    try:
        app = FastAPI()

        @app.post("/assessment/comprehensive-run/{run_id}/review")
        def review(run_id: str) -> dict[str, object]:
            allowed, authority = routes.require_comprehensive_operator("")
            return {
                "allowed": allowed,
                "authority": authority.get("authority"),
                "run_id": run_id,
            }

        install_specialist_access(app)
        installed = install_specialist_review_session_bridge(app)
        assert installed["request_context_isolated"] is True
        assert installed["specialist_scope_required"] is True
        assert installed["production_proof_scope_rejected"] is True

        specialist_token, _ = issue_specialist_session(
            {"authority": "nico_comprehensive_operator"}
        )
        proof_token, _ = issue_specialist_session(
            {"authority": "github_actions_production_proof"},
            scope=PRODUCTION_PROOF_SCOPE,
            retained_claims=_proof_claims(),
        )
        client = TestClient(app)
        blocked = client.post("/assessment/comprehensive-run/run-1/review")
        assert blocked.status_code == 401

        accepted = client.post(
            "/assessment/comprehensive-run/run-1/review",
            headers={"X-NICO-Operator-Session": specialist_token},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {
            "allowed": True,
            "authority": "nico_comprehensive_operator",
            "run_id": "run-1",
        }

        proof_blocked = client.post(
            "/assessment/comprehensive-run/run-1/review",
            headers={"X-NICO-Operator-Session": proof_token},
        )
        assert proof_blocked.status_code == 403
        assert proof_blocked.json()["detail"]["code"] == "production_proof_session_scope_forbidden"
    finally:
        routes.require_comprehensive_operator = original
        routes._nico_specialist_review_session_bridge_v1 = prior_v1
        routes._nico_specialist_review_session_bridge_v2 = prior_v2
