from __future__ import annotations

from copy import deepcopy
from typing import Any


_INSTALLED = False
FULL_REPORT_VERSION = "full-assessment-draft-v2"
FULL_DETAIL_LEVEL = 3
FULL_INCLUDED_MODULES = (
    "express_baseline",
    "mid_evidence_and_decision_support",
    "cross_domain_synthesis",
    "risk_and_remediation_planning",
    "verification_and_rollback",
    "final_review_preparation",
    "broad_evidence_appendix",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def _append_unique(values: list[Any], value: str) -> None:
    if value and value not in values:
        values.append(value)


def build_full_executive_detail(assessment: dict[str, Any]) -> dict[str, Any]:
    """Derive Full-only decision support from retained assessment truth."""

    sections = [item for item in _list(assessment.get("sections")) if isinstance(item, dict)]
    prioritized_risks: list[dict[str, Any]] = []
    remediation_plan: list[dict[str, Any]] = []
    verification_plan: list[str] = []
    evidence_appendix: list[dict[str, Any]] = []

    for section in sections:
        section_id = str(section.get("id") or "unknown")
        label = str(section.get("label") or section_id)
        status = str(section.get("status") or section.get("truth_status") or "gray").lower()
        findings = _texts(section.get("findings"))
        unavailable = _texts(section.get("unavailable")) + _texts(section.get("unverified_claims"))
        evidence = _texts(section.get("evidence")) + _texts(section.get("verified_claims"))

        for finding in findings:
            prioritized_risks.append(
                {
                    "section_id": section_id,
                    "section": label,
                    "status": status,
                    "finding": finding,
                    "human_review_required": True,
                }
            )
            remediation_plan.append(
                {
                    "section_id": section_id,
                    "section": label,
                    "action": f"Review and remediate: {finding}",
                    "production_change_allowed": False,
                    "verification_required": True,
                }
            )
            verification_plan.append(f"Re-run evidence collection for {label} after reviewed remediation.")

        evidence_appendix.append(
            {
                "section_id": section_id,
                "section": label,
                "status": status,
                "evidence_count": len(evidence),
                "finding_count": len(findings),
                "limitation_count": len(unavailable),
            }
        )

    return {
        "report_tier": "full",
        "report_version": FULL_REPORT_VERSION,
        "detail_level": FULL_DETAIL_LEVEL,
        "detail_relationship": "includes Mid depth and adds cross-domain synthesis, remediation, verification, rollback, and final-review preparation",
        "included_modules": list(FULL_INCLUDED_MODULES),
        "cross_domain_synthesis": {
            "section_count": len(sections),
            "risk_bearing_sections": sorted({item["section"] for item in prioritized_risks}),
            "sections_with_limitations": [item["section"] for item in evidence_appendix if item["limitation_count"]],
        },
        "risk_and_remediation_plan": {
            "prioritized_risks": prioritized_risks[:20],
            "recommended_actions": remediation_plan[:20],
            "automatic_production_change": False,
        },
        "verification_and_rollback": {
            "verification_steps": verification_plan[:20],
            "rollback_required_for_production_change": True,
            "production_change_authorized": False,
        },
        "final_review_preparation": {
            "human_review_required": True,
            "approval_created": False,
            "client_delivery_allowed": False,
            "review_focus": [item["finding"] for item in prioritized_risks[:12]],
        },
        "evidence_appendix_summary": evidence_appendix,
    }


def attach_full_report_depth(assessment: dict[str, Any]) -> dict[str, Any]:
    """Attach Full depth before rendering so every format receives the detail.

    The added text is derived from retained sections. It does not alter section
    scores, evidence status, approval state, or client-delivery authority.
    """

    enriched = deepcopy(assessment)
    detail = build_full_executive_detail(enriched)
    synthesis = detail["cross_domain_synthesis"]
    risks = detail["risk_and_remediation_plan"]["prioritized_risks"]
    limitations = synthesis["sections_with_limitations"]

    enriched["report_version"] = FULL_REPORT_VERSION
    enriched["report_tier"] = "full"
    enriched["detail_level"] = FULL_DETAIL_LEVEL
    enriched["detail_relationship"] = detail["detail_relationship"]
    enriched["included_modules"] = deepcopy(detail["included_modules"])
    enriched["full_depth_contract"] = deepcopy(detail)

    depth_summary = (
        "Full-depth analysis reviewed "
        f"{synthesis['section_count']} retained assessment section(s), identified "
        f"{len(risks)} evidence-bound risk item(s), and retained "
        f"{len(limitations)} section(s) with unavailable or review-limited evidence. "
        "Remediation and verification guidance is advisory; production changes, approval, "
        "and client delivery remain blocked pending explicit human decisions."
    )
    summary = str(enriched.get("executive_summary") or "").strip()
    if depth_summary not in summary:
        enriched["executive_summary"] = f"{summary} {depth_summary}".strip()

    next_steps = list(_list(enriched.get("next_steps")))
    for item in detail["risk_and_remediation_plan"]["recommended_actions"][:8]:
        _append_unique(next_steps, str(item.get("action") or ""))
    for step in detail["verification_and_rollback"]["verification_steps"][:8]:
        _append_unique(next_steps, step)
    _append_unique(
        next_steps,
        "Require a reviewed rollback plan before any approved production change; this report does not authorize implementation.",
    )
    _append_unique(next_steps, "Complete final human review before approval or client delivery.")
    enriched["next_steps"] = next_steps
    enriched["human_review_required"] = True
    enriched["client_ready"] = False
    return enriched


def install_progressive_full_report_patch() -> None:
    """Make Full reports explicitly deeper than Mid without weakening gates."""

    global _INSTALLED
    if _INSTALLED:
        return

    from nico import full_assessment_idempotent_handlers as handler_module
    from nico import full_assessment_trust_pipeline as trust_pipeline

    original_prepare = trust_pipeline.prepare_full_assessment_trust
    original_reports_handler = handler_module._reports_handler

    def progressive_prepare(
        assessment: dict[str, Any],
        scanner_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = original_prepare(assessment, scanner_evidence)
        return attach_full_report_depth(prepared)

    def progressive_reports_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = original_reports_handler(context, outputs)
        if result.get("status") != "complete":
            return result

        scoring = _dict(outputs.get("scoring"))
        assessment = _dict(scoring.get("assessment"))
        detail = _dict(assessment.get("full_depth_contract")) or build_full_executive_detail(assessment)

        package = _dict(result.get("report_package"))
        reports = _dict(result.get("reports"))
        evidence = _dict(result.get("evidence"))

        package["report_version"] = FULL_REPORT_VERSION
        package["report_tier"] = "full"
        package["detail_level"] = FULL_DETAIL_LEVEL
        package["detail_relationship"] = detail["detail_relationship"]
        package["included_modules"] = deepcopy(detail["included_modules"])
        package["cross_domain_synthesis"] = deepcopy(detail["cross_domain_synthesis"])
        package["risk_and_remediation_plan"] = deepcopy(detail["risk_and_remediation_plan"])
        package["verification_and_rollback"] = deepcopy(detail["verification_and_rollback"])
        package["final_review_preparation"] = deepcopy(detail["final_review_preparation"])
        package["evidence_appendix_summary"] = deepcopy(detail["evidence_appendix_summary"])

        reports["report_tier"] = "Full"
        reports["detail_level"] = FULL_DETAIL_LEVEL
        reports["full_depth_contract"] = deepcopy(detail)

        evidence["report_version"] = FULL_REPORT_VERSION
        evidence["report_tier"] = "full"
        evidence["detail_level"] = FULL_DETAIL_LEVEL
        evidence["client_delivery_allowed"] = False

        result["report_package"] = package
        result["reports"] = reports
        result["evidence"] = evidence
        return result

    trust_pipeline.prepare_full_assessment_trust = progressive_prepare
    handler_module._reports_handler = progressive_reports_handler
    _INSTALLED = True
