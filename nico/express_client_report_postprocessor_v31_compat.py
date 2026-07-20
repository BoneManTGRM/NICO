from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_client_report_postprocessor.v32.compat"
_PATCH_MARKER = "_nico_express_terminal_truth_v32"
_NOT_SCORED_IDS = {
    "scanner_worker_evidence",
    "client_acceptance",
    "client_human_acceptance",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_not_scored_sections(result: dict[str, Any]) -> None:
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id not in _NOT_SCORED_IDS:
            continue
        if section_id != "scanner_worker_evidence" and _text(section.get("status")).casefold() == "green":
            continue
        section["score"] = None
        section["presented_score"] = None
        section["directly_scored"] = False
        section["exclude_from_maturity"] = True
        section["score_label"] = "NOT SCORED"


def _reconcile_terminal_progress(result: dict[str, Any]) -> None:
    progress = result.get("progress")
    if not isinstance(progress, list):
        return
    overall = _text(result.get("status")).casefold()
    reports = result.get("reports")
    report_ready = isinstance(reports, dict) and any(reports.get(key) for key in ("markdown", "html", "pdf_base64"))
    final_complete = any(
        isinstance(item, dict)
        and _text(item.get("step")).casefold() in {"complete", "completed"}
        and _text(item.get("status")).casefold() in {"complete", "completed", "success", "passed"}
        for item in progress
    )
    automated_complete = overall in {"complete", "completed", "success", "review_required"} and report_ready and final_complete
    if not automated_complete:
        return

    for item in progress:
        if not isinstance(item, dict):
            continue
        step = _text(item.get("step")).casefold()
        if "truth" in step and "review" in step and _text(item.get("status")).casefold() in {"running", "queued", "pending"}:
            item["status"] = "complete"
            item["message"] = "Automated truth and consistency gates completed. The report package is awaiting required human review."
        if step in {"complete", "completed"}:
            item["step"] = "automated_complete"
            item["status"] = "complete"
            item["message"] = "Automated assessment stages and draft report artifacts are complete. Required human review is pending."

    result["status"] = "complete"
    result["terminal_state"] = "human_review_pending"
    result["automated_stages_complete"] = True
    result["human_review_status"] = "pending"
    result["human_review_required"] = True
    result["client_ready"] = False
    result["client_delivery_allowed"] = False


def install_express_client_report_postprocessor_v31_compat() -> dict[str, Any]:
    from nico import express_client_report_postprocessor_v27 as target

    def replace_paragraph_section(markdown: str, heading: str, paragraph: str) -> str:
        replacement = f"## {heading}\n{paragraph}\n"
        pattern = rf"## {re.escape(heading)}\n[\s\S]*?(?=\n## |\n### |\Z)"
        if re.search(pattern, markdown):
            return re.sub(pattern, replacement.rstrip(), markdown)
        return markdown.rstrip() + "\n\n" + replacement

    previous_risk_register = target._risk_register

    def risk_register(result: dict[str, Any]) -> list[str]:
        risks = list(previous_risk_register(result))
        required = (
            "Scanner-clean claims require current-run artifacts to remain attached and parseable. "
            "Mitigation: retain the exact-run scanner artifacts, verify their digests, and block clean claims when an artifact is missing or unreadable."
        )
        if not any("scanner-clean claims require current-run artifacts" in str(item).casefold() for item in risks):
            risks.insert(0, required)
        return risks[:6]

    if not getattr(target.prepare_express_client_report, _PATCH_MARKER, False):
        previous_prepare: Callable[[dict[str, Any]], dict[str, Any]] = target.prepare_express_client_report

        @wraps(previous_prepare)
        def prepare(result: dict[str, Any]) -> dict[str, Any]:
            _normalize_not_scored_sections(result)
            prepared = previous_prepare(result)
            _normalize_not_scored_sections(prepared)
            _reconcile_terminal_progress(prepared)
            return prepared

        setattr(prepare, _PATCH_MARKER, True)
        setattr(prepare, "_nico_previous", previous_prepare)
        target.prepare_express_client_report = prepare

    if not getattr(target.postprocess_express_client_reports, _PATCH_MARKER, False):
        previous_postprocess: Callable[[dict[str, Any]], dict[str, Any]] = target.postprocess_express_client_reports

        @wraps(previous_postprocess)
        def postprocess(result: dict[str, Any]) -> dict[str, Any]:
            _normalize_not_scored_sections(result)
            _reconcile_terminal_progress(result)
            finalized = previous_postprocess(result)
            _normalize_not_scored_sections(finalized)
            _reconcile_terminal_progress(finalized)
            finalized.setdefault("express_client_report_postprocessor", {})["terminal_truth_reconciled"] = True
            finalized["express_client_report_postprocessor"]["not_scored_payload_normalized"] = True
            return finalized

        setattr(postprocess, _PATCH_MARKER, True)
        setattr(postprocess, "_nico_previous", previous_postprocess)
        target.postprocess_express_client_reports = postprocess

    try:
        from nico import express_pdf_renderer_truth_v21 as renderer

        if not getattr(renderer._score_records, _PATCH_MARKER, False):
            previous_score_records = renderer._score_records

            @wraps(previous_score_records)
            def score_records(result: dict[str, Any]) -> list[dict[str, Any]]:
                _normalize_not_scored_sections(result)
                records = previous_score_records(result)
                return [
                    item
                    for item in records
                    if _text(item.get("section_id")).casefold() not in _NOT_SCORED_IDS
                    and item.get("directly_scored") is not False
                ]

            setattr(score_records, _PATCH_MARKER, True)
            setattr(score_records, "_nico_previous", previous_score_records)
            renderer._score_records = score_records
    except ImportError:
        pass

    target._replace_paragraph_section = replace_paragraph_section
    target._risk_register = risk_register
    target.VERSION = "nico.express_client_report_postprocessor.v32"
    return {
        "status": "installed",
        "version": VERSION,
        "heading_boundary_preserved": True,
        "scanner_clean_risk_disclosure_preserved": True,
        "terminal_truth_reconciled": True,
        "not_scored_payload_normalized": True,
        "not_scored_pdf_records_excluded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_normalize_not_scored_sections",
    "_reconcile_terminal_progress",
    "install_express_client_report_postprocessor_v31_compat",
]
