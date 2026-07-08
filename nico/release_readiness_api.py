from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.deployment_verification import build_deployment_verification


class ReleaseReadinessRequest(BaseModel):
    payload: dict[str, Any] = {}


def release_readiness_response(req: ReleaseReadinessRequest) -> dict[str, Any]:
    return build_deployment_verification(req.payload or {})


def register_release_readiness_routes(app: FastAPI) -> None:
    app.post("/release/readiness")(release_readiness_response)
