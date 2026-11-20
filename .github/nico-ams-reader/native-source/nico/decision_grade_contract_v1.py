from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "nico.decision_grade_contract.v1"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class AssessmentType(str, Enum):
    EXPRESS = "express"
    MID = "mid"
    COMPREHENSIVE = "comprehensive"


class EvidenceStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    EXCLUDED_BY_SCOPE = "excluded_by_scope"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    STALE = "stale"
    CONFLICTED = "conflicted"
    PERMISSION_UNAVAILABLE = "permission_unavailable"


class EvidenceOrigin(str, Enum):
    DIRECT = "direct"
    DERIVED = "derived"
    EXTERNALLY_SUPPLIED = "externally_supplied"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ReadinessStatus(str, Enum):
    INTERNAL_DRAFT = "Internal Draft"
    EVIDENCE_INCOMPLETE = "Evidence Incomplete"
    HUMAN_REVIEW_REQUIRED = "Human Review Required"
    CONDITIONALLY_DELIVERABLE = "Conditionally Deliverable"
    CLIENT_READY = "Client Ready"
    DELIVERY_BLOCKED = "Delivery Blocked"


class AssessmentIdentity(ContractModel):
    assessment_id: str
    assessment_type: AssessmentType
    repository_identifier: str
    repository_url: str | None = None
    branch: str
    assessed_commit_sha: str
    commit_timestamp: str | None = None
    assessment_started_at: str | None = None
    assessment_completed_at: str | None = None
    generation_duration_seconds: float | None = Field(default=None, ge=0)
    nico_version: str
    schema_version: str = SCHEMA_VERSION
    scanner_configuration_version: str
    report_template_version: str
    previous_comparable_assessment_id: str | None = None


class EvidenceRecord(ContractModel):
    evidence_id: str
    category: str
    scanner_or_collector: str
    scanner_version: str | None = None
    collection_status: EvidenceStatus
    collected_at: str | None = None
    assessed_commit_sha: str
    file_path: str | None = None
    symbol_or_control: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    raw_measurement: Any = None
    normalized_measurement: Any = None
    threshold_or_rule: str | None = None
    evidence_excerpt: str | None = None
    structured_value: dict[str, Any] | list[Any] | None = None
    confidence: str
    limitations: list[str] = Field(default_factory=list)
    source_reference: str
    origin: EvidenceOrigin

    @model_validator(mode="after")
    def validate_line_range(self) -> "EvidenceRecord":
        if self.line_start and self.line_end and self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class AcceptanceCriterion(ContractModel):
    criterion_id: str
    description: str
    validation_method: str
    target_commit_sha: str
    file_path: str | None = None
    symbol_or_control: str | None = None
    test_name: str | None = None
    workflow_name: str | None = None
    configuration_key: str | None = None
    command: str | None = None
    metric: str | None = None
    comparator: Literal["<", "<=", "=", ">=", ">", "contains", "absent", "present"] | None = None
    target_value: str | int | float | bool | None = None
    repository_query: str | None = None
    dependency_identifier: str | None = None
    control_identifier: str | None = None
    required_evidence: list[str] = Field(default_factory=list)
    state: Literal["pending", "pass", "fail", "not_applicable"] = "pending"
    verification_timestamp: str | None = None

    @model_validator(mode="after")
    def validate_binary_criterion(self) -> "AcceptanceCriterion":
        anchors = (
            self.file_path,
            self.symbol_or_control,
            self.test_name,
            self.workflow_name,
            self.configuration_key,
            self.metric,
            self.repository_query,
            self.dependency_identifier,
            self.control_identifier,
        )
        if not any(anchors):
            raise ValueError("acceptance criterion requires a durable evidence anchor")
        if not self.required_evidence:
            raise ValueError("acceptance criterion requires verification evidence")
        return self


class CostOfInaction(ContractModel):
    mode: Literal["client_input", "scenario", "qualitative"]
    categories: list[str]
    timeframe_days: int = Field(ge=1)
    qualitative_exposure: Literal["Minimal", "Limited", "Material", "Severe", "Critical"] | None = None
    engineering_hours_low: float | None = Field(default=None, ge=0)
    engineering_hours_high: float | None = Field(default=None, ge=0)
    amount_low: float | None = Field(default=None, ge=0)
    amount_base: float | None = Field(default=None, ge=0)
    amount_high: float | None = Field(default=None, ge=0)
    currency: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    confidence: str
    rationale: str

    @model_validator(mode="after")
    def validate_estimate_integrity(self) -> "CostOfInaction":
        amounts = (self.amount_low, self.amount_base, self.amount_high)
        if self.mode == "qualitative" and any(value is not None for value in amounts):
            raise ValueError("qualitative exposure cannot contain monetary amounts")
        if any(value is not None for value in amounts):
            if not self.currency:
                raise ValueError("monetary exposure requires a currency")
            if not self.assumptions:
                raise ValueError("monetary exposure requires disclosed assumptions")
        if self.amount_low is not None and self.amount_high is not None and self.amount_high < self.amount_low:
            raise ValueError("amount_high must be greater than or equal to amount_low")
        if (
            self.engineering_hours_low is not None
            and self.engineering_hours_high is not None
            and self.engineering_hours_high < self.engineering_hours_low
        ):
            raise ValueError("engineering_hours_high must be greater than or equal to engineering_hours_low")
        if self.mode == "qualitative" and not self.qualitative_exposure:
            raise ValueError("qualitative mode requires an exposure level")
        return self


