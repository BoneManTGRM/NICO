from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import comprehensive_api_routes as routes
from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session
from nico.specialist_review_session_bridge_v1 import (
    install_specialist_review_session_bridge,
)


def test_signed_session_reaches_protected_review_authority(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "review-session-bridge-test-signing-secret",
    )
    original = routes.require_comprehensive_operator
    prior_flag = getattr(routes, "_nico_specialist_review_session_bridge_v1", False)
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

        token, _ = issue_specialist_session(
            {"authority": "nico_comprehensive_operator"}
        )
        client = TestClient(app)
        blocked = client.post("/assessment/comprehensive-run/run-1/review")
        assert blocked.status_code == 401

        accepted = client.post(
            "/assessment/comprehensive-run/run-1/review",
            headers={"X-NICO-Operator-Session": token},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {
            "allowed": True,
            "authority": "nico_comprehensive_operator",
            "run_id": "run-1",
        }
    finally:
        routes.require_comprehensive_operator = original
        routes._nico_specialist_review_session_bridge_v1 = prior_flag
