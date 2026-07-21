from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_source_score_refresh.v34"
_PATCH_MARKER = "_nico_express_source_score_refresh_v34"


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def refresh_canonical_source_scores(result: dict[str, Any]) -> dict[str, Any]:
    """Refresh presentation baselines from the current canonical score fields.

    Express can render more than once: an early polish pass and a later final
    consistency pass after scanner reconciliation and score adjustments.  The
    evidence-specific presentation layer previously retained the first pass in
    ``source_score`` and then reused it after the canonical ``score`` changed.
    That made the UI/PDF show stale values such as Code Audit 49 while the final
    canonical section score was 86.
    """

    refreshed_sections: list[str] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        canonical = section.get("score")
        if not _numeric(canonical):
            continue
        canonical_value = max(0, min(100, int(canonical)))
        if section.get("source_score") != canonical_value:
            refreshed_sections.append(str(section.get("id") or section.get("label") or "unknown"))
        section["source_score"] = canonical_value

    maturity = result.get("maturity_signal")
    if isinstance(maturity, dict) and _numeric(maturity.get("score")):
        maturity["source_score"] = max(0, min(100, int(maturity["score"])))

    result["express_source_score_refresh"] = {
        "status": "complete",
        "version": VERSION,
        "canonical_section_score_preferred": True,
        "canonical_maturity_score_preferred": True,
        "refreshed_sections": refreshed_sections,
        "stale_first_pass_source_scores_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def install_express_source_score_refresh_v34() -> dict[str, Any]:
    from nico import express_evidence_specific_scoring_v33 as target
    from nico import express_report_premium_v14 as premium

    current: Callable[[dict[str, Any]], tuple[list[Any], int]] = target.reconcile_express_scores
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def reconcile(result: dict[str, Any]) -> tuple[list[Any], int]:
        refresh_canonical_source_scores(result)
        records, overall = current(result)
        refresh_canonical_source_scores(result)
        transparency = result.get("express_score_transparency")
        if isinstance(transparency, dict):
            maturity = result.get("maturity_signal")
            transparency["source_maturity_score"] = (
                maturity.get("source_score") if isinstance(maturity, dict) else None
            )
            transparency["source_scores_refreshed_after_final_reconciliation"] = True
        return records, overall

    setattr(reconcile, _PATCH_MARKER, True)
    setattr(reconcile, "_nico_previous", current)
    target.reconcile_express_scores = reconcile
    premium.reconcile_express_scores = reconcile
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_section_score_preferred": True,
        "canonical_maturity_score_preferred": True,
        "premium_renderer_rebound": True,
        "human_review_required": True,
    }


__all__ = [
    "VERSION",
    "install_express_source_score_refresh_v34",
    "refresh_canonical_source_scores",
]