class ResidualRisk(ContractModel):
    reduces: str
    does_not_eliminate: str
    remaining_likelihood: str
    remaining_impact: str
    required_monitoring: list[str]
    possible_follow_on_work: list[str]
    confidence: str


class Finding(ContractModel):
    finding_id: str
    source_finding_id: str | None = None
    fingerprint: str
    title: str
    priority: Priority
    severity: str
    likelihood: str
    business_criticality: str
    confidence: str
    finding_type: str
    current_status: str
    scope: str
    category: str
    evidence_ids: list[str]
    factual_statement: str
    technical_interpretation: str
    business_impact: str
    affected_decision_areas: list[str]
    recommended_action: str
    owner_role: str
    effort: str
    expected_impact: str
    acceptance_criteria: list[AcceptanceCriterion]
    cost_of_inaction: CostOfInaction
    residual_risk: ResidualRisk
    roadmap_mappings: list[str]
    backlog_issue_mapping: str
    previous_run_relationship: str | None = None
    suppression_or_exclusion_reason: str | None = None
    evidence_locations: list[str]
    release_blocker: bool = False

    @model_validator(mode="after")
    def validate_priority_traceability(self) -> "Finding":
        if self.priority in {Priority.P0, Priority.P1}:
            if not self.evidence_ids:
                raise ValueError("P0/P1 findings require evidence")
            if not self.acceptance_criteria:
                raise ValueError("P0/P1 findings require acceptance criteria")
            if not self.roadmap_mappings:
                raise ValueError("P0/P1 findings require roadmap mapping")
            if not self.business_impact:
                raise ValueError("P0/P1 findings require business impact")
        return self


class RoadmapWorkPackage(ContractModel):
    work_package_id: str
    title: str
    time_window: Literal["0-30 days", "31-90 days", "91-180 days"]
    related_finding_ids: list[str]
    objective: str
    ordered_implementation_steps: list[str]
    dependencies: list[str]
    owner_role: str
    supporting_roles: list[str]
    effort_range: str
    classification: Literal["Quick Win", "Strategic"]
    expected_technical_impact: str
    expected_business_impact: str
    acceptance_criteria: list[AcceptanceCriterion]
    residual_risk: ResidualRisk
    sequencing_rationale: str


class ScannerExecutionRecord(ContractModel):
    scanner_name: str
    scanner_version: str | None = None
    status: EvidenceStatus
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    timeout_state: bool = False
    failure_type: str | None = None
    failure_message: str | None = None
    evidence_categories_affected: list[str] = Field(default_factory=list)
    score_controls_affected: list[str] = Field(default_factory=list)
    confidence_impact: str
    required: bool
    remediation_guidance: str | None = None


class Assumption(ContractModel):
    assumption_id: str
    category: str
    description: str
    source: str
    user_supplied: bool
    confidence: str
    impacted_calculations: list[str]
    sensitivity: str
    consequence_if_wrong: str


class DecisionPosture(ContractModel):
    status: str
    conditions: list[str]
    blocking_finding_ids: list[str]
    confidence: str
    required_next_action: str


class DecisionPostures(ContractModel):
    operate: DecisionPosture
    release: DecisionPosture
    client_delivery: DecisionPosture
    human_review: DecisionPosture


class ValidationIssue(ContractModel):
    code: str
    severity: Literal["info", "warning", "error", "critical"]
    message: str
    path: str | None = None
    related_ids: list[str] = Field(default_factory=list)


