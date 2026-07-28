from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

VERSION = "nico.evidence_execution_contract.v1"


class EvidenceContractViolation(ValueError):
    pass


class ExecutionStatus(str, Enum):
    COMPLETED_CLEAN = "completed_clean"
    COMPLETED_WITH_FINDINGS = "completed_with_findings"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"


class FailureClass(str, Enum):
    NONE = "none"
    INSTALLATION = "installation"
    INFRASTRUCTURE = "infrastructure"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    SOURCE_DETERMINISTIC = "source_deterministic"
    COVERAGE_PARTIAL = "coverage_partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ScannerExecutionRecord:
    tool: str
    version: str
    status: ExecutionStatus
    applicable: bool
    command: tuple[str, ...]
    immutable_revision: str
    exact_revision_match: bool
    exit_code: int | None
    started_at: str
    finished_at: str
    coverage_scope: Mapping[str, Any]
    stdout_artifact: str
    stderr_artifact: str
    raw_artifact: str
    artifact_sha256: str
    retry_count: int = 0
    failure_class: FailureClass = FailureClass.NONE
    failure_reason: str = ""
    finding_count: int = 0
    environment_summary: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.tool:
            raise EvidenceContractViolation("Scanner tool is required")
        if self.applicable and not self.immutable_revision:
            raise EvidenceContractViolation(f"{self.tool}: immutable revision is required")
        if self.applicable and not self.exact_revision_match:
            raise EvidenceContractViolation(f"{self.tool}: scanner evidence is not bound to the assessed revision")
        if self.status in {ExecutionStatus.COMPLETED_CLEAN, ExecutionStatus.COMPLETED_WITH_FINDINGS}:
            if self.exit_code not in {0, 1}:
                raise EvidenceContractViolation(f"{self.tool}: completed status has invalid exit code {self.exit_code}")
            if not self.raw_artifact or not self.artifact_sha256:
                raise EvidenceContractViolation(f"{self.tool}: completed evidence must retain a hashed raw artifact")
            if self.failure_class is not FailureClass.NONE:
                raise EvidenceContractViolation(f"{self.tool}: completed evidence cannot retain a failure class")
        elif self.status is ExecutionStatus.NOT_APPLICABLE:
            if self.applicable:
                raise EvidenceContractViolation(f"{self.tool}: applicable scanner cannot be not_applicable")
        else:
            if self.failure_class is FailureClass.NONE:
                raise EvidenceContractViolation(f"{self.tool}: incomplete execution requires a failure classification")
            if not self.failure_reason:
                raise EvidenceContractViolation(f"{self.tool}: incomplete execution requires a failure reason")
        if self.status is ExecutionStatus.COMPLETED_CLEAN and self.finding_count:
            raise EvidenceContractViolation(f"{self.tool}: clean execution cannot contain findings")
        if self.status is ExecutionStatus.COMPLETED_WITH_FINDINGS and self.finding_count <= 0:
            raise EvidenceContractViolation(f"{self.tool}: completed_with_findings requires findings")

    @property
    def complete(self) -> bool:
        return self.status in {ExecutionStatus.COMPLETED_CLEAN, ExecutionStatus.COMPLETED_WITH_FINDINGS}

    @property
    def retryable(self) -> bool:
        return self.failure_class in {FailureClass.INSTALLATION, FailureClass.INFRASTRUCTURE, FailureClass.TIMEOUT}


@dataclass(frozen=True)
class EvidenceHealthDecision:
    mode: str
    complete_tools: tuple[str, ...]
    incomplete_tools: tuple[str, ...]
    excluded_controls: tuple[str, ...]
    client_delivery_allowed: bool
    technical_score_may_be_normalized: bool
    evidence_adjusted_score_required: bool


def evaluate_scanner_matrix(
    records: Sequence[ScannerExecutionRecord],
    *,
    required_tools: Sequence[str],
    allow_degraded: bool = False,
) -> EvidenceHealthDecision:
    by_tool = {record.tool: record for record in records}
    missing = [tool for tool in required_tools if tool not in by_tool]
    for record in records:
        record.validate()
    incomplete = [
        tool
        for tool in required_tools
        if tool in missing or not by_tool[tool].complete
    ]
    complete = [tool for tool in required_tools if tool in by_tool and by_tool[tool].complete]
    if incomplete and not allow_degraded:
        raise EvidenceContractViolation(
            "Required scanner evidence is incomplete; final report generation is blocked: " + ", ".join(incomplete)
        )
    mode = "degraded" if incomplete else "complete"
    return EvidenceHealthDecision(
        mode=mode,
        complete_tools=tuple(sorted(complete)),
        incomplete_tools=tuple(sorted(incomplete)),
        excluded_controls=("static_analysis",) if incomplete else (),
        client_delivery_allowed=False if incomplete else False,
        technical_score_may_be_normalized=False,
        evidence_adjusted_score_required=True,
    )


class PipelineStatus(str, Enum):
    SUCCESS = "success"
    GENUINE_FAILURE = "genuine_failure"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    CANCELLED_BY_USER = "cancelled_by_user"
    SUPERSEDED = "superseded"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"
    MANUAL_ACTION_REQUIRED = "manual_action_required"
    ACTIVE = "active"
    UNKNOWN_REVIEW_REQUIRED = "unknown_review_required"


@dataclass(frozen=True)
class PipelineRunEvidence:
    provider: str
    provider_run_id: str
    provider_status: str
    normalized_status: PipelineStatus
    immutable_revision: str
    exact_revision_match: bool
    branch: str
    started_at: str
    finished_at: str | None
    classification_reason: str
    artifact_reference: str = ""

    def validate(self) -> None:
        if not self.provider_run_id or not self.provider:
            raise EvidenceContractViolation("Pipeline run identity is incomplete")
        if not self.immutable_revision:
            raise EvidenceContractViolation("Pipeline run lacks immutable revision binding")
        if self.normalized_status is PipelineStatus.UNKNOWN_REVIEW_REQUIRED and not self.classification_reason:
            raise EvidenceContractViolation("Unknown pipeline status requires a review reason")


def assessed_revision_health(runs: Sequence[PipelineRunEvidence], revision: str) -> Mapping[str, Any]:
    exact = [run for run in runs if run.immutable_revision == revision and run.exact_revision_match]
    for run in exact:
        run.validate()
    completed = [run for run in exact if run.normalized_status is not PipelineStatus.ACTIVE]
    failures = [
        run for run in completed
        if run.normalized_status in {
            PipelineStatus.GENUINE_FAILURE,
            PipelineStatus.INFRASTRUCTURE_FAILURE,
            PipelineStatus.TIMED_OUT,
            PipelineStatus.UNKNOWN_REVIEW_REQUIRED,
        }
    ]
    if not exact:
        return {"status": "not_observed", "green": None, "revision": revision, "observed_count": 0}
    return {
        "status": "green" if completed and not failures else "not_green",
        "green": bool(completed) and not failures,
        "revision": revision,
        "observed_count": len(exact),
        "failure_count": len(failures),
    }


__all__ = [
    "EvidenceContractViolation",
    "EvidenceHealthDecision",
    "ExecutionStatus",
    "FailureClass",
    "PipelineRunEvidence",
    "PipelineStatus",
    "ScannerExecutionRecord",
    "assessed_revision_health",
    "evaluate_scanner_matrix",
]
