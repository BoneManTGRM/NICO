from __future__ import annotations

from importlib import import_module

from fastapi import FastAPI, Request

from nico.express_final_report_progress_patch import install_express_final_report_progress_patch
from nico.final_report_runtime_copy_patch import install_final_report_runtime_copy_patch
from nico.operations_readiness import build_operations_readiness

FINAL_REPORT_RUNTIME_COPY = install_final_report_runtime_copy_patch()
EXPRESS_FINAL_REPORT_PROGRESS = install_express_final_report_progress_patch()
register_final_review_operator_routes = import_module(
    "nico.final_review_operator_api"
).register_final_review_operator_routes

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
    # Final-review operations share the operator control plane and must be installed
    # before readiness inventory is calculated. Their write paths remain admin-gated.
    register_final_review_operator_routes(app)
    if _route_registered(app):
        return
    app.get(OPERATIONS_READINESS_PATH, tags=["operations"])(operations_readiness_response)
    app.openapi_schema = None
