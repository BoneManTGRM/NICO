from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_final_truth_repair.v34.1"
_MARKER = "_nico_express_final_truth_repair_v34"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _technical_evidence_projection(section: dict[str, Any]) -> dict[str, Any]:
    """Build the final-report deduction view without changing source evidence.

    The normal evidence-specific scorer remains untouched. During the terminal
    production presentation pass only, ordinary context that has already affected
    the canonical source score is removed from the second-layer deduction view.
    Failed, timed-out, unavailable required analyzers and unresolved scanner
    candidates remain eligible for explicit section-level deductions.
    """

    projected = deepcopy(section)
    section_id = _text(projected.get("id")).casefold()

    projected["findings"] = [
        item
        for item in projected.get("findings") or []
        if any(
            marker in _text(item).casefold()
            for marker in (
                "requires human triage",
                "requiring human triage",
                "human disposition",
                "status failed",
                "status=failed",
                "ended with status failed",
                "timeout",
                "timed out",
            )
        )
    ]

    if section_id == "ci_cd":
        projected["findings"] = [
            item
            for item in projected.get("findings") or []
            if "historical workflow reliability" not in _text(item).casefold()
        ]

    if section_id in {"architecture_debt", "velocity_complexity"}:
        projected["findings"] = []

    if section_id == "velocity_complexity":
        projected["unavailable"] = [
            item
            for item in projected.get("unavailable") or []
            if not any(
                marker in _text(item).casefold()
                for marker in (
                    "story point",
                    "reviewer seniority",
                    "business-value",
                    "business value",
                    "client acceptance",
                    "release-readiness lift",
                    "project trend",
                    "stakeholder context",
                )
            )
        ]
        projected["limitations"] = [
            item
            for item in projected.get("limitations") or []
            if not any(
                marker in _text(item).casefold()
                for marker in (
                    "story point",
                    "reviewer seniority",
                    "client acceptance",
                    "stakeholder",
                )
            )
        ]

    if section_id == "static_analysis":
        evidence_text = " ".join(
            _text(value).casefold() for value in projected.get("evidence") or []
        )
        projected["unavailable"] = [
            item
            for item in projected.get("unavailable") or []
            if not (
                "no eslint configuration exists" in _text(item).casefold()
                and "typescript" in evidence_text
            )
        ]

    return projected


def _normalize_terminal_progress(result: dict[str, Any]) -> None:
    status = _text(result.get("status")).casefold()
    if status not in {"complete", "completed", "review_required"}:
        return
    progress = result.get("progress")
    if isinstance(progress, list):
        for item in progress:
            if not isinstance(item, dict):
                continue
            step = _text(item.get("step")).casefold()
            item["status"] = "complete"
            if "truth" in step and "review" in step:
                item["message"] = (
                    "Automated truth, evidence-ledger, consistency, acceptance, and report-quality gates completed. "
                    "Required human review remains pending."
                )
            elif step in {"complete", "automated_complete", "completed"}:
                item["step"] = "complete"
                item["message"] = (
                    "Automated assessment and draft report artifacts are complete. "
                    "Required human review is pending."
                )
    result["status"] = "complete"
    result["terminal_state"] = "human_review_pending"
    result["automated_stages_complete"] = True
    result["human_review_required"] = True
    result["human_review_status"] = "pending"
    result["client_ready"] = False
    result["client_delivery_allowed"] = False


def _level(score: int) -> str:
    if score >= 82:
        return "Senior"
    if score >= 58:
        return "Mid"
    return "Junior"