class DecisionGradeContract(ContractModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: str
    identity: AssessmentIdentity
    evidence_records: list[EvidenceRecord]
    findings: list[Finding]
    executive_risk_register: list[str]
    roadmap_work_packages: list[RoadmapWorkPackage]
    scanner_executions: list[ScannerExecutionRecord]
    assumptions: list[Assumption]
    decision_postures: DecisionPostures
    validation_issues: list[ValidationIssue]
    readiness_status: ReadinessStatus


_PRIORITY_ORDER = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}
_PRIORITY_EXPOSURE = {
    Priority.P0: "Critical",
    Priority.P1: "Severe",
    Priority.P2: "Limited",
    Priority.P3: "Minimal",
}
_CATEGORY_DECISIONS = {
    "secret": ["operate", "release", "client_delivery", "security"],
    "dependency": ["release", "client_delivery", "security", "maintainability"],
    "static": ["release", "reliability", "maintainability"],
    "architecture": ["velocity", "reliability", "maintainability"],
    "ci_cd": ["release", "client_delivery", "reliability"],
    "code": ["release", "reliability", "maintainability"],
    "evidence": ["release", "client_delivery", "confidence"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _location_parts(location: str) -> tuple[str | None, int | None]:
    value = _text(location, 500)
    match = re.match(r"^(?P<path>.+?):(?P<line>\d+)$", value)
    if match:
        return match.group("path"), int(match.group("line"))
    if value and "not retained" not in value.casefold() and "boundary" not in value.casefold():
        return value, None
    return None, None


def stable_finding_fingerprint(record: dict[str, Any]) -> str:
    location = _text(record.get("location") or record.get("file_path"), 500)
    location = re.sub(r":\d+$", "", location)
    identity = {
        "category": _text(record.get("category") or record.get("finding_type"), 100).casefold(),
        "control": _text(record.get("control_identifier") or record.get("symbol") or record.get("title"), 320).casefold(),
        "location": location.casefold(),
        "scanner": _text(record.get("tool") or record.get("scanner"), 100).casefold(),
    }
    return _canonical_hash(identity)


def stable_finding_id(record: dict[str, Any]) -> str:
    priority = _normalize_priority(record.get("priority"))
    return f"RISK-{priority.value}-{stable_finding_fingerprint(record)[:10].upper()}"


def _normalize_priority(value: Any) -> Priority:
    normalized = _text(value, 10).upper()
    return Priority(normalized) if normalized in {item.value for item in Priority} else Priority.P2


def _severity_for(priority: Priority, raw: Any) -> str:
    if _text(raw, 40):
        return _text(raw, 40).casefold()
    return {Priority.P0: "critical", Priority.P1: "high", Priority.P2: "medium", Priority.P3: "low"}[priority]


def _criterion_from_text(
    *,
    finding_id: str,
    index: int,
    description: str,
    commit_sha: str,
    category: str,
    location: str,
) -> AcceptanceCriterion:
    file_path, _ = _location_parts(location)
    normalized = description.casefold()
    method = "exact_sha_rerun"
    if "workflow" in normalized or "ci" in normalized:
        method = "workflow_verification"
    elif "test" in normalized:
        method = "automated_test"
    elif "human" in normalized or "approved" in normalized or "accepted" in normalized:
        method = "human_disposition_plus_exact_sha_rerun"
    comparator: Literal["<", "<=", "=", ">=", ">", "contains", "absent", "present"] | None = None
    target_value: str | int | float | bool | None = None
    metric = None
    match = re.search(r"(?P<metric>[A-Za-z][A-Za-z0-9 _/-]{2,80})\s*(?P<comparator><=|>=|=|<|>)\s*(?P<value>\d+(?:\.\d+)?)", description)
    if match:
        metric = _text(match.group("metric"), 100)
        comparator = match.group("comparator")  # type: ignore[assignment]
        raw_value = match.group("value")
        target_value = float(raw_value) if "." in raw_value else int(raw_value)
    return AcceptanceCriterion(
        criterion_id=f"AC-{finding_id}-{index:02d}",
        description=_text(description, 700),
        validation_method=method,
        target_commit_sha=commit_sha,
        file_path=file_path,
        symbol_or_control=category,
        metric=metric,
        comparator=comparator,
        target_value=target_value,
        control_identifier=category,
        required_evidence=["Exact-SHA verification result", "Pass/fail disposition recorded against this criterion"],
    )


def _acceptance_criteria(record: dict[str, Any], finding_id: str, commit_sha: str) -> list[AcceptanceCriterion]:
    raw = record.get("acceptance_criteria") or record.get("acceptance")
    values: list[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [_text(item, 700) for item in raw if _text(item, 700)]
    elif isinstance(raw, dict):
        values = [_text(raw.get("description") or raw.get("criterion"), 700)]
    if not values:
        values = ["The exact-SHA rerun records a binary pass for the affected control and preserves verification evidence."]
    category = _text(record.get("category") or "assessment_control", 80).casefold()
    location = _text(record.get("location"), 500)
    return [
        _criterion_from_text(
            finding_id=finding_id,
            index=index,
            description=value,
            commit_sha=commit_sha,
            category=category,
            location=location,
        )
        for index, value in enumerate(values, start=1)
    ]


def _cost_of_inaction(priority: Priority, category: str, impact: str) -> CostOfInaction:
    categories = {
        "architecture": ["engineering_rework", "maintenance_cost", "release_delay"],
        "ci_cd": ["release_delay", "incident_likelihood", "opportunity_cost"],
        "dependency": ["security_exposure", "maintenance_cost", "release_delay"],
        "secret": ["security_exposure", "data_loss_exposure", "customer_impact"],
        "static": ["incident_likelihood", "engineering_rework", "maintenance_cost"],
        "evidence": ["release_delay", "opportunity_cost", "customer_impact"],
    }.get(category, ["engineering_rework", "release_delay", "maintenance_cost"])
    return CostOfInaction(
        mode="qualitative",
        categories=categories,
        timeframe_days=90,
        qualitative_exposure=_PRIORITY_EXPOSURE[priority],  # type: ignore[arg-type]
        assumptions=["No client financial or operating-rate inputs were supplied; no monetary amount is claimed."],
        confidence="moderate",
        rationale=_text(impact or "Leaving the condition unresolved may increase delivery friction and residual technical risk.", 700),
    )


def _residual_risk(priority: Priority, category: str) -> ResidualRisk:
    remaining = "low" if priority in {Priority.P2, Priority.P3} else "moderate"
    return ResidualRisk(
        reduces=f"The recommended action reduces the observed {category or 'technical'} risk and improves verification confidence.",
        does_not_eliminate="Future regressions, adjacent unassessed paths, operational misuse, and evidence outside the assessed commit remain possible.",
        remaining_likelihood=remaining,
        remaining_impact="Material if the control regresses or related unassessed conditions exist.",
        required_monitoring=["Re-run the affected control against the remediation commit", "Track recurrence in the next comparable assessment"],
        possible_follow_on_work=["Expand evidence depth where limitations remain", "Add preventive CI enforcement when proportionate"],
        confidence="moderate",
    )


def _classification(effort: str, window: str, dependencies: Iterable[str]) -> Literal["Quick Win", "Strategic"]:
    normalized = effort.casefold()
    dependency_count = len(list(dependencies))
    low_effort = any(token in normalized for token in ("s", "1-2", "1-3", "2-4")) and "8" not in normalized
    return "Quick Win" if window == "0-30 days" and low_effort and dependency_count <= 3 else "Strategic"


def _roadmap_match_categories(title: str) -> set[str]:
    normalized = title.casefold()
    categories: set[str] = set()
    if any(token in normalized for token in ("scanner", "evidence")):
        categories.update({"evidence", "secret", "dependency", "static", "code"})
    if any(token in normalized for token in ("ci", "pipeline", "release")):
        categories.add("ci_cd")
    if any(token in normalized for token in ("complex", "architecture", "decompose", "technical debt")):
        categories.add("architecture")
    if any(token in normalized for token in ("traceability", "requirements")):
        categories.update({"code", "architecture", "ci_cd", "evidence"})
    return categories


def _roadmap_packages(
    roadmap: list[dict[str, Any]],
    finding_stubs: list[dict[str, Any]],
    commit_sha: str,
) -> tuple[list[RoadmapWorkPackage], dict[str, list[str]]]:
    output: list[RoadmapWorkPackage] = []
    mapping: dict[str, list[str]] = {stub["finding_id"]: [] for stub in finding_stubs}
    for window_index, window in enumerate(roadmap, start=1):
        if not isinstance(window, dict):
            continue
        time_window = _text(window.get("window"), 40)
        if time_window not in {"0-30 days", "31-90 days", "91-180 days"}:
            continue
        for package_index, package in enumerate(window.get("work_packages") or [], start=1):
            if not isinstance(package, dict):
                continue
            title = _text(package.get("title"), 240) or f"Work package {package_index}"
            package_id = f"WP-{window_index:02d}-{_canonical_hash({'window': time_window, 'title': title})[:10].upper()}"
            categories = _roadmap_match_categories(title)
            related = [stub["finding_id"] for stub in finding_stubs if not categories or stub["category"] in categories]
            for finding_id in related:
                mapping[finding_id].append(package_id)
            raw_acceptance = package.get("acceptance_criteria") or package.get("acceptance") or []
            if isinstance(raw_acceptance, str):
                raw_acceptance = [raw_acceptance]
            acceptance = [
                _criterion_from_text(
                    finding_id=package_id,
                    index=index,
                    description=_text(value, 700),
                    commit_sha=commit_sha,
                    category="roadmap_work_package",
                    location=title,
                )
                for index, value in enumerate(raw_acceptance or ["The work package is verified against the remediation commit."], start=1)
            ]
            dependencies = [_text(item, 300) for item in package.get("dependencies") or [] if _text(item, 300)]
            effort = _text(package.get("effort") or package.get("effort_range") or "Requires estimation", 80)
            output.append(
                RoadmapWorkPackage(
                    work_package_id=package_id,
                    title=title,
                    time_window=time_window,  # type: ignore[arg-type]
                    related_finding_ids=related,
                    objective=_text(package.get("objective"), 700) or "Resolve the related evidence-bound risks in dependency order.",
                    ordered_implementation_steps=[
                        "Confirm scope and evidence anchors against the assessed commit.",
                        "Implement the bounded remediation and associated tests.",
                        "Run the structured acceptance criteria against the remediation commit.",
                    ],
                    dependencies=dependencies,
                    owner_role=_text(package.get("owner_role") or package.get("owner"), 120) or "Product Engineering Architect",
                    supporting_roles=[_text(item, 120) for item in package.get("supporting_roles") or [] if _text(item, 120)],
                    effort_range=effort,
                    classification=_classification(effort, time_window, dependencies),
                    expected_technical_impact=_text(package.get("expected_impact"), 700) or "Improves the affected technical control and verification coverage.",
                    expected_business_impact=_text(package.get("expected_business_impact"), 700) or "Reduces delivery uncertainty, rework exposure, and decision latency.",
                    acceptance_criteria=acceptance,
                    residual_risk=_residual_risk(Priority.P1, "roadmap"),
                    sequencing_rationale=_text(window.get("objective"), 500) or "Scheduled according to risk, dependency, and verification readiness.",
                )
            )
    first_30_day = next((item.work_package_id for item in output if item.time_window == "0-30 days"), None)
    if first_30_day:
        for stub in finding_stubs:
            if stub["priority"] in {Priority.P0, Priority.P1} and not mapping[stub["finding_id"]]:
                mapping[stub["finding_id"]].append(first_30_day)
                for package in output:
                    if package.work_package_id == first_30_day and stub["finding_id"] not in package.related_finding_ids:
                        package.related_finding_ids.append(stub["finding_id"])
    return output, mapping


def _normalize_findings(
    records: list[dict[str, Any]],
    commit_sha: str,
    roadmap: list[dict[str, Any]],
) -> tuple[list[Finding], list[RoadmapWorkPackage], list[EvidenceRecord]]:
    stubs: list[dict[str, Any]] = []
    evidence_records: list[EvidenceRecord] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        fingerprint = stable_finding_fingerprint(record)
        finding_id = stable_finding_id(record)
        priority = _normalize_priority(record.get("priority"))
        category = _text(record.get("category") or "technical", 80).casefold()
        location = _text(record.get("location"), 500)
        file_path, line_start = _location_parts(location)
        evidence_id = f"EVD-{fingerprint[:12].upper()}"
        evidence_records.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                category=category,
                scanner_or_collector=_text(record.get("tool") or record.get("scanner") or "NICO assessment synthesis", 120),
                scanner_version=None,
                collection_status=EvidenceStatus.COMPLETE,
                collected_at=None,
                assessed_commit_sha=commit_sha,
                file_path=file_path,
                symbol_or_control=category,
                line_start=line_start,
                raw_measurement=_text(record.get("evidence"), 1000),
                normalized_measurement=None,
                threshold_or_rule=None,
                evidence_excerpt=_text(record.get("evidence"), 1000),
                structured_value=None,
                confidence=_text(record.get("confidence") or "moderate", 40).casefold(),
                limitations=[] if file_path else ["A durable file or symbol location was not retained by the source finding."],
                source_reference=_text(record.get("id") or finding_id, 200),
                origin=EvidenceOrigin.DERIVED,
            )
        )
        stubs.append(
            {
                "record": record,
                "finding_id": finding_id,
                "fingerprint": fingerprint,
                "priority": priority,
                "category": category,
                "location": location,
                "evidence_id": evidence_id,
            }
        )
    roadmap_packages, mappings = _roadmap_packages(roadmap, stubs, commit_sha)
    findings: list[Finding] = []
    for stub in stubs:
        record = stub["record"]
        priority: Priority = stub["priority"]
        category = stub["category"]
        impact = _text(record.get("business_impact") or record.get("impact"), 700)
        title = _text(record.get("title"), 320) or "Evidence-bound technical risk"
        recommendation = _text(record.get("recommended_action") or record.get("recommendation"), 900)
        confidence = _text(record.get("confidence") or "moderate", 40).casefold()
        evidence_text = _text(record.get("evidence"), 1000)
        findings.append(
            Finding(
                finding_id=stub["finding_id"],
                source_finding_id=_text(record.get("id"), 160) or None,
                fingerprint=stub["fingerprint"],
                title=title,
                priority=priority,
                severity=_severity_for(priority, record.get("severity")),
                likelihood=_text(record.get("likelihood") or ("high" if priority in {Priority.P0, Priority.P1} else "moderate"), 40).casefold(),
                business_criticality=_text(record.get("business_criticality") or _PRIORITY_EXPOSURE[priority], 40).casefold(),
                confidence=confidence,
                finding_type=_text(record.get("finding_type") or "risk", 80).casefold(),
                current_status=_text(record.get("current_status") or "open", 40).casefold(),
                scope=_text(record.get("scope") or "assessed_repository", 120),
                category=category,
                evidence_ids=[stub["evidence_id"]],
                factual_statement=evidence_text or f"NICO recorded the condition '{title}' against the assessed commit.",
                technical_interpretation=_text(record.get("technical_interpretation") or title, 700),
                business_impact=impact or "The condition may increase delivery uncertainty, rework, or residual operational risk.",
                affected_decision_areas=_CATEGORY_DECISIONS.get(category, ["release", "maintainability"]),
                recommended_action=recommendation or "Disposition the evidence, implement the bounded remediation, and verify it against an immutable commit.",
                owner_role=_text(record.get("owner_role") or "Product Engineering Architect", 120),
                effort=_text(record.get("effort") or "Requires estimation", 80),
                expected_impact=_text(record.get("expected_impact") or impact, 700) or "Reduces the observed risk and improves verification confidence.",
                acceptance_criteria=_acceptance_criteria(record, stub["finding_id"], commit_sha),
                cost_of_inaction=_cost_of_inaction(priority, category, impact),
                residual_risk=_residual_risk(priority, category),
                roadmap_mappings=mappings.get(stub["finding_id"], []),
                backlog_issue_mapping=f"backlog/{stub['finding_id']}",
                previous_run_relationship=_text(record.get("previous_run_relationship"), 120) or None,
                suppression_or_exclusion_reason=_text(record.get("suppression_or_exclusion_reason"), 300) or None,
                evidence_locations=[stub["location"]] if stub["location"] else [],
                release_blocker=bool(record.get("release_blocker")) or priority == Priority.P0,
            )
        )
    return findings, roadmap_packages, evidence_records


def _rank_findings(findings: list[Finding]) -> list[Finding]:
    confidence = {"high": 0, "moderate": 1, "low": 2}
    category_override = {"secret": 0, "dependency": 1, "ci_cd": 2, "evidence": 3, "static": 4, "architecture": 5, "code": 6}
    return sorted(
        findings,
        key=lambda item: (
            0 if item.release_blocker else 1,
            _PRIORITY_ORDER[item.priority],
            category_override.get(item.category, 9),
            confidence.get(item.confidence, 9),
            item.finding_id,
        ),
    )


def _scanner_status(value: Any) -> EvidenceStatus:
    normalized = _text(value, 40).casefold().replace("-", "_")
    if normalized in {"complete", "completed", "success", "passed", "attached"}:
        return EvidenceStatus.COMPLETE
    if normalized in {"partial", "review_limited"}:
        return EvidenceStatus.PARTIAL
    if normalized in {"timeout", "timed_out"}:
        return EvidenceStatus.TIMED_OUT
    if normalized in {"permission_unavailable", "unauthorized", "forbidden"}:
        return EvidenceStatus.PERMISSION_UNAVAILABLE
    if normalized in {"not_applicable", "n/a"}:
        return EvidenceStatus.NOT_APPLICABLE
    if normalized in {"excluded", "excluded_by_scope"}:
        return EvidenceStatus.EXCLUDED_BY_SCOPE
    return EvidenceStatus.FAILED


def _scanner_executions(stage_summaries: list[dict[str, Any]]) -> list[ScannerExecutionRecord]:
    output: list[ScannerExecutionRecord] = []
    seen: set[str] = set()
    for stage in stage_summaries:
        if not isinstance(stage, dict):
            continue
        stage_name = _text(stage.get("stage") or stage.get("name") or stage.get("step"), 120)
        payloads: list[dict[str, Any]] = []
        if isinstance(stage.get("scanner_results"), list):
            payloads.extend(item for item in stage["scanner_results"] if isinstance(item, dict))
        evidence = stage.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("scanner_results"), list):
            payloads.extend(item for item in evidence["scanner_results"] if isinstance(item, dict))
        for payload in payloads:
            name = _text(payload.get("tool") or payload.get("scanner") or "unknown", 120).casefold()
            key = f"{stage_name}:{name}"
            if key in seen:
                continue
            seen.add(key)
            status = _scanner_status(payload.get("status"))
            output.append(
                ScannerExecutionRecord(
                    scanner_name=name,
                    scanner_version=_text(payload.get("version"), 80) or None,
                    status=status,
                    started_at=_text(payload.get("started_at"), 80) or None,
                    finished_at=_text(payload.get("finished_at"), 80) or None,
                    duration_seconds=float(payload["duration_seconds"]) if isinstance(payload.get("duration_seconds"), (int, float)) else None,
                    retry_count=int(payload.get("retry_count") or 0),
                    timeout_state=status == EvidenceStatus.TIMED_OUT,
                    failure_type=_text(payload.get("failure_type"), 100) or None,
                    failure_message=_text(payload.get("reason") or payload.get("error"), 500) or None,
                    evidence_categories_affected=[_text(payload.get("category"), 80)] if _text(payload.get("category"), 80) else [],
                    score_controls_affected=[],
                    confidence_impact="Material reduction" if status in {EvidenceStatus.FAILED, EvidenceStatus.TIMED_OUT, EvidenceStatus.PERMISSION_UNAVAILABLE} else "None",
                    required=bool(payload.get("required", True)),
                    remediation_guidance="Repair the scanner boundary and rerun against the same immutable commit." if status != EvidenceStatus.COMPLETE else None,
                )
            )
    return output


