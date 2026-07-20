from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_section_status_truth.v26"
_PATCH_MARKER = "_nico_express_section_status_truth_v26"
_REVIEW_TERMS = (
    " failed",
    "status=failed",
    " timeout",
    "timed out",
    "status=timeout",
    " unavailable",
    "requires human triage",
    "requires human review",
    "finding(s)",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _has_unresolved(section: dict[str, Any]) -> bool:
    values = [*(section.get("findings") or []), *(section.get("unavailable") or [])]
    for value in values:
        text = f" {_text(value)}"
        if any(term in text for term in _REVIEW_TERMS):
            return True
    return False


def reconcile_section_status_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    sections = output.get("sections")
    changed: list[str] = []
    if not isinstance(sections, list):
        sections = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        label = str(section.get("label") or "")
        if section_id == "scanner_worker_evidence" or label.casefold() == "scanner worker evidence":
            section.update(
                {
                    "status": "SUPPLEMENTAL",
                    "display_status": "SUPPLEMENTAL · NOT SCORED",
                    "directly_scored": False,
                    "score_treatment": "supplemental_not_scored",
                    "presented_score": None,
                    "presented": None,
                    "score": None,
                }
            )
            changed.append(section_id or "scanner_worker_evidence")
            continue
        if section_id == "client_acceptance" or label.casefold() == "client / human acceptance":
            section.update(
                {
                    "status": "gray",
                    "display_status": "GRAY · NOT SCORED",
                    "directly_scored": False,
                    "score_treatment": "not_scored_pending_approval",
                    "presented_score": None,
                    "presented": None,
                    "score": None,
                }
            )
            changed.append(section_id or "client_acceptance")
            continue
        if str(section.get("status") or "").casefold() == "green" and _has_unresolved(section):
            section["status"] = "yellow"
            section["display_status"] = "YELLOW · REVIEW LIMITED"
            section["status_reason"] = "Unresolved failed, timed-out, unavailable, or human-triage evidence prevents a GREEN presentation state."
            changed.append(section_id or label)

    output["sections"] = sections
    output["express_section_status_truth"] = {
        "status": "complete",
        "version": VERSION,
        "changed_sections": changed,
        "green_requires_no_unresolved_analyzer_evidence": True,
        "scanner_worker_not_scored": True,
        "client_acceptance_not_scored": True,
    }
    return output


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    result.clear()
    result.update(normalized)
    if isinstance(existing_reports, dict) and isinstance(result.get("reports"), dict):
        reports = result["reports"]
        existing_reports.clear()
        existing_reports.update(reports)
        result["reports"] = existing_reports


def install_express_section_status_truth_v26() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        normalized = reconcile_section_status_truth(result)
        _apply_in_place(result, normalized)
        return current(result)

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {"status": "installed", "version": VERSION}


__all__ = ["VERSION", "install_express_section_status_truth_v26", "reconcile_section_status_truth"]