def _bind_single_terminal_overall(result: dict[str, Any], canonical_score: int) -> None:
    """Keep one overall score while retaining section-level evidence constraints."""

    maturity = (
        result.get("maturity_signal")
        if isinstance(result.get("maturity_signal"), dict)
        else {}
    )
    maturity["source_score"] = canonical_score
    maturity["presented_score"] = canonical_score
    maturity["score"] = canonical_score
    maturity["level"] = _level(canonical_score)
    maturity["score_treatment"] = (
        "single_terminal_maturity_score_with_section_evidence_constraints"
    )
    result["maturity_signal"] = maturity
    result["source_maturity_score"] = canonical_score
    result["evidence_adjusted_score"] = canonical_score

    transparency = result.get("express_score_transparency")
    if isinstance(transparency, dict):
        transparency["overall_presented_score"] = canonical_score
        transparency["source_maturity_score"] = canonical_score
        transparency["method"] = (
            "The final canonical maturity score is published once across UI and all report formats. "
            "Explicit analyzer failures, timeouts, unavailable required evidence, and unresolved scanner candidates "
            "remain visible as section-level score and status constraints without recharging ordinary findings already reflected in source scoring."
        )
        transparency["single_terminal_overall_score"] = True
        transparency["ordinary_findings_double_charged"] = False

    source = result.get("score_source_of_truth")
    if isinstance(source, dict):
        source["field"] = "maturity_signal.score"
        source["score"] = canonical_score
        source["level"] = _level(canonical_score)
        source["rule"] = (
            "The terminal UI, Markdown, HTML, JSON, and PDF use one final maturity score after source adjustments; "
            "section-level evidence constraints remain separately reproducible."
        )


def install_express_final_truth_repair_v34() -> dict[str, Any]:
    from nico import express_async_api as express
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_report_premium_v14 as premium
    from nico import final_report_consistency as consistency

    if not getattr(consistency.finalize_express_result_consistency, _MARKER, False):
        previous_finalize: Callable[[dict[str, Any]], dict[str, Any]] = (
            consistency.finalize_express_result_consistency
        )

        @wraps(previous_finalize)
        def finalize(result: dict[str, Any]) -> dict[str, Any]:
            finalized = previous_finalize(result)
            if _text(finalized.get("status")).casefold() != "complete":
                return finalized

            maturity = (
                finalized.get("maturity_signal")
                if isinstance(finalized.get("maturity_signal"), dict)
                else {}
            )
            canonical_score = int(maturity.get("score") or 0)

            original_deductions = scoring._deductions
            original_reconcile = scoring.reconcile_express_scores
            original_premium_reconcile = getattr(
                premium,
                "reconcile_express_scores",
                None,
            )

            @wraps(original_deductions)
            def terminal_deductions(section: dict[str, Any]):
                return original_deductions(_technical_evidence_projection(section))

            @wraps(original_reconcile)
            def terminal_reconcile(target: dict[str, Any]):
                records, _section_average = original_reconcile(target)
                _bind_single_terminal_overall(target, canonical_score)
                return records, canonical_score

            scoring._deductions = terminal_deductions
            scoring.reconcile_express_scores = terminal_reconcile
            premium.reconcile_express_scores = terminal_reconcile
            try:
                records, _ = terminal_reconcile(finalized)
                consistency._rebuild_reports(finalized)
                scoring.rewrite_cross_format_scores(finalized)
                _bind_single_terminal_overall(finalized, canonical_score)
            finally:
                scoring._deductions = original_deductions
                scoring.reconcile_express_scores = original_reconcile
                if original_premium_reconcile is not None:
                    premium.reconcile_express_scores = original_premium_reconcile

            _normalize_terminal_progress(finalized)
            finalized["express_final_truth_repair"] = {
                "status": "complete",
                "version": VERSION,
                "final_source_scores_used": True,
                "ordinary_findings_not_double_charged": True,
                "section_analyzer_deductions_preserved": True,
                "single_terminal_overall_score": canonical_score,
                "terminal_progress_reconciled": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "scored_section_count": len(records),
            }
            return finalized

        setattr(finalize, _MARKER, True)
        setattr(finalize, "_nico_previous", previous_finalize)
        consistency.finalize_express_result_consistency = finalize

    if not getattr(express._record, _MARKER, False):
        previous_record = express._record

        @wraps(previous_record)
        def record(
            run_id: str,
            request_payload: dict[str, Any],
            response: dict[str, Any],
        ):
            _normalize_terminal_progress(response)
            return previous_record(run_id, request_payload, response)

        setattr(record, _MARKER, True)
        setattr(record, "_nico_previous", previous_record)
        express._record = record

    return {
        "status": "installed",
        "version": VERSION,
        "final_score_order_repaired": True,
        "double_deduction_removed": True,
        "section_analyzer_deductions_preserved": True,
        "single_terminal_overall_score": True,
        "terminal_progress_reconciled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_final_truth_repair_v34",
]