def _assumptions(findings: list[Finding]) -> list[Assumption]:
    return [
        Assumption(
            assumption_id="ASM-FIN-001",
            category="financial_exposure",
            description="No client-specific labor rates, revenue, incident cost, or contract-penalty inputs were supplied.",
            source="system_default",
            user_supplied=False,
            confidence="high",
            impacted_calculations=[item.finding_id for item in findings],
            sensitivity="Any monetary conversion changes materially when client operating inputs are supplied.",
            consequence_if_wrong="Qualitative exposure remains usable, but any future financial estimate must be recalculated.",
        )
    ]


def _postures(findings: list[Finding], scanner_records: list[ScannerExecutionRecord]) -> DecisionPostures:
    blocking = [item.finding_id for item in findings if item.release_blocker]
    required_scanner_failures = [
        item.scanner_name
        for item in scanner_records
        if item.required and item.status in {EvidenceStatus.FAILED, EvidenceStatus.TIMED_OUT, EvidenceStatus.PERMISSION_UNAVAILABLE}
    ]
    release_blocked = bool(blocking or required_scanner_failures)
    release_conditions = ["Close release-blocking findings against their acceptance criteria."] if blocking else []
    if required_scanner_failures:
        release_conditions.append("Restore required scanner evidence: " + ", ".join(sorted(required_scanner_failures)))
    return DecisionPostures(
        operate=DecisionPosture(
            status="conditional" if findings else "permitted_with_monitoring",
            conditions=["Operate only within the authorized and assessed scope.", "Track unresolved P0/P1 risks."],
            blocking_finding_ids=blocking,
            confidence="moderate",
            required_next_action="Disposition the highest-priority open finding and verify the operating boundary.",
        ),
        release=DecisionPosture(
            status="blocked" if release_blocked else "conditional",
            conditions=release_conditions or ["Complete human review and verify the intended release commit."],
            blocking_finding_ids=blocking,
            confidence="high" if release_blocked else "moderate",
            required_next_action="Satisfy all release conditions and rerun the readiness gate.",
        ),
        client_delivery=DecisionPosture(
            status="blocked_pending_human_approval",
            conditions=["Report contract passes", "Human reviewer approves the exact immutable package"],
            blocking_finding_ids=blocking,
            confidence="high",
            required_next_action="Complete final human review; automated generation alone cannot authorize delivery.",
        ),
        human_review=DecisionPosture(
            status="required",
            conditions=["Reviewer dispositions every P0/P1 and material evidence limitation."],
            blocking_finding_ids=blocking,
            confidence="high",
            required_next_action="Record approval, conditional approval, or rejection against the exact package hash.",
        ),
    )


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _validation_issues(
    *,
    identity: AssessmentIdentity,
    assessment: dict[str, Any],
    findings: list[Finding],
    executive_ids: list[str],
    roadmap_packages: list[RoadmapWorkPackage],
    scanner_records: list[ScannerExecutionRecord],
    pdf_page_count: int,
    core_page_count: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ids = [item.finding_id for item in findings]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        issues.append(ValidationIssue(code="duplicate_finding_ids", severity="critical", message="Stable finding IDs are not unique.", related_ids=duplicates))
    if len(executive_ids) > 7:
        issues.append(ValidationIssue(code="executive_risk_limit_exceeded", severity="critical", message="Executive Risk Register exceeds seven items."))
    package_ids = {item.work_package_id for item in roadmap_packages}
    for finding in findings:
        missing = [item for item in finding.roadmap_mappings if item not in package_ids]
        if missing:
            issues.append(ValidationIssue(code="invalid_roadmap_mapping", severity="error", message="Finding references an unknown roadmap package.", related_ids=[finding.finding_id, *missing]))
        if finding.priority in {Priority.P0, Priority.P1} and not finding.evidence_locations:
            issues.append(ValidationIssue(code="priority_location_missing", severity="warning", message="P0/P1 finding lacks a durable evidence location.", related_ids=[finding.finding_id]))
    required_failures = [
        item.scanner_name
        for item in scanner_records
        if item.required and item.status in {EvidenceStatus.FAILED, EvidenceStatus.TIMED_OUT, EvidenceStatus.PERMISSION_UNAVAILABLE}
    ]
    if required_failures:
        issues.append(
            ValidationIssue(
                code="required_scanner_evidence_incomplete",
                severity="error",
                message="Required scanner evidence is incomplete: " + ", ".join(sorted(required_failures)),
            )
        )
    technical = assessment.get("technical_score")
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))
    if isinstance(technical, (int, float)) and isinstance(adjusted, (int, float)) and adjusted > technical:
        issues.append(ValidationIssue(code="evidence_adjusted_exceeds_technical", severity="critical", message="Evidence-adjusted score cannot exceed the technical score."))
    if pdf_page_count <= 0:
        issues.append(ValidationIssue(code="pdf_render_missing", severity="critical", message="The final PDF did not render."))
    if core_page_count <= 0:
        issues.append(ValidationIssue(code="executive_brief_page_unverified", severity="error", message="The report core-page boundary could not be verified."))
    benchmark_terms = ("high-risk quartile", "industry average", "industry percentile", "top quartile")
    if any(term in text.casefold() for text in _walk_strings(assessment) for term in benchmark_terms):
        issues.append(ValidationIssue(code="unsupported_benchmark_claim", severity="critical", message="Assessment contains benchmark language without a validated benchmark dataset."))
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", identity.assessed_commit_sha):
        issues.append(ValidationIssue(code="invalid_commit_sha", severity="critical", message="Assessed commit SHA is missing or malformed."))
    return issues


