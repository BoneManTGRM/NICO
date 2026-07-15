from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from nico.api.hosted import REQUIRED_FULL_ASSESSMENT_ROUTES, app, register_hosted_extension_routes

EXPECTED_ROUTES = REQUIRED_FULL_ASSESSMENT_ROUTES


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def _route_counts(target: FastAPI) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            key = (str(method).upper(), path)
            counts[key] = counts.get(key, 0) + 1
    return counts


def test_hosted_app_registers_complete_full_assessment_delivery_surface():
    assert EXPECTED_ROUTES <= _route_pairs(app)


def test_hosted_route_registration_is_idempotent():
    target = FastAPI()
    register_hosted_extension_routes(target)
    first_counts = _route_counts(target)
    register_hosted_extension_routes(target)
    second_counts = _route_counts(target)
    assert EXPECTED_ROUTES <= set(first_counts)
    assert second_counts == first_counts
    assert all(first_counts[item] == 1 for item in EXPECTED_ROUTES)


def test_hosted_registration_rejects_partial_route_surface():
    target = FastAPI()
    target.add_api_route("/assessment/full-run", lambda: {"status": "partial"}, methods=["POST"])
    with pytest.raises(RuntimeError, match="Partial Full Assessment route registration"):
        register_hosted_extension_routes(target)


def test_hosted_registration_invalidates_cached_openapi_schema():
    target = FastAPI()
    initial_schema = target.openapi()
    assert "/assessment/full-run" not in (initial_schema.get("paths") or {})
    assert target.openapi_schema is not None
    register_hosted_extension_routes(target)
    assert target.openapi_schema is None
    refreshed_paths = target.openapi().get("paths") or {}
    assert "/assessment/full-run" in refreshed_paths
    assert "/delivery/approved/acknowledge" in refreshed_paths


def test_hosted_openapi_schema_exposes_full_assessment_routes():
    paths = app.openapi().get("paths") or {}
    assert "/assessment/full-run" in paths
    assert "post" in paths["/assessment/full-run"]
    assert "/delivery/approved/redeem" in paths
    assert "post" in paths["/delivery/approved/redeem"]
    assert "/delivery/approved/acknowledge" in paths
    assert "post" in paths["/delivery/approved/acknowledge"]


def test_docker_starts_the_canonical_production_entrypoint():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "uvicorn nico.api.production_bootstrap:app" in dockerfile
    assert "uvicorn nico.api.production:app" not in dockerfile
    assert "uvicorn nico.api.hosted:app" not in dockerfile
    assert "uvicorn nico.api.main:app" not in dockerfile
