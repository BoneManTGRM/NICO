from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.workflow_preflight import build_workflow_preflight, build_workflow_preflight_batch


class WorkflowPreflightRequest(BaseModel):
    payload: dict[str, Any] = {}


class WorkflowPreflightBatchRequest(BaseModel):
    payloads: list[dict[str, Any]] = []


def workflow_preflight_response(req: WorkflowPreflightRequest) -> dict[str, Any]:
    return build_workflow_preflight(req.payload or {})


def workflow_preflight_batch_response(req: WorkflowPreflightBatchRequest) -> dict[str, Any]:
    return build_workflow_preflight_batch(req.payloads or [])


def register_workflow_preflight_routes(app: FastAPI) -> None:
    app.post("/workflow/preflight")(workflow_preflight_response)
    app.post("/workflow/preflight/batch")(workflow_preflight_batch_response)
