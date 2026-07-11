from __future__ import annotations

from fastapi import FastAPI

from nico.api.main import app
from nico.full_assessment_api import register_full_assessment_routes

FULL_ASSESSMENT_SENTINEL_PATH = "/assessment/full-run"


def register_hosted_extension_routes(target: FastAPI) -> FastAPI:
    """Register hosted-only route groups exactly once on the production app."""

    existing_paths = {getattr(route, "path", "") for route in target.routes}
    if FULL_ASSESSMENT_SENTINEL_PATH not in existing_paths:
        register_full_assessment_routes(target)
    return target


register_hosted_extension_routes(app)

__all__ = ["app", "register_hosted_extension_routes"]
