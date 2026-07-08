from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.report_readiness_attachment import attach_report_readiness_gate


class ReportReadinessAttachmentRequest(BaseModel):
    report: dict[str, Any] = {}
    readiness_gate: dict[str, Any] = {}


def report_readiness_attachment_response(req: ReportReadinessAttachmentRequest) -> dict[str, Any]:
    return attach_report_readiness_gate(req.report or {}, req.readiness_gate or {})


def register_report_readiness_attachment_routes(app: FastAPI) -> None:
    app.post("/reports/attach-readiness")(report_readiness_attachment_response)
