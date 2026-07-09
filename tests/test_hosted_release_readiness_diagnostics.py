from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.hosted_release_readiness_diagnostics import (
    hosted_release_readiness_diagnostics,
    install_hosted_release_readiness_diagnostics_route,
    register_hosted_release_readiness_diagnostics_routes,
)


def test_release_readiness_diagnostics_reports_installed_components():
    payload = hosted_release_readiness_diagnostics()

    assert payload["status"] == "ok"
    assert payload["summary_schema"] == "nico.release_readiness_summary.v1"
    assert payload["client_delivery_allowed_default"] is False
    assert "release_readiness_summary_patch" in payload["patch_chain"]
    assert "release_readiness_summary_json" in payload["required_report_export_keys"]
    assert payload["guardrail"]


def test_register_release_readiness_route_is_idempotent():
    app = FastAPI()

    register_hosted_release_readiness_diagnostics_routes(app)
    register_hosted_release_readiness_diagnostics_routes(app)

    routes = [route.path for route in app.routes]
    assert routes.count("/diagnostics/release-readiness") == 1
    response = TestClient(app).get("/diagnostics/release-readiness")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_install_release_readiness_route_patches_fastapi_init():
    install_hosted_release_readiness_diagnostics_route()
    app = FastAPI()

    routes = [route.path for route in app.routes]
    assert "/diagnostics/release-readiness" in routes
