from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from nico.service_workflows import build_mid_assessment

LEGACY_MID_PATH = "/assessment/mid"
UNIFIED_MID_PATH = "/assessment/mid-run"
LEGACY_ENABLE_ENV = "NICO_ENABLE_LEGACY_MID_MANUAL"
LEGACY_DEPRECATION_CODE = "legacy_mid_manual_deprecated"


class LegacyMidAssessmentRequest(BaseModel):
    authorized: bool = False
    client_name: str = ""
    project_name: str = ""
    qa_evidence: str = ""
    parity_notes: str = ""
    stakeholder_notes: str = ""
    roadmap_notes: str = ""
    known_risks: str = ""
    customer_id: str = "default_customer"
    project_id: str = "default_project"


def _payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def legacy_mid_enabled() -> bool:
    return os.getenv(LEGACY_ENABLE_ENV, "false").strip().lower() == "true"


def legacy_mid_headers(enabled: bool) -> dict[str, str]:
    return {
        "Cache-Control": "no-store, private, max-age=0",
        "Pragma": "no-cache",
        "Deprecation": "true",
        "Link": f'<{UNIFIED_MID_PATH}>; rel="successor-version"',
        "Warning": '299 NICO "Legacy Mid manual-notes workflow is deprecated; use /assessment/mid-run."',
        "X-NICO-Legacy-Mid-Enabled": "true" if enabled else "false",
        "X-NICO-Mid-Successor": UNIFIED_MID_PATH,
    }


def legacy_mid_deprecation_payload() -> dict[str, Any]:
    return {
        "status": "deprecated",
        "code": LEGACY_DEPRECATION_CODE,
        "message": "The legacy manual-notes Mid workflow is disabled. Use the unified repository-first Mid Assessment endpoint.",
        "deprecated_endpoint": LEGACY_MID_PATH,
        "successor_endpoint": UNIFIED_MID_PATH,
        "successor_method": "POST",
        "required_successor_fields": [
            "repository or target",
            "authorization_confirmed or authorized",
            "optional client_name",
            "optional project_name",
        ],
        "optional_evidence_endpoint_template": "/assessment/mid-run/{run_id}/evidence",
        "migration": {
            "one_run_id": True,
            "repository_first": True,
            "snapshot_bound": True,
            "manual_notes_as_primary_assessment": False,
            "artifacts_created": False,
            "compatibility_flag": LEGACY_ENABLE_ENV,
            "compatibility_default": False,
        },
        "rule": "The deprecated endpoint does not create a Mid run, report, score, approval, or delivery artifact unless the explicit server-side compatibility flag is enabled.",
    }


def legacy_mid_response(req: LegacyMidAssessmentRequest) -> JSONResponse:
    enabled = legacy_mid_enabled()
    headers = legacy_mid_headers(enabled)
    if not enabled:
        return JSONResponse(status_code=410, content=legacy_mid_deprecation_payload(), headers=headers)

    result = build_mid_assessment(_payload(req))
    status_code = 400 if result.get("status") == "blocked" else 200
    result["deprecated"] = True
    result["legacy_compatibility_mode"] = True
    result["legacy_endpoint"] = LEGACY_MID_PATH
    result["successor_endpoint"] = UNIFIED_MID_PATH
    result["migration_warning"] = (
        "Compatibility mode preserves the former manual-notes response temporarily. "
        "It is not the unified evidence-bound Mid workflow and must not be presented as a repository-first Mid Assessment."
    )
    result["unified_run"] = False
    result["snapshot_bound"] = False
    result["client_delivery_allowed"] = False
    return JSONResponse(status_code=status_code, content=result, headers=headers)


def register_legacy_mid_migration(app: FastAPI) -> int:
    """Replace every POST /assessment/mid handler with the guarded migration endpoint."""

    retained = []
    removed = 0
    for route in app.router.routes:
        path = str(getattr(route, "path", ""))
        methods = {str(method).upper() for method in (getattr(route, "methods", set()) or set())}
        if path == LEGACY_MID_PATH and "POST" in methods:
            removed += 1
            continue
        retained.append(route)
    app.router.routes[:] = retained
    app.post(LEGACY_MID_PATH, include_in_schema=True, deprecated=True)(legacy_mid_response)
    app.openapi_schema = None
    return removed


__all__ = [
    "LEGACY_MID_PATH",
    "UNIFIED_MID_PATH",
    "LEGACY_ENABLE_ENV",
    "LEGACY_DEPRECATION_CODE",
    "LegacyMidAssessmentRequest",
    "legacy_mid_enabled",
    "legacy_mid_headers",
    "legacy_mid_deprecation_payload",
    "legacy_mid_response",
    "register_legacy_mid_migration",
]
