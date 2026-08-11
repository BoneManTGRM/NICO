from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_review_work_runtime_v1 import GET_ROUTE, POST_ROUTE


def _route_count(method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def test_phase2_review_work_routes_are_present_exactly_once_on_production_app() -> None:
    assert _route_count("GET", GET_ROUTE) == 1
    assert _route_count("POST", POST_ROUTE) == 1