def _readiness_status(issues: list[ValidationIssue], scanner_records: list[ScannerExecutionRecord]) -> ReadinessStatus:
    if any(item.severity == "critical" for item in issues):
        return ReadinessStatus.DELIVERY_BLOCKED
    if any(item.code == "required_scanner_evidence_incomplete" for item in issues):
        return ReadinessStatus.EVIDENCE_INCOMPLETE
    if any(item.severity == "error" for item in issues):
        return ReadinessStatus.HUMAN_REVIEW_REQUIRED
    if any(item.required and item.status != EvidenceStatus.COMPLETE for item in scanner_records):
        return ReadinessStatus.EVIDENCE_INCOMPLETE
    return ReadinessStatus.HUMAN_REVIEW_REQUIRED


def build_decision_grade_contract(
    *,
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stage_summaries: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    report_template_version: str,
    pdf_page_count: int,
    core_page_count: int,
    generated_at: str | None = None,
) -> DecisionGradeContract:
    commit_sha = _text(identity.get("commit_sha"), 80)
    assessment_type = _text(identity.get("assessment_type") or identity.get("service_id") or "comprehensive", 40).casefold()
    if assessment_type == "full":
        assessment_type = "comprehensive"
    if assessment_type not in {item.value for item in AssessmentType}:
        assessment_type = "comprehensive"
    contract_identity = AssessmentIdentity(
        assessment_id=_text(identity.get("assessment_id") or identity.get("run_id"), 180),
        assessment_type=AssessmentType(assessment_type),
        repository_identifier=_text(identity.get("repository"), 240),
        repository_url=_text(identity.get("repository_url"), 500) or None,
        branch=_text(identity.get("branch") or "unknown", 180),
        assessed_commit_sha=commit_sha,
        commit_timestamp=_text(identity.get("commit_timestamp"), 80) or None,
        assessment_started_at=_text(identity.get("assessment_started_at"), 80) or None,
        assessment_completed_at=_text(identity.get("assessment_completed_at") or generated_at, 80) or None,
        generation_duration_seconds=float(identity["generation_duration_seconds"]) if isinstance(identity.get("generation_duration_seconds"), (int, float)) else None,
        nico_version=_text(identity.get("nico_version") or "0.1.1", 80),
        scanner_configuration_version=_text(identity.get("scanner_configuration_version") or "current", 120),
        report_template_version=report_template_version,
        previous_comparable_assessment_id=_text(identity.get("previous_comparable_assessment_id"), 180) or None,
    )
    records = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    findings, roadmap_packages, evidence_records = _normalize_findings(records, commit_sha, roadmap)
    ranked = _rank_findings(findings)
    executive_ids = [item.finding_id for item in ranked[:7]]
    scanner_records = _scanner_executions(stage_summaries)
    issues = _validation_issues(
        identity=contract_identity,
        assessment=assessment,
        findings=findings,
        executive_ids=executive_ids,
        roadmap_packages=roadmap_packages,
        scanner_records=scanner_records,
        pdf_page_count=pdf_page_count,
        core_page_count=core_page_count,
    )
    return DecisionGradeContract(
        generated_at=generated_at or _now(),
        identity=contract_identity,
        evidence_records=evidence_records,
        findings=findings,
        executive_risk_register=executive_ids,
        roadmap_work_packages=roadmap_packages,
        scanner_executions=scanner_records,
        assumptions=_assumptions(findings),
        decision_postures=_postures(findings, scanner_records),
        validation_issues=issues,
        readiness_status=_readiness_status(issues, scanner_records),
    )


