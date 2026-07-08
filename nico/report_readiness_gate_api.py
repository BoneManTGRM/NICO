from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.report_readiness_gate import build_report_readiness_gate


class ReportReadinessGateRequest(BaseModel):
    payload: dict[str, Any] = {}


def report_readiness_gate_response(req: ReportReadinessGateRequest) -> dict[str, Any]:
    return build_report_readiness_gate(req.payload or {})


def register_report_readiness_gate_routes(app: FastAPI) -> None:
    app.post("/reports/readiness-gate")(report_readiness_gate_response)
