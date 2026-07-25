from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "nico.decision_grade.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=True)


class AssessmentType(str, Enum):
    EXPRESS = "express"
    MID = "mid"
    COMPREHENSIVE = "comprehensive"


class EvidenceStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    EXCLUDED = "excluded"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    STALE = "stale"
    CONFLICTED = "conflicted"
    PERMISSION_BLOCKED = "permission_blocked"
    NOT_ASSESSED = "not_assessed"


class Confidence(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FindingStatus(str, Enum):
    OPEN = "open"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    SUPPRESSED = "suppressed"


class TimeWindow(str, Enum):
    DAYS_0_30 = "0-30"
    DAYS_31_90 = "31-90"
    DAYS_91_180 = "91-180"


class WorkClassification(str, Enum):
    QUICK_WIN = "quick_win"
    STRATEGIC = "strategic"


class CostMode(str, Enum):
    CLIENT_INPUT = "client_input"
    SCENARIO = "scenario"
    QUALITATIVE = "qualitative"


class DeliveryStatus(str, Enum):
    INTERNAL_DRAFT = "Internal Draft"
    EVIDENCE_INCOMPLETE = "Evidence Incomplete"
    HUMAN_REVIEW_REQUIRED = "Human Review Required"
    CONDITIONALLY_DELIVERABLE = "Conditionally Deliverable"
    CLIENT_READY = "Client Ready"
    DELIVERY_BLOCKED = "Delivery Blocked"


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class AssessmentIdentity(StrictModel):
    assessment_id: str
    assessment_type: AssessmentType
    repository: str
    repository_url: str | None = None
    branch: str | None = None
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,64}$")
    commit_timestamp: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    nico_version: str = "unknown"
    schema_version: str = VERSION
    scanner_configuration_version: str = "unknown"
    report_template_version: str = "unknown"
    previous_assessment_id: str | None = None


class EvidenceLocation(StrictModel):
    file_path: str | None = None
    symbol: str | None = None
    control_name: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def lines_are_ordered(self) -> "EvidenceLocation":
        if self.line_end is not None and self.line_start is None:
            raise ValueError("line_end requires line_start")
        if self.line_start and self.line_end and self.line_end < self.line_start:
            raise ValueError("line_end cannot precede line_start")
        return self


class EvidenceRecord(StrictModel):
    evidence_id: str
    category: str
    collector: str
    collector_version: str = "unknown"
    status: EvidenceStatus
    collected_at: str | None = None
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{7,64}$")
    location: EvidenceLocation = Field(default_factory=EvidenceLocation)
    raw_measurement: Any = None
    normalized_measurement: Any = None
    threshold_or_rule: str | None = None
    evidence_value: Any = None
    confidence: Confidence = Confidence.MODERATE
    limitations: list[str] = Field(default_factory=list)
    source_reference: str | None = None
    source_kind: str = Field(default="direct", pattern=r"^(direct|derived|external)$")


class AcceptanceCriterion(StrictModel):
    criterion_id: str
    description: str = Field(min_length=8)
    validation_method: str
    target_commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{7,64}$")
    file_path: str | None = None
    symbol_or_control: str | None = None
    test_name: str | None = None
    workflow_name: str | None = None
    command: str | None = None
    metric: str | None = None
    comparator: str | None = Field(default=None, pattern=r"^(<=|>=|==|!=|<|>)$")
    target_value: Any = None
    required_evidence_ids: list[str] = Field(default_factory=list)
    passed: bool | None = None
    verified_at: str | None = None

    @model_validator(mode="after")
    def binary_and_anchored(self) -> "AcceptanceCriterion":
        anchors = (self.file_path, self.symbol_or_control, self.test_name, self.workflow_name, self.command, self.metric, *self.required_evidence_ids)
        if not any(anchors):
            raise ValueError("acceptance criterion requires a durable validation anchor")
        if bool(self.metric) != bool(self.comparator) or (self.comparator and self.target_value is None):
            raise ValueError("metric criteria require comparator and target_value")
        return self


