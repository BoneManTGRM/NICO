from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Iterable

from pydantic import Field

from nico.decision_grade_types_v1 import (
    AcceptanceCriterion,
    Confidence,
    CostOfInaction,
    EvidenceRecord,
    FindingStatus,
    Priority,
    ResidualRisk,
    StrictModel,
    TimeWindow,
    WorkClassification,
)


class Finding(StrictModel):
    finding_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{2,80}$")
    title: str
    priority: Priority
    severity: str
    likelihood: str
    business_criticality: str
    confidence: Confidence
    finding_type: str
    status: FindingStatus = FindingStatus.OPEN
    scope: str
    evidence_ids: list[str] = Field(default_factory=list)
    factual_statement: str
    technical_interpretation: str
    business_impact: str = ""
    decision_areas: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    owner_role: str = ""
    effort: str = ""
    expected_impact: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    cost_of_inaction: CostOfInaction | None = None
    residual_risk: ResidualRisk | None = None
    roadmap_work_package_ids: list[str] = Field(default_factory=list)
    backlog_item_ids: list[str] = Field(default_factory=list)
    previous_run_relationship: str | None = None
    suppressed_or_excluded_reason: str | None = None
    benchmark_claim: str | None = None
    benchmark_source: str | None = None

    def fingerprint(self, evidence: Iterable[EvidenceRecord] = ()) -> str:
        evidence_map = {item.evidence_id: item for item in evidence}
        anchors: list[dict[str, str]] = []
        for evidence_id in sorted(self.evidence_ids):
            record = evidence_map.get(evidence_id)
            anchors.append({
                "category": (record.category if record else evidence_id).casefold(),
                "file_path": (record.location.file_path if record else "") or "",
                "symbol": ((record.location.symbol or record.location.control_name) if record else "") or "",
            })
        payload = {"finding_type": self.finding_type.casefold(), "scope": self.scope.casefold(), "anchors": anchors}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RoadmapWorkPackage(StrictModel):
    work_package_id: str
    title: str
    time_window: TimeWindow
    related_finding_ids: list[str] = Field(default_factory=list)
    objective: str
    implementation_steps: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    owner_role: str
    supporting_roles: list[str] = Field(default_factory=list)
    effort_range: str
    classification: WorkClassification
    expected_technical_impact: str
    expected_business_impact: str
    acceptance_criteria_ids: list[str] = Field(default_factory=list)
    residual_risk: str
    sequencing_rationale: str


def value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def risk_score(finding: Finding) -> int:
    priority = {"P0": 500, "P1": 400, "P2": 200, "P3": 100}.get(value(finding.priority), 0)
    severity = {"critical": 90, "high": 70, "medium": 40, "moderate": 40, "low": 10}.get(finding.severity.casefold(), 25)
    likelihood = {"almost_certain": 50, "likely": 40, "possible": 25, "unlikely": 10, "rare": 5}.get(finding.likelihood.casefold().replace(" ", "_"), 20)
    criticality = {"critical": 60, "high": 45, "medium": 25, "moderate": 25, "low": 10}.get(finding.business_criticality.casefold(), 20)
    confidence = {"high": 20, "moderate": 10, "low": 0}.get(value(finding.confidence), 0)
    override = 200 if value(finding.priority) in {"P0", "P1"} and any(area.casefold() in {"release", "security", "data_loss", "operations"} for area in finding.decision_areas) else 0
    return priority + severity + likelihood + criticality + confidence + override


def rank_executive_findings(findings: Iterable[Finding], limit: int = 7) -> list[Finding]:
    open_findings = [item for item in findings if value(item.status) == FindingStatus.OPEN.value]
    return sorted(open_findings, key=lambda item: (-risk_score(item), item.finding_id))[: max(0, min(7, limit))]
