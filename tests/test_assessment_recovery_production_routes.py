from __future__ import annotations

from fastapi import FastAPI

import nico.assessment_recovery as assessment_recovery
import nico.scanner_recovery as scanner_recovery
import nico.storage_schema_readiness as storage_schema
from nico.api.production import (
    REQUIRED_ASSESSMENT_RECOVERY_ROUTES,
    REQUIRED_PRODUCTION_ROUTES,
    register_production_routes,
)


def _route_pairs(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }


def test_assessment_recovery_routes_are_required_in_production_contract() -> None:
    assert REQUIRED_ASSESSMENT_RECOVERY_ROUTES == {
        ("GET", "/operations/recovery/assessments"),
        ("POST", "/operations/recovery/assessment/{run_id}/resume"),
    }
    assert REQUIRED_ASSESSMENT_RECOVERY_ROUTES <= REQUIRED_PRODUCTION_ROUTES


def test_production_registration_installs_assessment_recovery_once(monkeypatch) -> None:
    monkeypatch.setattr(
        assessment_recovery,
        "reconcile_interrupted_assessment_runs",
        lambda **kwargs: {
            "artifact_schema": assessment_recovery.ASSESSMENT_RECOVERY_SCHEMA,
            "status": "clear",
            "recovery_required": 0,
            "automatic_resume": False,
        },
    )
    monkeypatch.setattr(
        scanner_recovery,
        "reconcile_interrupted_scanner_runs",
        lambda **kwargs: {
            "artifact_schema": scanner_recovery.SCANNER_RECOVERY_SCHEMA,
            "status": "clear",
            "recovery_required": 0,
            "automatic_resume": False,
        },
    )
    monkeypatch.setattr(
        storage_schema,
        "refresh_storage_schema_readiness",
        lambda **kwargs: {
            "status": "ready",
            "contract_sha256": "a" * 64,
        },
    )

    app = FastAPI()
    register_production_routes(app)
    register_production_routes(app)
    pairs = _route_pairs(app)

    assert REQUIRED_ASSESSMENT_RECOVERY_ROUTES <= pairs
    for method, path in REQUIRED_ASSESSMENT_RECOVERY_ROUTES:
        assert sum(
            1
            for route in app.routes
            if str(getattr(route, "path", "")) == path
            and method in {
                str(item).upper()
                for item in (getattr(route, "methods", set()) or set())
            }
        ) == 1
