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


def test_phase2_terminal_production_boundary_is_fail_closed() -> None:
    status = dict(getattr(app.state, "nico_phase2_review_work", {}) or {})
    assert status["status"] == "installed"
    assert status["review_work_get_route_count"] == 1
    assert status["review_work_post_route_count"] == 1
    assert status["protected_admin_authorization"] is True
    assert status["runtime_service_binding"] is True
    assert status["configurable_quality_control_sampling"] is True
    assert status["bulk_review_fails_closed_for_individual_attention"] is True
    assert status["report_truth_synchronized_before_approval"] is True
    assert status["approved_delivery_has_one_client_report"] is True
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
