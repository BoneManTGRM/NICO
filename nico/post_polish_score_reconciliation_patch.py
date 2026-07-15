from __future__ import annotations

import sys
from typing import Any, Callable

PATCH_VERSION = "nico.post_polish_score_reconciliation.v1"
_MARKER = "_nico_post_polish_score_reconciliation_v1"
_EXPLICIT_TEST_ABSENCE = (
    "no test-path signals were found",
    "no test path signals were found",
)


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in result.get("sections", []) or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _remove_contradicted_test_absence(result: dict[str, Any]) -> int:
    """Remove explicit repository-wide absence wording when tree proof is positive."""

    stage = result.get("final_score_reconciliation")
    if not isinstance(stage, dict) or int(stage.get("recursive_tree_test_path_count") or 0) <= 0:
        return 0
    code = _section(result, "code_audit")
    if not code:
        return 0

    removed = 0
    for key in ("evidence", "verified_claims", "findings", "unavailable"):
        values = code.get(key)
        if not isinstance(values, list):
            continue
        kept = []
        for item in values:
            lowered = str(item or "").lower()
            if any(fragment in lowered for fragment in _EXPLICIT_TEST_ABSENCE):
                removed += 1
                continue
            kept.append(item)
        code[key] = kept
    return removed


def reconcile_after_polish(result: dict[str, Any]) -> dict[str, Any]:
    """Run evidence reconciliation after the last score-mutating polish pass."""

    if result.get("status") != "complete":
        return result

    from nico import final_report_consistency as consistency
    from nico.final_score_reconciliation_patch import reconcile_final_evidence_scores

    reconciled = reconcile_final_evidence_scores(result)
    removed_absence_claims = _remove_contradicted_test_absence(reconciled)
    reconciled["executive_summary"] = consistency._build_executive_summary(reconciled)
    maturity = reconciled.get("maturity_signal") if isinstance(reconciled.get("maturity_signal"), dict) else {}
    source = reconciled.get("score_source_of_truth") if isinstance(reconciled.get("score_source_of_truth"), dict) else {}
    source.update(
        {
            "field": "maturity_signal",
            "level": maturity.get("level"),
            "score": maturity.get("score"),
            "final_stage": "post_polish_score_reconciliation",
            "rule": (
                "The client-visible score, score details, executive summary, and exports are rebuilt after the final "
                "report-polishing and QA stage so no earlier section value can survive as a stale score source."
            ),
        }
    )
    reconciled["score_source_of_truth"] = source
    stage = reconciled.get("final_score_reconciliation") if isinstance(reconciled.get("final_score_reconciliation"), dict) else {}
    stage["final_stage"] = "post_polish"
    stage["post_polish_applied"] = True
    stage["exports_rebuilt_after_post_polish"] = True
    stage["contradicted_test_absence_claims_removed"] = removed_absence_claims
    reconciled["final_score_reconciliation"] = stage
    consistency._rebuild_reports(reconciled)
    return reconciled


def install_post_polish_score_reconciliation_patch() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], dict[str, Any]] = assessment_quality.polish_express_result
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "post_polish_reconciliation": True,
            "executive_summary_refreshed": True,
            "score_details_refreshed": True,
            "exports_rebuilt": True,
            "contradicted_test_absence_removed": True,
        }
    original = current

    def polish_with_final_reconciliation(result: dict[str, Any]) -> dict[str, Any]:
        polished = original(result)
        return reconcile_after_polish(polished)

    setattr(polish_with_final_reconciliation, _MARKER, True)
    setattr(polish_with_final_reconciliation, "_nico_previous", original)
    assessment_quality.polish_express_result = polish_with_final_reconciliation

    rebound = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "polish_express_result", None) is original:
                setattr(module, "polish_express_result", polish_with_final_reconciliation)
                rebound += 1
        except Exception:
            continue

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "post_polish_reconciliation": True,
        "executive_summary_refreshed": True,
        "score_details_refreshed": True,
        "exports_rebuilt": True,
        "contradicted_test_absence_removed": True,
        "rebound_import_references": rebound,
        "score_inflation_allowed": False,
        "guardrail": (
            "The post-polish pass may only apply the existing evidence-bound reconciliation rules. It cannot create "
            "scanner proof, test evidence, acceptance, or client-ready state that is absent from the report."
        ),
    }


__all__ = [
    "PATCH_VERSION",
    "install_post_polish_score_reconciliation_patch",
    "reconcile_after_polish",
]
