from __future__ import annotations

from fastapi import FastAPI

from nico.hosted_smoke_test_api import HostedSmokeTestRequest, hosted_smoke_test_response, register_hosted_smoke_test_routes


def test_hosted_smoke_test_api_registers_route():
    app = FastAPI()
    register_hosted_smoke_test_routes(app)

    assert "/hosted/smoke-test" in {route.path for route in app.routes}


def test_hosted_smoke_test_api_returns_artifact():
    result = hosted_smoke_test_response(HostedSmokeTestRequest(payload={"evidence": {}}))

    assert result["artifact_schema"] == "nico.hosted_smoke_test.v1"
    assert result["status"] == "incomplete_smoke_test"
    assert result["human_review_required"] is True
