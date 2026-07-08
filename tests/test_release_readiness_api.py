from __future__ import annotations

from fastapi import FastAPI

from nico.release_readiness_api import ReleaseReadinessRequest, register_release_readiness_routes, release_readiness_response


def test_release_readiness_api_registers_route():
    app = FastAPI()
    register_release_readiness_routes(app)

    assert "/release/readiness" in {route.path for route in app.routes}


def test_release_readiness_api_returns_artifact_for_empty_payload():
    result = release_readiness_response(ReleaseReadinessRequest(payload={}))

    assert result["artifact_schema"] == "nico.deployment_verification.v1"
    assert result["human_review_required"] is True
