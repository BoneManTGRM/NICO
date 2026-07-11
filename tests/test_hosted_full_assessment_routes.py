from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from nico.api.hosted import app, register_hosted_extension_routes


EXPECTED_ROUTES = {
    ("POST", "/assessment/full-run"),
    ("POST", "/assessment/full-run/{run_id}/status"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/verify"),
    ("POST", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/access"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/receipts"),
    ("GET", "/assessment/full-run/{run_id}/approved-delivery/acknowledgments"),
    ("POST", "/assessment/full-run/approved-delivery/access/{access_id}/revoke"),
    ("POST", "/delivery/approved/inspect"),
    ("POST", "/delivery/approved/redeem"),
    ("POST", "/delivery/approved/acknowledge"),
    ("GET", "/reports/{run_id}/approved-delivery"),
    ("GET", "/reports/{run_id}/approved-delivery/verify"),
    ("GET", "/reports/{run_id}/approved-delivery/receipts"),
    ("GET", "/reports/{run_id}/approved-delivery/acknowledgments"),
}


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
    registered = _route_pairs(app)

    assert EXPECTED_ROUTES <= registered


def test_hosted_route_registration_is_idempotent():
    target = FastAPI()

    register_hosted_extension_routes(target)
    first_counts = _route_counts(target)
    register_hosted_extension_routes(target)
    second_counts = _route_counts(target)

    assert EXPECTED_ROUTES <= set(first_counts)
    assert second_counts == first_counts
    assert all(first_counts[item] == 1 for item in EXPECTED_ROUTES)


def test_hosted_openapi_schema_exposes_full_assessment_routes():
    paths = app.openapi().get("paths") or {}

    assert "/assessment/full-run" in paths
    assert "post" in paths["/assessment/full-run"]
    assert "/delivery/approved/redeem" in paths
    assert "post" in paths["/delivery/approved/redeem"]
    assert "/delivery/approved/acknowledge" in paths
    assert "post" in paths["/delivery/approved/acknowledge"]


def test_docker_starts_the_hosted_route_entrypoint():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "uvicorn nico.api.hosted:app" in dockerfile
    assert "uvicorn nico.api.main:app" not in dockerfile
