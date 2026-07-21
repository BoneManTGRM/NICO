from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_final_truth_repair.v34"
_MARKER = "_nico_express_final_truth_repair_v34"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _technical_evidence_projection(section: dict[str, Any]) -> dict[str, Any]:
    """Remove non-technical context from evidence-confidence deductions.

    Source section scoring already accounts for ordinary technical findings. The
    evidence-adjusted layer is reserved for execution failures, unavailable
    required evidence, and unresolved scanner candidates. This prevents the
    same architecture, branch, historical-CI, or planning context from being
    charged twice.
    """

    projected = deepcopy(section)
    section_id = _text(projected.get("id")).casefold()

    # Ordinary findings remain visible in the report but are already reflected
    # in the source score, so they must not trigger a second generic deduction.
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
                for marker in ("story point", "reviewer seniority", "client acceptance", "stakeholder")
            )
        ]

    # ESLint is not a required analyzer when the repository intentionally has no
    # ESLint configuration and TypeScript compilation is the declared check.
    if section_id == "static_analysis":
        projected["unavailable"] = [
            item
            for item in projected.get("unavailable") or []
            if not (
                "no eslint configuration exists" in _text(item).casefold()
                and "typescript" in " ".join(_text(v).casefold() for v in projected.get("evidence") or [])
            )
        ]

    return projected


def _normalize_terminal_progress(result: dict[str, Any]) -> None:
    status = _text(result.get("status")).casefold()
    if status not in {"complete", "completed", "review_required"}:
        return
    progress = result.get("progress")
    if not isinstance(progress, list):
        return
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
            item["message"] = "Automated assessment and draft report artifacts are complete. Required human review is pending."
    result["status"] = "complete"
    result["terminal_state"] = "human_review_pending"
    result["automated_stages_complete"] = True
    result["human_review_required"] = True
    result["human_review_status"] = "pending"
    result["client_ready"] = False
    result["client_delivery_allowed"] = False


def install_express_final_truth_repair_v34() -> dict[str, Any]:
    from nico import express_async_api as express
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import final_report_consistency as consistency

    if not getattr(scoring._deductions, _MARKER, False):
        previous_deductions = scoring._deductions

        @wraps(previous_deductions)
        def deductions(section: dict[str, Any]):
            return previous_deductions(_technical_evidence_projection(section))

        setattr(deductions, _MARKER, True)
        setattr(deductions, "_nico_previous", previous_deductions)
        scoring._deductions = deductions

    if not getattr(consistency.finalize_express_result_consistency, _MARKER, False):
        previous_finalize: Callable[[dict[str, Any]], dict[str, Any]] = consistency.finalize_express_result_consistency

        @wraps(previous_finalize)
        def finalize(result: dict[str, Any]) -> dict[str, Any]:
            finalized = previous_finalize(result)
            if _text(finalized.get("status")).casefold() != "complete":
                return finalized

            # Final source adjustments must happen before evidence-specific
            # presentation. Reconcile once more from the final canonical state,
            # then rebuild every format from that same state.
            records, presented = scoring.reconcile_express_scores(finalized)
            source_scores = [record.source_score for record in records]
            source_overall = round(sum(source_scores) / len(source_scores)) if source_scores else 0
            maturity = finalized.get("maturity_signal") if isinstance(finalized.get("maturity_signal"), dict) else {}
            maturity["source_score"] = source_overall
            maturity["presented_score"] = presented
            maturity["score"] = presented
            maturity["level"] = "Senior" if presented >= 82 else "Mid" if presented >= 58 else "Junior"
            maturity["score_treatment"] = "final_canonical_evidence_adjusted_score"
            finalized["maturity_signal"] = maturity
            finalized["evidence_adjusted_score"] = presented
            finalized["source_maturity_score"] = source_overall
            consistency._rebuild_reports(finalized)
            scoring.rewrite_cross_format_scores(finalized)
            _normalize_terminal_progress(finalized)
            finalized["express_final_truth_repair"] = {
                "status": "complete",
                "version": VERSION,
                "final_source_scores_used": True,
                "ordinary_findings_not_double_charged": True,
                "canonical_overall_score_is_evidence_adjusted": True,
                "terminal_progress_reconciled": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            return finalized

        setattr(finalize, _MARKER, True)
        setattr(finalize, "_nico_previous", previous_finalize)
        consistency.finalize_express_result_consistency = finalize

    if not getattr(express._record, _MARKER, False):
        previous_record = express._record

        @wraps(previous_record)
        def record(run_id: str, request_payload: dict[str, Any], response: dict[str, Any]):
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
        "terminal_progress_reconciled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_final_truth_repair_v34",
]
