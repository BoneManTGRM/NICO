from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _production_probe() -> dict:
    script = r'''
import json

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_review_work_runtime_v1 import GET_ROUTE, POST_ROUTE
from nico.comprehensive_run_service import ComprehensiveRunService


def route_count(method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected
        in {
            str(item).upper()
            for item in (getattr(route, "methods", set()) or set())
        }
    )


print(
    "NICO_PRODUCTION_PROBE="
    + json.dumps(
        {
            "get_route_count": route_count("GET", GET_ROUTE),
            "post_route_count": route_count("POST", POST_ROUTE),
            "delivery_authorization_route_count": route_count(
                "POST",
                "/assessment/comprehensive-run/{run_id}/authorize-delivery",
            ),
            "delivery_authorization_service_method": callable(
                getattr(ComprehensiveRunService, "authorize_delivery", None)
            ),
            "status": dict(getattr(app.state, "nico_phase2_review_work", {}) or {}),
        },
        sort_keys=True,
    )
)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    prefix = "NICO_PRODUCTION_PROBE="
    line = next(
        (value for value in reversed(completed.stdout.splitlines()) if value.startswith(prefix)),
        "",
    )
    assert line, completed.stdout
    return json.loads(line.removeprefix(prefix))


def test_phase2_review_work_routes_are_present_exactly_once_on_production_app() -> None:
    probe = _production_probe()
    assert probe["get_route_count"] == 1
    assert probe["post_route_count"] == 1
    assert probe["delivery_authorization_route_count"] == 1
    assert probe["delivery_authorization_service_method"] is True


def test_phase2_terminal_production_boundary_is_fail_closed() -> None:
    status = _production_probe()["status"]
    assert status["status"] == "installed"
    assert status["review_work_get_route_count"] == 1
    assert status["review_work_post_route_count"] == 1
    assert status["protected_admin_authorization"] is True
    assert status["runtime_service_binding"] is True
    assert status["configurable_quality_control_sampling"] is True
    assert status["bulk_review_fails_closed_for_individual_attention"] is True
    assert status["report_truth_synchronized_before_approval"] is True
    assert status["final_human_decision_bound_into_accepted_edition"] is True
    assert status["approved_delivery_has_one_client_report"] is True
    assert status["approved_client_pdf_preserved_exactly"] is True
    assert status["approval_certificate_is_separate_json"] is True
    assert status["delivery_validates_exact_review_ledger"] is True
    assert status["four_hour_target_is_safety_gate"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
