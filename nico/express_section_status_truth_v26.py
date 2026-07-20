from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_section_status_truth.v26.1"
_PATCH_MARKER = "_nico_express_section_status_truth_v26"
_REVIEW_TERMS = (
    "status=failed",
    "status=timeout",
    "status=timed_out",
    " ended with status failed",
    " ended with status timeout",
    " returned failed",
    " returned timeout",
    " requires human triage",
    " requiring human triage",
    " exact-snapshot scanner unavailable",
    " analyzer unavailable for this run",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _has_unresolved(section: dict[str, Any]) -> bool:
    """Detect unresolved current-run analyzer evidence without overriding superseding truth.

    Generic historical notes such as "human review required", an inherited
    "unavailable" sentence, or the mere word "findings" are not sufficient to
    downgrade a section that a later evidence reconciliation legitimately
    promoted to green.
    """

    values = [*(section.get("findings") or []), *(section.get("unavailable") or [])]
    return any(any(term in _text(value) for term in _REVIEW_TERMS) for value in values)


def _client_acceptance_is_approved(section: dict[str, Any], result: dict[str, Any]) -> bool:
    top_level = result.get("client_acceptance") if isinstance(result.get("client_acceptance"), dict) else {}
    statuses = {
        _text(section.get("status")),
        _text(section.get("acceptance_status")),
        _text(top_level.get("status")),
    }
    score = section.get("score")
    try:
        score_is_positive = float(score or 0) > 0
    except (TypeError, ValueError):
        score_is_positive = False
    return bool(statuses & {"approved", "accepted", "green", "verified"}) and score_is_positive


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
            prior_score = section.get("score")
            if prior_score is not None and "diagnostic_finding_count" not in section:
                section["diagnostic_finding_count"] = prior_score
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
            if _client_acceptance_is_approved(section, output):
                section.update(
                    {
                        "status": "green",
                        "display_status": "GREEN · HUMAN APPROVED",
                        "directly_scored": True,
                        "score_treatment": "human_approved_scored_control",
                    }
                )
            else:
                section.update(
                    {
                        "status": "gray",
                        "display_status": "GRAY · NOT SCORED",
                        "directly_scored": False,
                        "score_treatment": "not_scored_pending_approval",
                        "presented_score": 0,
                        "presented": 0,
                        "score": 0,
                    }
                )
            changed.append(section_id or "client_acceptance")
            continue
        if str(section.get("status") or "").casefold() == "green" and _has_unresolved(section):
            section["status"] = "yellow"
            section["display_status"] = "YELLOW · REVIEW LIMITED"
            section["status_reason"] = "Unresolved current-run failed, timed-out, unavailable, or human-triage analyzer evidence prevents a GREEN presentation state."
            changed.append(section_id or label)

    output["sections"] = sections
    output["express_section_status_truth"] = {
        "status": "complete",
        "version": VERSION,
        "changed_sections": changed,
        "green_requires_no_unresolved_current_run_analyzer_evidence": True,
        "superseding_clean_evidence_preserved": True,
        "scanner_worker_not_scored": True,
        "unapproved_client_acceptance_not_scored": True,
        "approved_client_acceptance_preserved": True,
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
