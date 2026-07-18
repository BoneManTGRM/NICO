from __future__ import annotations

import base64
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_backend_final_gate_truth.v1"
_PATCH_MARKER = "_nico_express_backend_final_gate_truth_v1"
_PRESERVE_FIELDS = (
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
    "evidence_readiness",
    "evidence_artifact_bundle",
    "findings",
    "repair_intelligence",
    "report_quality_guards",
    "report_generation_recovery",
)


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return value is not None


def _valid_pdf(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception:
        return False
    return raw.startswith(b"%PDF-") and b"%%EOF" in raw[-2048:]


def _completion_evidence(result: dict[str, Any]) -> dict[str, Any]:
    reports = _record(result.get("reports"))
    markdown_ready = bool(str(reports.get("markdown") or "").strip())
    html_ready = bool(str(reports.get("html") or "").strip())
    pdf_ready = _valid_pdf(reports.get("pdf_base64"))
    sections_ready = isinstance(result.get("sections"), list) and bool(result.get("sections"))
    maturity = _record(result.get("maturity_signal"))
    score = maturity.get("score", result.get("technical_score"))
    try:
        score_value = float(score)
        score_ready = 0.0 <= score_value <= 100.0
    except (TypeError, ValueError):
        score_ready = False
    return {
        "markdown_ready": markdown_ready,
        "html_ready": html_ready,
        "pdf_ready": pdf_ready,
        "report_formats_ready": markdown_ready and html_ready and pdf_ready,
        "sections_ready": sections_ready,
        "score_ready": score_ready,
    }


def reconcile_express_backend_completion(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(after if isinstance(after, dict) else {})
    source = before if isinstance(before, dict) else {}
    for field in _PRESERVE_FIELDS:
        if not _nonempty(output.get(field)) and _nonempty(source.get(field)):
            output[field] = deepcopy(source[field])

    tier = str(output.get("assessment_type") or output.get("service_tier") or source.get("assessment_type") or "express").lower()
    if tier != "express":
        return output

    evidence = _completion_evidence(output)
    complete = evidence["report_formats_ready"] and evidence["sections_ready"] and evidence["score_ready"]
    completion = {
        "version": PATCH_VERSION,
        "tier": "express",
        **evidence,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_completion_separate_from_client_acceptance": True,
    }

    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False

    if complete:
        output["status"] = "complete"
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["report_generation_status"] = "complete"
        output["delivery_status"] = "blocked_pending_human_review"
        output["recovery_required"] = False
        completion["status"] = "complete_pending_human_review"
        output["assessment_completion"] = completion
        output["express_completion"] = completion
        return output

    missing = [name for name, ready in (
        ("markdown", evidence["markdown_ready"]),
        ("html", evidence["html_ready"]),
        ("pdf", evidence["pdf_ready"]),
        ("sections", evidence["sections_ready"]),
        ("score", evidence["score_ready"]),
    ) if not ready]
    completion["status"] = "blocked_missing_completion_evidence"
    completion["missing"] = missing
    output["status"] = "blocked"
    output["current_stage"] = "truth_and_review_gates"
    output["report_generation_status"] = "blocked_missing_usable_artifacts" if any(x in missing for x in ("markdown", "html", "pdf")) else str(output.get("report_generation_status") or "complete")
    output["recovery_required"] = True
    output["recovery_code"] = "express_backend_completion_evidence_missing"
    output["assessment_completion"] = completion
    output["express_completion"] = completion
    return output


def install_express_backend_final_gate_truth() -> dict[str, Any]:
    import nico.client_acceptance as client_acceptance
    from nico.api import main as api_main

    current: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_client_acceptance_gate
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def authoritative_gate(result: dict[str, Any]) -> dict[str, Any]:
        before = deepcopy(result)
        after = current(result)
        return reconcile_express_backend_completion(before, after)

    setattr(authoritative_gate, _PATCH_MARKER, True)
    setattr(authoritative_gate, "_nico_previous", current)
    api_main.attach_client_acceptance_gate = authoritative_gate
    client_acceptance.attach_client_acceptance_gate = authoritative_gate
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "backend_authoritative": True,
        "preserves_report_and_score_fields": True,
        "validates_pdf_structure": True,
        "separates_completion_from_delivery": True,
    }


__all__ = [
    "PATCH_VERSION",
    "install_express_backend_final_gate_truth",
    "reconcile_express_backend_completion",
]
