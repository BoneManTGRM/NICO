from __future__ import annotations

from nico.api.main import app, targets


def test_main_api_has_hosted_smoke_test_route():
    paths = {route.path for route in app.routes}

    assert "/hosted/smoke-test" in paths


def test_targets_includes_hosted_smoke_test_route():
    result = targets()
    endpoints = set(result["workflow_endpoints"])

    assert "POST /hosted/smoke-test" in endpoints
