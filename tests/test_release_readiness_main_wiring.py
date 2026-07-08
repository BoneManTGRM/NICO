from __future__ import annotations

from nico.api.main import app, targets


def test_main_api_has_release_readiness_route():
    paths = {route.path for route in app.routes}

    assert "/release/readiness" in paths


def test_targets_includes_release_readiness_route():
    result = targets()
    endpoints = set(result["workflow_endpoints"])

    assert "POST /release/readiness" in endpoints
