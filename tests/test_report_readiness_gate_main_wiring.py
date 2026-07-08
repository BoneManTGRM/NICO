from __future__ import annotations

from nico.api.main import app, targets


def test_main_api_has_report_readiness_gate_route():
    paths = {route.path for route in app.routes}

    assert "/reports/readiness-gate" in paths


def test_targets_includes_report_readiness_gate_route():
    result = targets()
    endpoints = set(result["workflow_endpoints"])

    assert "POST /reports/readiness-gate" in endpoints
