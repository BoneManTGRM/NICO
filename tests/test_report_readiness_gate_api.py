from __future__ import annotations

from fastapi import FastAPI

from nico.report_readiness_gate_api import (
    ReportReadinessGateRequest,
    register_report_readiness_gate_routes,
    report_readiness_gate_response,
)


def test_report_readiness_gate_api_registers_route():
    app = FastAPI()
    register_report_readiness_gate_routes(app)

    assert "/reports/readiness-gate" in {route.path for route in app.routes}


def test_report_readiness_gate_api_returns_artifact():
    result = report_readiness_gate_response(ReportReadinessGateRequest(payload={}))

    assert result["artifact_schema"] == "nico.report_readiness_gate.v1"
    assert result["status"] == "blocked_report_readiness"
    assert result["human_review_required"] is True
