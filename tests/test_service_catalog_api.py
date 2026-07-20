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


def test_service_catalog_api_returns_only_express_and_comprehensive_assessments():
    result = service_catalog_response()

    assert result["status"] == "ok"
    assert result["artifact_schema"] == "nico.service_catalog.v2"
    assert set(result["services"]) == {"express", "comprehensive"}
    assert result["customer_assessment_count"] == 2
    assert "monitor_execute" in result["recurring_services"]


def test_service_catalog_api_returns_item_or_404():
    result = service_catalog_item_response("express")
    assert result["status"] == "ok"
    assert result["workflow"] == "express"

    alias = service_catalog_item_response("full")
    assert alias["workflow"] == "comprehensive"
    assert alias["internal_execution_profile"] == "full"

    try:
        service_catalog_item_response("unknown")
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail["status"] == "not_found"
    else:
        raise AssertionError("Expected HTTPException for unknown workflow")


def test_service_catalog_api_returns_comprehensive_intake_readiness():
    result = service_intake_readiness_response(
        ServiceIntakeRequest(
            payload={
                "workflow": "comprehensive",
                "repository": "BoneManTGRM/NICO",
                "authorized": True,
                "authorized_by": "reviewer",
                "authorization_scope": "repository assessment only",
                "qa_evidence": "PASS login works",
                "parity_notes": "iOS and Android copy matches",
                "stakeholder_notes": "Goal is launch faster",
                "roadmap_notes": "Month 1 stabilize QA",
                "known_risks": "No known launch blocker",
            }
        )
    )

    assert result["artifact_schema"] == "nico.service_intake_readiness.v2"
    assert result["recommended_workflow"] == "comprehensive"
    assert result["status"] == "ready_for_workflow_request"
