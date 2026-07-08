from __future__ import annotations

from nico.api.main import app, targets


def test_main_api_has_workflow_preflight_routes():
    paths = {route.path for route in app.routes}

    assert "/workflow/preflight" in paths
    assert "/workflow/preflight/batch" in paths


def test_targets_includes_workflow_preflight_routes():
    result = targets()
    endpoints = set(result["workflow_endpoints"])

    assert "POST /workflow/preflight" in endpoints
    assert "POST /workflow/preflight/batch" in endpoints
