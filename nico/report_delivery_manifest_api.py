from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from nico.report_delivery_manifest import build_report_delivery_manifest


class ReportDeliveryManifestRequest(BaseModel):
    payload: dict[str, Any] = {}


def report_delivery_manifest_response(req: ReportDeliveryManifestRequest) -> dict[str, Any]:
    return build_report_delivery_manifest(req.payload or {})


def register_report_delivery_manifest_routes(app: FastAPI) -> None:
    app.post("/reports/delivery-manifest")(report_delivery_manifest_response)
