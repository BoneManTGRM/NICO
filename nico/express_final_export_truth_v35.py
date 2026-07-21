from __future__ import annotations

import re
import sys
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_final_export_truth.v35"
_PATCH_MARKER = "_nico_express_final_export_truth_v35"
_NOT_SCORED_IDS = {
    "scanner_worker",
    "scanner_worker_evidence",
    "client_acceptance",
    "client_human_acceptance",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id")).casefold()
    status = _text(section.get("presented_status") or section.get("status")).casefold()
    if section_id in {"scanner_worker", "scanner_worker_evidence"} or status == "supplemental":
        return True
    if section_id in {"client_acceptance", "client_human_acceptance"} and status != "green":
        return True
    return section.get("directly_scored") is False and section.get(
        "presented_score", section.get("score")
    ) is None


def reconcile_final_express_scores(result: dict[str, Any]) -> dict[str, Any]:
    """Recompute presentation scores from the final canonical evidence state."""

    from nico.express_evidence_specific_scoring_v33 import reconcile_express_scores
    from nico.express_source_score_refresh_v34 import refresh_canonical_source_scores

    refresh_canonical_source_scores(result)
    reconcile_express_scores(result)
    refresh_canonical_source_scores(result)
    result["express_final_score_truth"] = {
        "status": "complete",
        "version": VERSION,
        "final_canonical_scores_reconciled": True,
        "stale_first_pass_source_scores_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def _normalize_section_payloads(result: dict[str, Any]) -> None:
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or not _not_scored(section):
            continue
        section["score"] = None
        section["source_score"] = None
        section["presented_score"] = None
        section["directly_scored"] = False
        section["exclude_from_maturity"] = True
        section["score_label"] = "NOT SCORED"
        if _text(section.get("id")).casefold() in {"scanner_worker", "scanner_worker_evidence"}:
            section["presented_status"] = "supplemental"


def _rewrite_not_scored_document(document: str, result: dict[str, Any], *, html: bool = False) -> str:
    output = str(document or "")
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or not _not_scored(section):
            continue
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        if not label:
            continue
        status = _text(section.get("presented_status") or section.get("status") or "gray").upper()
        if _text(section.get("id")).casefold() in {"scanner_worker", "scanner_worker_evidence"}:
            status = "SUPPLEMENTAL"
        escaped = re.escape(label)
        if html:
            patterns = (
                rf"({escaped}\s*[—-]\s*)[A-Z]+\s*\((?:NONE|NULL|0|\d+)\s*/\s*100\)",
                rf"({escaped}[\s\S]{{0,140}}?)[A-Z]+\s*\((?:NONE|NULL|0)\s*/\s*100\)",
            )
        else:
            patterns = (
                rf"(###\s+{escaped}\s*[—-]\s*)[A-Z]+\s*\((?:NONE|NULL|0|\d+)\s*/\s*100\)",
                rf"(-\s+\*\*{escaped}\*\*:\s*)[^\n]*(?:NONE|NULL|0)\s*/\s*100[^\n]*",
            )
        replacement = rf"\1{status} (NOT SCORED)"
        for pattern in patterns:
            output = re.sub(pattern, replacement, output, flags=re.I)

    output = re.sub(r"\b(?:NONE|NULL)\s*/\s*100\b", "NOT SCORED", output, flags=re.I)
    return output


def normalize_final_express_exports(result: dict[str, Any]) -> dict[str, Any]:
    """Make Markdown and HTML consume the same final score/status truth."""

    from nico.express_evidence_specific_scoring_v33 import rewrite_cross_format_scores
    from nico.hosted_assessment import build_html

    _normalize_section_payloads(result)
    rewrite_cross_format_scores(result)

    reports = result.get("reports")
    if not isinstance(reports, dict):
        reports = {}
        result["reports"] = reports

    markdown = _rewrite_not_scored_document(str(reports.get("markdown") or ""), result)
    if markdown:
        reports["markdown"] = markdown
        reports["html"] = build_html(markdown)
    else:
        reports["html"] = _rewrite_not_scored_document(
            str(reports.get("html") or ""), result, html=True
        )

    markdown_upper = str(reports.get("markdown") or "").upper()
    html_upper = str(reports.get("html") or "").upper()
    leakage = any(token in markdown_upper or token in html_upper for token in ("NONE/100", "NULL/100"))
    result["express_final_export_truth"] = {
        "status": "blocked" if leakage else "complete",
        "version": VERSION,
        "markdown_html_share_final_truth": not leakage,
        "not_scored_numeric_leakage": leakage,
        "null_score_tokens_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    if leakage:
        raise RuntimeError("Express final export retained a null numeric score token")
    return result


def finalize_after_consistency(
    current: Callable[[dict[str, Any]], dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    finalized = current(result)
    if finalized.get("status") != "complete":
        return finalized

    from nico import final_report_consistency as finalizer
    from nico.express_cross_format_contract_v24 import build_cross_format_contract

    reconcile_final_express_scores(finalized)
    _normalize_section_payloads(finalized)
    finalizer.attach_score_details(finalized)
    # Rebuild every output only after the final canonical and presented scores
    # are settled. This second render is deliberate and bounded.
    finalizer._rebuild_reports(finalized)
    normalize_final_express_exports(finalized)
    build_cross_format_contract(finalized)
    return finalized


def install_express_final_export_truth_v35() -> dict[str, Any]:
    from nico import final_report_consistency as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target.finalize_express_result_consistency
    if getattr(current, _PATCH_MARKER, False):
        api_main = sys.modules.get("nico.api.main")
        if api_main is not None:
            api_main.finalize_express_result_consistency = current
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def finalize(result: dict[str, Any]) -> dict[str, Any]:
        return finalize_after_consistency(current, result)

    setattr(finalize, _PATCH_MARKER, True)
    setattr(finalize, "_nico_previous", current)
    target.finalize_express_result_consistency = finalize
    api_main = sys.modules.get("nico.api.main")
    if api_main is not None:
        api_main.finalize_express_result_consistency = finalize
    return {
        "status": "installed",
        "version": VERSION,
        "backend_finalizer_bound": True,
        "api_alias_rebound": api_main is not None,
        "second_render_after_final_scores": True,
        "null_score_tokens_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "finalize_after_consistency",
    "install_express_final_export_truth_v35",
    "normalize_final_express_exports",
    "reconcile_final_express_scores",
]
