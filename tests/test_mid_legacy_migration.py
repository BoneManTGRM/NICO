from __future__ import annotations

import json

from fastapi import FastAPI

from nico.api.production import app as production_app
from nico.mid_legacy_migration import (
    LEGACY_DEPRECATION_CODE,
    LEGACY_ENABLE_ENV,
    LEGACY_MID_PATH,
    UNIFIED_MID_PATH,
    LegacyMidAssessmentRequest,
    legacy_mid_response,
    register_legacy_mid_migration,
)
from nico.storage import STORE


def _json(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _legacy_routes(app: FastAPI):
    return [
        route
        for route in app.routes
        if str(getattr(route, "path", "")) == LEGACY_MID_PATH
        and "POST" in {str(method).upper() for method in (getattr(route, "methods", set()) or set())}
    ]


def test_legacy_mid_is_disabled_by_default_with_successor_headers(monkeypatch):
    monkeypatch.delenv(LEGACY_ENABLE_ENV, raising=False)

    response = legacy_mid_response(LegacyMidAssessmentRequest(authorized=True, client_name="Legacy Client"))
    payload = _json(response)

    assert response.status_code == 410
    assert payload["status"] == "deprecated"
    assert payload["code"] == LEGACY_DEPRECATION_CODE
    assert payload["deprecated_endpoint"] == LEGACY_MID_PATH
    assert payload["successor_endpoint"] == UNIFIED_MID_PATH
    assert payload["migration"]["repository_first"] is True
    assert payload["migration"]["snapshot_bound"] is True
    assert payload["migration"]["manual_notes_as_primary_assessment"] is False
    assert payload["migration"]["artifacts_created"] is False
    assert payload["migration"]["compatibility_default"] is False
    assert response.headers["deprecation"] == "true"
    assert response.headers["x-nico-legacy-mid-enabled"] == "false"
    assert response.headers["x-nico-mid-successor"] == UNIFIED_MID_PATH
    assert 'rel="successor-version"' in response.headers["link"]
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert "75-85%" not in repr(payload)
    assert "90-95%" not in repr(payload)


def test_disabled_legacy_mid_creates_no_run_report_approval_or_evidence(monkeypatch):
    monkeypatch.delenv(LEGACY_ENABLE_ENV, raising=False)
    before = {
        table: len(STORE.list(table))
        for table in ("assessment_runs", "reports", "approvals", "evidence_items")
    }

    response = legacy_mid_response(
        LegacyMidAssessmentRequest(
            authorized=True,
            qa_evidence="Manual QA note",
            parity_notes="Manual parity note",
            stakeholder_notes="Manual stakeholder note",
            roadmap_notes="Manual roadmap note",
        )
    )
    after = {
        table: len(STORE.list(table))
        for table in ("assessment_runs", "reports", "approvals", "evidence_items")
    }

    assert response.status_code == 410
    assert after == before


def test_explicit_compatibility_flag_preserves_old_response_but_marks_it_non_unified(monkeypatch):
    monkeypatch.setenv(LEGACY_ENABLE_ENV, "true")

    response = legacy_mid_response(
        LegacyMidAssessmentRequest(
            authorized=True,
            client_name="Migration Client",
            project_name="Migration Project",
            qa_evidence="Observed login flow manually.",
            parity_notes="Compared one mobile screen manually.",
        )
    )
    payload = _json(response)

    assert response.status_code == 200
    assert payload["deprecated"] is True
    assert payload["legacy_compatibility_mode"] is True
    assert payload["legacy_endpoint"] == LEGACY_MID_PATH
    assert payload["successor_endpoint"] == UNIFIED_MID_PATH
    assert payload["unified_run"] is False
    assert payload["snapshot_bound"] is False
    assert payload["client_delivery_allowed"] is False
    assert "not the unified evidence-bound Mid workflow" in payload["migration_warning"]
    assert response.headers["x-nico-legacy-mid-enabled"] == "true"
    assert response.headers["deprecation"] == "true"


def test_compatibility_mode_still_enforces_authorization(monkeypatch):
    monkeypatch.setenv(LEGACY_ENABLE_ENV, "true")

    response = legacy_mid_response(LegacyMidAssessmentRequest(authorized=False))
    payload = _json(response)

    assert response.status_code == 400
    assert payload["status"] == "blocked"
    assert payload["deprecated"] is True
    assert payload["client_delivery_allowed"] is False


def test_route_replacement_is_idempotent_and_removes_old_handler():
    app = FastAPI()

    @app.post(LEGACY_MID_PATH)
    def old_manual_handler():
        return {"old": True}

    removed_first = register_legacy_mid_migration(app)
    removed_second = register_legacy_mid_migration(app)
    routes = _legacy_routes(app)

    assert removed_first == 1
    assert removed_second == 1
    assert len(routes) == 1
    assert routes[0].endpoint is legacy_mid_response
    assert routes[0].deprecated is True
    assert all(route.endpoint is not old_manual_handler for route in routes)


def test_production_exposes_exactly_one_deprecated_legacy_boundary_and_unified_successor():
    routes = _legacy_routes(production_app)
    pairs = {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in production_app.routes
        for method in (getattr(route, "methods", set()) or set())
    }

    assert len(routes) == 1
    assert routes[0].endpoint is legacy_mid_response
    assert routes[0].deprecated is True
    assert ("POST", LEGACY_MID_PATH) in pairs
    assert ("POST", UNIFIED_MID_PATH) in pairs
    assert ("POST", "/assessment/mid-run/{run_id}/evidence") in pairs
    assert ("GET", "/assessment/mid-run/{run_id}/review-exceptions") in pairs
    assert ("POST", "/assessment/mid-run/{run_id}/approval/request") in pairs
    assert ("POST", "/assessment/mid-run/{run_id}/delivery/access") in pairs
