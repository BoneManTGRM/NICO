from __future__ import annotations

from typing import Any, Iterable, Mapping

from nico.full_report_download_authorization_v1 import authorize_full_download
from nico.full_report_release_pipeline_v1 import build_full_release_pipeline

VERSION = "full_report_authorized_release_v1"
FORMATS = ("pdf", "html", "markdown")


def build_authorized_full_release(
    report: Mapping[str, Any],
    *,
    pages: Iterable[Any],
    exports: Mapping[str, Any],
    assessment_id: str,
    locale: str,
    report_format: str,
    actor_id: str,
    actor_role: str,
    workspace_id: str,
    assessment_workspace_id: str,
    request_id: str,
    human_review_complete: bool = False,
) -> dict[str, Any]:
    """Build, validate, select, authorize, and audit one Full report download."""
    result = build_full_release_pipeline(
        report,
        pages=pages,
        exports=exports,
        assessment_id=assessment_id,
        locale=locale,
        human_review_complete=human_review_complete,
    )
    fmt = str(report_format or "").strip().lower()
    responses = (result.get("full_download_responses") or {}).get("formats") or {}
    response = responses.get(fmt) if fmt in FORMATS else {}
    decision = authorize_full_download(
        response or {},
        actor_id=actor_id,
        actor_role=actor_role,
        workspace_id=workspace_id,
        assessment_workspace_id=assessment_workspace_id,
        request_id=request_id,
    )
    prior_allowed = bool(result.get("client_delivery_allowed"))
    allowed = prior_allowed and decision["client_delivery_allowed"]
    result["full_authorized_release"] = {
        "version": VERSION,
        "assessment_id": assessment_id,
        "locale": locale,
        "format": fmt,
        "pipeline_allowed": prior_allowed,
        "authorization": decision,
        "audit_event": decision["audit_event"],
        "client_delivery_allowed": allowed,
    }
    result["client_delivery_allowed"] = allowed
    return result


__all__ = ["FORMATS", "VERSION", "build_authorized_full_release"]
