from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nico.mid_optional_evidence import MAX_FIELD_CHARS, submit_mid_optional_evidence


class MidOptionalEvidenceRequest(BaseModel):
    token: str = Field(default="", max_length=256)
    application_url: str = Field(default="", max_length=MAX_FIELD_CHARS)
    ios_build_access: str = Field(default="", max_length=MAX_FIELD_CHARS)
    android_build_access: str = Field(default="", max_length=MAX_FIELD_CHARS)
    architecture_documents: str = Field(default="", max_length=MAX_FIELD_CHARS)
    product_requirements: str = Field(default="", max_length=MAX_FIELD_CHARS)
    stakeholder_questionnaire: str = Field(default="", max_length=MAX_FIELD_CHARS)
    meeting_transcripts: str = Field(default="", max_length=MAX_FIELD_CHARS)
    existing_roadmap: str = Field(default="", max_length=MAX_FIELD_CHARS)
    business_priorities: str = Field(default="", max_length=MAX_FIELD_CHARS)


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
