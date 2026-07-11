from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nico.mid_optional_evidence import submit_mid_optional_evidence


class MidOptionalEvidenceRequest(BaseModel):
    token: str = ""
    application_url: str = ""
    ios_build_access: str = ""
    android_build_access: str = ""
    architecture_documents: str = ""
    product_requirements: str = ""
    stakeholder_questionnaire: str = ""
    meeting_transcripts: str = ""
    existing_roadmap: str = ""
    business_priorities: str = ""


def _payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def mid_optional_evidence_response(run_id: str, req: MidOptionalEvidenceRequest) -> dict[str, Any]:
    result = submit_mid_optional_evidence(run_id, _payload(req))
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail={"status": "not_found", "message": "Optional evidence submission is unavailable."},
        )
    if result.get("status") == "blocked":
        raise HTTPException(
            status_code=400,
            detail={"status": "blocked", "message": str(result.get("error") or "Optional evidence submission was blocked.")},
        )
    return result


def register_mid_optional_evidence_routes(app: FastAPI) -> None:
    app.post("/assessment/mid-run/{run_id}/evidence")(mid_optional_evidence_response)


__all__ = [
    "MidOptionalEvidenceRequest",
    "mid_optional_evidence_response",
    "register_mid_optional_evidence_routes",
]
