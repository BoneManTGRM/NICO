from __future__ import annotations

from fastapi import FastAPI

from nico.workflow_preflight_api import (
    WorkflowPreflightBatchRequest,
    WorkflowPreflightRequest,
    register_workflow_preflight_routes,
    workflow_preflight_batch_response,
    workflow_preflight_response,
)


def _comprehensive_payload():
    return {
        "workflow": "comprehensive",
        "repository": "owner/repo",
        "authorized": True,
        "authorized_by": "reviewer",
        "authorization_scope": "repository assessment only",
        "qa_evidence": "PASS login works",
        "parity_notes": "same labels",
        "stakeholder_notes": "goal launch",
        "roadmap_notes": "month 1",
        "known_risks": "none",
    }


def test_workflow_preflight_api_registers_routes():
    app = FastAPI()
    register_workflow_preflight_routes(app)

    paths = {route.path for route in app.routes}
    assert "/workflow/preflight" in paths
    assert "/workflow/preflight/batch" in paths


def test_workflow_preflight_api_returns_single_preflight():
    result = workflow_preflight_response(WorkflowPreflightRequest(payload=_comprehensive_payload()))

    assert result["artifact_schema"] == "nico.workflow_preflight.v2"
    assert result["status"] == "ready_to_submit"
    assert result["allowed_to_run"] is True
    assert result["recommended_workflow"] == "comprehensive"
    assert result["target_endpoint"] == "POST /assessment/mid-run"


def test_workflow_preflight_api_returns_batch_preflight():
    result = workflow_preflight_batch_response(
        WorkflowPreflightBatchRequest(
            payloads=[
                _comprehensive_payload(),
                {
                    "workflow": "express",
                    "repository": "owner/repo",
                    "authorized": False,
                },
            ]
        )
    )

    assert result["artifact_schema"] == "nico.workflow_preflight_batch.v2"
    assert result["count"] == 2
    assert result["ready_count"] == 1
    assert result["blocked_count"] == 1
