from __future__ import annotations

import base64
from typing import Any

from nico.express_report_dossier_export_v15 import build_express_dossier_export
from nico.express_report_visual_qa_v16 import validate_express_pdf


VERSION = "express_visual_qa_binding_v16"
_PATCH_MARKER = "_nico_express_visual_qa_binding_v16"


def build_express_pdf_with_visual_qa(result: dict[str, Any]) -> tuple[str | None, str | None]:
    encoded, error = build_express_dossier_export(result)
    if error or not encoded:
        result["express_visual_qa"] = {
            "status": "fail",
            "version": VERSION,
            "issues": [error or "Final Express PDF was not produced."],
            "client_delivery_allowed": False,
            "human_review_required": True,
        }
        return None, error or "Final Express PDF was not produced."

    try:
        pdf_bytes = base64.b64decode(encoded)
        qa = validate_express_pdf(pdf_bytes, result)
    except Exception as exc:  # pragma: no cover
        qa = {
            "status": "fail",
            "version": VERSION,
            "issues": [f"Visual QA execution failed: {type(exc).__name__}: {exc}"],
            "client_delivery_allowed": False,
            "human_review_required": True,
        }

    result["express_visual_qa"] = qa
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    reports["pdf_quality_status"] = qa.get("status")
    reports["pdf_quality_issues"] = list(qa.get("issues") or [])
    reports["client_delivery_allowed"] = bool(qa.get("client_delivery_allowed"))
    result["reports"] = reports

    # Preserve the evidence artifact for internal review, but fail closed for any
    # client-delivery or approval path until all QA and human-review gates pass.
    if qa.get("status") != "pass":
        result["client_delivery_allowed"] = False
        result["client_delivery_block_reason"] = "Express visual QA did not pass."
    elif bool(result.get("human_review_required", True)):
        result["client_delivery_allowed"] = False
        result["client_delivery_block_reason"] = "Authorized human review is still required."
    else:
        result["client_delivery_allowed"] = True
        result.pop("client_delivery_block_reason", None)

    return encoded, None


def install_express_visual_qa_binding_v16() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(build_express_pdf_with_visual_qa, _PATCH_MARKER, True)
    setattr(build_express_pdf_with_visual_qa, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_pdf_with_visual_qa
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "fail_closed": True,
        "human_review_required": True,
    }


__all__ = ["VERSION", "build_express_pdf_with_visual_qa", "install_express_visual_qa_binding_v16"]
