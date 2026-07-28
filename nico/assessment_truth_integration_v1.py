from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from nico.final_assessment_truth_v1 import FinalAssessmentTruthV1, TruthViolation

VERSION = "nico.assessment_truth_integration.v1"


class FindingVerification(str, Enum):
    CANDIDATE = "candidate"
    REVIEW_REQUIRED = "review_required"
    VERIFIED = "verified"
    REPRODUCED = "reproduced"
    REMEDIATED = "remediated"
    FALSE_POSITIVE = "false_positive"


@dataclass(frozen=True)
class ScoreLedger:
    observed_performance: float
    coverage_adjusted_maturity: float
    evidence_adjusted_readiness: float
    scored_weight: float
    configured_weight: float
    penalties: tuple[Mapping[str, Any], ...]
    ceilings: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_performance": round(self.observed_performance, 2),
            "coverage_adjusted_maturity": round(self.coverage_adjusted_maturity, 2),
            "evidence_adjusted_readiness": round(self.evidence_adjusted_readiness, 2),
            "scored_weight": round(self.scored_weight, 4),
            "configured_weight": round(self.configured_weight, 4),
            "penalties": [dict(item) for item in self.penalties],
            "ceilings": [dict(item) for item in self.ceilings],
            "formula_version": VERSION,
        }


def calculate_score_ledger(
    *,
    scored_contribution: float,
    scored_weight: float,
    configured_weight: float = 1.0,
    penalties: Sequence[Mapping[str, Any]] = (),
    ceilings: Sequence[Mapping[str, Any]] = (),
) -> ScoreLedger:
    if configured_weight <= 0 or scored_weight < 0 or scored_weight > configured_weight:
        raise TruthViolation("Invalid score weights")
    observed = 0.0 if scored_weight == 0 else scored_contribution / scored_weight
    coverage_adjusted = scored_contribution / configured_weight
    penalty_total = sum(float(item.get("points", 0.0)) for item in penalties)
    readiness = max(0.0, coverage_adjusted - penalty_total)
    applicable_ceilings = [float(item["maximum"]) for item in ceilings if item.get("applies", True)]
    if applicable_ceilings:
        readiness = min(readiness, min(applicable_ceilings))
        coverage_adjusted = min(coverage_adjusted, min(applicable_ceilings))
    return ScoreLedger(
        observed_performance=max(0.0, min(100.0, observed)),
        coverage_adjusted_maturity=max(0.0, min(100.0, coverage_adjusted)),
        evidence_adjusted_readiness=max(0.0, min(100.0, readiness)),
        scored_weight=scored_weight,
        configured_weight=configured_weight,
        penalties=tuple(dict(item) for item in penalties),
        ceilings=tuple(dict(item) for item in ceilings),
    )


def enforce_finding_verification(findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in findings:
        item = dict(raw)
        status = FindingVerification(str(item.get("verification_status") or "candidate"))
        severity = str(item.get("severity") or item.get("priority") or "P3").upper()
        title = str(item.get("title") or "")
        if "$" in title or "{" in title or "}" in title:
            raise TruthViolation(f"Unresolved placeholder in finding title: {title}")
        if severity == "P0" and status not in {FindingVerification.VERIFIED, FindingVerification.REPRODUCED}:
            item["severity"] = "P1"
            item["priority"] = "P1"
            item["severity_adjustment_reason"] = "P0 requires verified or reproduced evidence"
        item["verification_status"] = status.value
        output.append(item)
    return output


def freeze_assessment(source: Mapping[str, Any], ledger: ScoreLedger) -> FinalAssessmentTruthV1:
    payload = dict(source)
    payload.update(ledger.as_dict())
    payload["technical_score"] = ledger.coverage_adjusted_maturity
    payload["evidence_adjusted_score"] = ledger.evidence_adjusted_readiness
    raw_findings = payload.get("canonical_findings") or payload.get("decision_grade_findings_register") or []
    payload["canonical_findings"] = enforce_finding_verification(raw_findings)
    return FinalAssessmentTruthV1.freeze(payload)


__all__ = [
    "FindingVerification",
    "ScoreLedger",
    "calculate_score_ledger",
    "enforce_finding_verification",
    "freeze_assessment",
]
