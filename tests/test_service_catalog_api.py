from __future__ import annotations

from fastapi import FastAPI, HTTPException

from nico.service_catalog_api import (
    ServiceIntakeRequest,
    register_service_catalog_routes,
    service_catalog_item_response,
    service_catalog_response,
    service_intake_readiness_response,
)


def test_service_catalog_api_registers_routes():
    app = FastAPI()
    register_service_catalog_routes(app)

    paths = {route.path for route in app.routes}
    assert "/service-catalog" in paths
    assert "/service-catalog/{workflow}" in paths
    assert "/service-catalog/intake-readiness" in paths


def test_service_catalog_api_returns_catalog():
    result = service_catalog_response()

    assert result["status"] == "ok"
    assert result["artifact_schema"] == "nico.service_catalog.v1"
    assert "express" in result["services"]
    assert "mid" in result["services"]
    assert "retainer" in result["services"]


def test_service_catalog_api_returns_item_or_404():
    result = service_catalog_item_response("express")
    assert result["status"] == "ok"
    assert result["workflow"] == "express"

    try:
        service_catalog_item_response("unknown")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail["status"] == "not_found"
    else:
        raise AssertionError("Expected HTTPException for unknown workflow")


def test_service_catalog_api_returns_intake_readiness():
    result = service_intake_readiness_response(
        ServiceIntakeRequest(
            payload={
                "qa_evidence": "PASS login works",
                "parity_notes": "iOS and Android copy matches",
                "stakeholder_notes": "Goal is launch faster",
                "roadmap_notes": "Month 1 stabilize QA",
                "known_risks": "No known launch blocker",
            }
        )
    )

    assert result["artifact_schema"] == "nico.service_intake_readiness.v1"
    assert result["recommended_workflow"] == "mid"
    assert result["status"] == "ready_for_workflow_request"
