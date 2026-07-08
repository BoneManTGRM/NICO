from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.hosted_smoke_test import build_hosted_smoke_test


class HostedSmokeTestRequest(BaseModel):
    payload: dict[str, Any] = {}


def hosted_smoke_test_response(req: HostedSmokeTestRequest) -> dict[str, Any]:
    return build_hosted_smoke_test(req.payload or {})


def register_hosted_smoke_test_routes(app: FastAPI) -> None:
    app.post("/hosted/smoke-test")(hosted_smoke_test_response)
