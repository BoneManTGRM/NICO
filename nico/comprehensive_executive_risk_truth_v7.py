from __future__ import annotations

from typing import Any

from nico.phase12_report_remediation_v1 import remediate_assessment

VERSION = "nico.comprehensive_executive_risk_truth.v8"


def reconcile_executive_risk_truth(assessment: dict[str, Any]) -> dict[str, Any]:
    """Align executive risk wording with final control truth and canonicalize report findings."""
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    static = next((item for item in sections if item.get("id") == "static_analysis"), None)
    static_scored = bool(
        static
        and isinstance(static.get("score_value"), (int, float))
        and static.get("exclude_from_maturity") is not True
    )

    contradictory_risk_found = False
    rewritten = False
    risks = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    if static_scored:
        for risk in risks:
            title = str(risk.get("title") or "").strip().casefold()
            if title != "static-analysis evidence incomplete":
                continue
            contradictory_risk_found = True
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
        "contradictory_static_risk_found": contradictory_risk_found,
        "static_risk_wording_reconciled": rewritten or not contradictory_risk_found,
        "technical_score_not_conflated_with_assurance": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    identity = assessment.get("identity")
    commit_sha = str(
        assessment.get("commit_sha")
        or (identity.get("commit_sha") if isinstance(identity, dict) else "")
        or ""
    )
    return remediate_assessment(assessment, commit_sha=commit_sha)


__all__ = ["VERSION", "reconcile_executive_risk_truth"]
