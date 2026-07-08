from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.easy_mode import build_easy_mode_catalog, build_easy_mode_intake
from nico.service_catalog import build_service_intake_readiness, get_service_catalog_item, list_service_catalog


class ServiceIntakeRequest(BaseModel):
    payload: dict[str, Any] = {}


class EasyModeIntakeRequest(BaseModel):
    payload: dict[str, Any] = {}


def service_catalog_response() -> dict[str, Any]:
    return list_service_catalog()


def service_catalog_item_response(workflow: str) -> dict[str, Any]:
    result = get_service_catalog_item(workflow)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result)
    return result


def service_intake_readiness_response(req: ServiceIntakeRequest) -> dict[str, Any]:
    return build_service_intake_readiness(req.payload or {})


def easy_mode_response() -> dict[str, Any]:
    return build_easy_mode_catalog()


def easy_mode_intake_response(req: EasyModeIntakeRequest) -> dict[str, Any]:
    return build_easy_mode_intake(req.payload or {})


def register_service_catalog_routes(app: FastAPI) -> None:
    """Register service catalog endpoints on a FastAPI app."""
    app.get("/service-catalog")(service_catalog_response)
    app.get("/service-catalog/easy-mode")(easy_mode_response)
    app.post("/service-catalog/easy-mode/intake")(easy_mode_intake_response)
    app.get("/service-catalog/{workflow}")(service_catalog_item_response)
    app.post("/service-catalog/intake-readiness")(service_intake_readiness_response)
