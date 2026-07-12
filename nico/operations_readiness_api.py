from __future__ import annotations

from fastapi import FastAPI, Request

from nico.operations_readiness import build_operations_readiness

OPERATIONS_READINESS_PATH = "/operations/readiness"


def application_route_inventory(app: FastAPI) -> list[str]:
    inventory: set[str] = set()
    for route in app.routes:
        path = str(getattr(route, "path", "")).strip()
        if not path:
            continue
        for method in getattr(route, "methods", set()) or set():
            normalized = str(method).upper()
            if normalized in {"HEAD", "OPTIONS"}:
                continue
            inventory.add(f"{normalized} {path}")
    return sorted(inventory)


def operations_readiness_response(request: Request) -> dict:
    return build_operations_readiness(application_route_inventory(request.app))


def _route_registered(app: FastAPI) -> bool:
    for route in app.routes:
        if str(getattr(route, "path", "")) != OPERATIONS_READINESS_PATH:
            continue
        methods = {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
        if "GET" in methods:
            return True
    return False


def register_operations_readiness_routes(app: FastAPI) -> None:
    if _route_registered(app):
        return
    app.get(OPERATIONS_READINESS_PATH, tags=["operations"])(operations_readiness_response)
    app.openapi_schema = None
