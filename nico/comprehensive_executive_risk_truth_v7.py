from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive_executive_risk_truth.v7"


def reconcile_executive_risk_truth(assessment: dict[str, Any]) -> dict[str, Any]:
    """Align executive risk wording with the final shared-control score disposition."""
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    static = next((item for item in sections if item.get("id") == "static_analysis"), None)
    static_scored = bool(
        static
        and isinstance(static.get("score_value"), (int, float))
        and static.get("exclude_from_maturity") is not True
    )

    rewritten = False
    risks = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    if static_scored:
        for risk in risks:
            title = str(risk.get("title") or "").strip().casefold()
            if title != "static-analysis evidence incomplete":
                continue
            risk.update(
                {
                    "title": "Static-analysis assurance remains review-limited",
                    "impact": (
                        "Accepted Semgrep, TypeScript, and bounded triage evidence supports a conservative technical signal, "
                        "but incomplete live analyzer acceptance prevents verified assurance."
                    ),
                    "recommendation": (
                        "Repair the failed analyzer boundary, complete rule-level candidate triage, and retain two consecutive "
                        "exact-SHA successful runs before promoting the control to verified assurance."
                    ),
                }
            )
            rewritten = True

    assessment["executive_risk_register"] = risks
    assessment["comprehensive_executive_risk_truth"] = {
        "status": "complete",
        "version": VERSION,
        "static_is_bounded_scored": static_scored,
        "static_risk_wording_reconciled": rewritten or not static_scored,
        "technical_score_not_conflated_with_assurance": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return assessment


__all__ = ["VERSION", "reconcile_executive_risk_truth"]
