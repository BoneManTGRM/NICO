from __future__ import annotations

from typing import Any, Mapping

from nico.assessment_truth_integration_v1 import calculate_score_ledger, freeze_assessment
from nico.comprehensive_decision_grade_assessment_v6 import build_decision_grade_assessment
from nico.phase8_report_quality_v1 import harden_report_findings

VERSION = "nico.comprehensive_phase8_truth_gateway.v2"


def _section_weight(section_count: int) -> float:
    return 0.0 if section_count <= 0 else 1.0 / section_count


def _is_evidence_complete(section: Mapping[str, Any]) -> bool:
    unavailable = section.get("unavailable") or []
    evidence = section.get("evidence") or []
    return not unavailable and bool(evidence)


def _penalties(assessment: Mapping[str, Any]) -> list[dict[str, Any]]:
    penalties: list[dict[str, Any]] = []
    notes = assessment.get("unavailable_data_notes") or []
    if notes:
        penalties.append({"reason": "assessment evidence limitations", "points": min(15.0, 2.0 * len(notes))})
    metrics = assessment.get("limitation_metrics") or {}
    review_required = int(metrics.get("review_required_findings") or 0)
    if review_required:
        penalties.append({"reason": "unverified findings require review", "points": min(10.0, float(review_required))})
    return penalties


def _ceilings(assessment: Mapping[str, Any]) -> list[dict[str, Any]]:
    sections = assessment.get("sections") or []
    missing = [str(section.get("section_id") or section.get("id") or "unknown") for section in sections if not _is_evidence_complete(section)]
    ceilings: list[dict[str, Any]] = []
    if missing:
        ceilings.append({"reason": "one or more controls lack complete evidence", "maximum": 79.0, "applies": True, "controls": missing})
    return ceilings


def build_truth_bound_comprehensive_assessment(
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
    repo: dict[str, Any],
    complexity: dict[str, Any],
    scan: dict[str, Any],
) -> dict[str, Any]:
    assessment = build_decision_grade_assessment(
        repository=repository,
        commit_sha=commit_sha,
        run_id=run_id,
        repo=repo,
        complexity=complexity,
        scan=scan,
    )
    sections = assessment.get("sections") or []
    weight = _section_weight(len(sections))
    scored_sections = [section for section in sections if _is_evidence_complete(section)]
    scored_weight = weight * len(scored_sections)
    scored_contribution = sum(float(section.get("presented_score") or 0.0) * weight for section in scored_sections)
    ledger = calculate_score_ledger(
        scored_contribution=scored_contribution,
        scored_weight=scored_weight,
        configured_weight=1.0,
        penalties=_penalties(assessment),
        ceilings=_ceilings(assessment),
    )
    assessment["assessment_identity"] = {
        "provider": "github",
        "repository": repository,
        "immutable_revision": commit_sha,
        "run_id": run_id,
    }
    hardened = harden_report_findings(assessment.get("findings_register") or [])
    assessment["canonical_findings"] = hardened
    assessment["findings_register"] = hardened
    assessment["decision_grade_findings_register"] = hardened
    assessment["executive_risk_register"] = hardened
    assessment["approval_state"] = "FINAL-PENDING-APPROVAL"
    frozen = freeze_assessment(assessment, ledger).as_dict()

    canonical_findings = list(frozen.get("canonical_findings") or [])
    frozen["findings_register"] = canonical_findings
    frozen["decision_grade_findings_register"] = canonical_findings
    frozen["executive_risk_register"] = canonical_findings
    frozen["ranked_risks"] = [item.get("finding_id") for item in canonical_findings]

    frozen["maturity_signal"] = {
        **dict(assessment.get("maturity_signal") or {}),
        "observed_performance": frozen["observed_performance"],
        "coverage_adjusted_maturity": frozen["coverage_adjusted_maturity"],
        "evidence_adjusted_readiness": frozen["evidence_adjusted_readiness"],
        "score": frozen["coverage_adjusted_maturity"],
        "presented_score": frozen["coverage_adjusted_maturity"],
    }
    frozen["client_ready"] = False
    frozen["client_delivery_allowed"] = False
    frozen["truth_gateway_version"] = VERSION
    return frozen


__all__ = ["build_truth_bound_comprehensive_assessment"]