def contract_quality_summary(contract: DecisionGradeContract) -> dict[str, Any]:
    return {
        "schema_version": contract.schema_version,
        "readiness_status": contract.readiness_status.value,
        "validation_error_count": sum(item.severity in {"error", "critical"} for item in contract.validation_issues),
        "validation_warning_count": sum(item.severity == "warning" for item in contract.validation_issues),
        "executive_risk_count": len(contract.executive_risk_register),
        "executive_risk_limit_met": len(contract.executive_risk_register) <= 7,
        "p0_p1_traceability_complete": all(
            item.evidence_ids
            and item.acceptance_criteria
            and item.roadmap_mappings
            and item.backlog_issue_mapping
            and item.residual_risk
            for item in contract.findings
            if item.priority in {Priority.P0, Priority.P1}
        ),
        "monetary_claims_require_assumptions": all(
            not any(value is not None for value in (item.cost_of_inaction.amount_low, item.cost_of_inaction.amount_base, item.cost_of_inaction.amount_high))
            or bool(item.cost_of_inaction.assumptions)
            for item in contract.findings
        ),
        "client_ready": contract.readiness_status == ReadinessStatus.CLIENT_READY,
    }


__all__ = [
    "SCHEMA_VERSION",
    "AssessmentIdentity",
    "AssessmentType",
    "EvidenceRecord",
    "EvidenceStatus",
    "EvidenceOrigin",
    "AcceptanceCriterion",
    "CostOfInaction",
    "ResidualRisk",
    "Finding",
    "RoadmapWorkPackage",
    "ScannerExecutionRecord",
    "Assumption",
    "DecisionPosture",
    "DecisionPostures",
    "ValidationIssue",
    "DecisionGradeContract",
    "ReadinessStatus",
    "Priority",
    "stable_finding_fingerprint",
    "stable_finding_id",
    "build_decision_grade_contract",
    "contract_quality_summary",
]
