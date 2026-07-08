from __future__ import annotations

from nico.api.main import app, targets


def test_main_api_mounts_service_catalog_routes():
    paths = {route.path for route in app.routes}

    assert "/service-catalog" in paths
    assert "/service-catalog/{workflow}" in paths
    assert "/service-catalog/intake-readiness" in paths


def test_targets_lists_service_catalog_endpoints():
    result = targets()
    endpoints = set(result["workflow_endpoints"])

    assert "GET /service-catalog" in endpoints
    assert "GET /service-catalog/{workflow}" in endpoints
    assert "POST /service-catalog/intake-readiness" in endpoints
