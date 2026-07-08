from __future__ import annotations

from fastapi import FastAPI

from nico.report_readiness_attachment_api import (
    ReportReadinessAttachmentRequest,
    register_report_readiness_attachment_routes,
    report_readiness_attachment_response,
)


def test_report_readiness_attachment_api_registers_route():
    app = FastAPI()
    register_report_readiness_attachment_routes(app)

    assert "/reports/attach-readiness" in {route.path for route in app.routes}


def test_report_readiness_attachment_api_returns_attached_report():
    result = report_readiness_attachment_response(
        ReportReadinessAttachmentRequest(
            report={"run_id": "run-1"},
            readiness_gate={
                "status": "ready_for_fresh_express_report",
                "report_delivery_allowed": True,
                "missing": [],
                "blockers": [],
            },
        )
    )

    assert result["run_id"] == "run-1"
    assert result["delivery_readiness"]["status"] == "delivery_ready"
    assert result["report_readiness_gate"]["status"] == "ready_for_fresh_express_report"


def test_report_readiness_attachment_api_blocks_empty_gate():
    result = report_readiness_attachment_response(ReportReadinessAttachmentRequest(report={"run_id": "run-1"}))

    assert result["delivery_readiness"]["status"] == "delivery_blocked"
    assert result["report_readiness_gate"]["status"] == "missing_report_readiness_gate"