class CostOfInaction(StrictModel):
    mode: CostMode
    time_window_days: int = Field(ge=1, le=3650)
    categories: list[str] = Field(default_factory=list)
    engineering_hours_low: float | None = Field(default=None, ge=0)
    engineering_hours_base: float | None = Field(default=None, ge=0)
    engineering_hours_high: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount_low: float | None = Field(default=None, ge=0)
    amount_base: float | None = Field(default=None, ge=0)
    amount_high: float | None = Field(default=None, ge=0)
    qualitative_exposure: str | None = Field(default=None, pattern=r"^(Minimal|Limited|Material|Severe|Critical)$")
    formula: str | None = None
    assumption_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW

    @model_validator(mode="after")
    def estimate_is_auditable(self) -> "CostOfInaction":
        money = [self.amount_low, self.amount_base, self.amount_high]
        hours = [self.engineering_hours_low, self.engineering_hours_base, self.engineering_hours_high]
        if any(value is not None for value in money) and (not self.currency or not self.assumption_ids):
            raise ValueError("monetary estimates require currency and assumptions")
        if self.mode == CostMode.SCENARIO and not self.assumption_ids:
            raise ValueError("scenario estimates require assumptions")
        if self.mode == CostMode.CLIENT_INPUT and any(value is not None for value in money) and not self.formula:
            raise ValueError("client-input monetary estimates require a formula")
        if self.mode == CostMode.QUALITATIVE and not self.qualitative_exposure:
            raise ValueError("qualitative mode requires qualitative_exposure")
        for values in (money, hours):
            present = [value for value in values if value is not None]
            if present != sorted(present):
                raise ValueError("estimate ranges must be ordered low, base, high")
        return self


class ResidualRisk(StrictModel):
    reduced_risk: str
    not_eliminated: str
    remaining_likelihood: str
    remaining_impact: str
    required_monitoring: list[str] = Field(default_factory=list)
    follow_on_work: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MODERATE


class ScannerExecutionRecord(StrictModel):
    scanner_name: str
    scanner_version: str = "unknown"
    status: EvidenceStatus
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    timed_out: bool = False
    failure_type: str | None = None
    failure_message: str | None = None
    evidence_categories_affected: list[str] = Field(default_factory=list)
    score_controls_affected: list[str] = Field(default_factory=list)
    confidence_impact: str = "none"
    required: bool = True
    limitation_accepted: bool = False
    remediation_guidance: str | None = None


class Assumption(StrictModel):
    assumption_id: str
    category: str
    description: str
    source: str
    source_kind: str = Field(pattern=r"^(user_supplied|system_default|external)$")
    confidence: Confidence
    impacted_calculations: list[str] = Field(default_factory=list)
    sensitivity: str
    if_wrong: str


class DecisionPosture(StrictModel):
    status: str
    conditions: list[str] = Field(default_factory=list)
    blocking_finding_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MODERATE
    required_next_action: str


class DecisionPostures(StrictModel):
    operate: DecisionPosture
    release: DecisionPosture
    client_delivery: DecisionPosture
    human_review: DecisionPosture


class ScoreControl(StrictModel):
    control_id: str
    raw_score: float | None = Field(default=None, ge=0, le=100)
    weight: float = Field(ge=0)
    contribution: float = Field(ge=0)
    evidence_status: EvidenceStatus
    confidence: Confidence = Confidence.MODERATE
    excluded: bool = False
    incomplete: bool = False


class RenderValidation(StrictModel):
    pdf_rendered: bool = False
    markdown_rendered: bool = False
    json_rendered: bool = False
    backlog_export_rendered: bool = False
    executive_brief_pages: int | None = Field(default=None, ge=0)
    empty_pages: int = Field(default=0, ge=0)
    clipped_content_detected: bool = False
    broken_tables_detected: bool = False


class HumanApproval(StrictModel):
    required: bool = True
    approved: bool = False
    reviewer: str | None = None
    approved_artifact_digest: str | None = None
    approved_at: str | None = None
