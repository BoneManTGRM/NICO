from __future__ import annotations

from fastapi import FastAPI

from nico.report_delivery_manifest_api import ReportDeliveryManifestRequest, register_report_delivery_manifest_routes, report_delivery_manifest_response


def test_report_delivery_manifest_api_registers_route():
    app = FastAPI()
    register_report_delivery_manifest_routes(app)

    assert "/reports/delivery-manifest" in {route.path for route in app.routes}


def test_report_delivery_manifest_api_returns_manifest():
    result = report_delivery_manifest_response(ReportDeliveryManifestRequest(payload={"report": {}}))

    assert result["artifact_schema"] == "nico.report_delivery_manifest.v1"
    assert result["human_review_required"] is True
