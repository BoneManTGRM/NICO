from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from nico.evidence_execution_contract_v1 import (
    EvidenceContractViolation,
    ExecutionStatus,
    FailureClass,
    ScannerExecutionRecord,
    evaluate_scanner_matrix,
)

VERSION = "nico.evidence_orchestrator.v1"


@dataclass(frozen=True)
class ScannerSpec:
    tool: str
    command: tuple[str, ...]
    applicable: bool = True
    max_retries: int = 1


@dataclass(frozen=True)
class ScannerAttempt:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    raw_output: bytes
    started_at: str
    finished_at: str
    version: str
    finding_count: int = 0
    failure_class: FailureClass = FailureClass.NONE
    failure_reason: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def execute_scanner(
    spec: ScannerSpec,
    *,
    immutable_revision: str,
    artifact_dir: Path,
    runner: Callable[[ScannerSpec, int], ScannerAttempt],
    coverage_scope: Mapping[str, Any],
) -> ScannerExecutionRecord:
    if not spec.applicable:
        return ScannerExecutionRecord(
            tool=spec.tool,
            version="not-applicable",
            status=ExecutionStatus.NOT_APPLICABLE,
            applicable=False,
            command=spec.command,
            immutable_revision=immutable_revision,
            exact_revision_match=True,
            exit_code=None,
            started_at="",
            finished_at="",
            coverage_scope=coverage_scope,
            stdout_artifact="",
            stderr_artifact="",
            raw_artifact="",
            artifact_sha256="",
        )
    attempt: ScannerAttempt | None = None
    attempt_index = 0
    while attempt_index <= spec.max_retries:
        attempt = runner(spec, attempt_index)
        if attempt.failure_class not in {FailureClass.INSTALLATION, FailureClass.INFRASTRUCTURE, FailureClass.TIMEOUT}:
            break
        attempt_index += 1
    assert attempt is not None
    base = artifact_dir / spec.tool
    stdout_path = _write(base.with_suffix(".stdout.log"), attempt.stdout)
    stderr_path = _write(base.with_suffix(".stderr.log"), attempt.stderr)
    raw_path = _write(base.with_suffix(".raw"), attempt.raw_output)
    if attempt.failure_class is FailureClass.NONE and attempt.exit_code in {0, 1}:
        status = ExecutionStatus.COMPLETED_WITH_FINDINGS if attempt.finding_count else ExecutionStatus.COMPLETED_CLEAN
    elif attempt.failure_class is FailureClass.TIMEOUT:
        status = ExecutionStatus.TIMED_OUT
    else:
        status = ExecutionStatus.FAILED
    record = ScannerExecutionRecord(
        tool=spec.tool,
        version=attempt.version,
        status=status,
        applicable=True,
        command=spec.command,
        immutable_revision=immutable_revision,
        exact_revision_match=True,
        exit_code=attempt.exit_code,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        coverage_scope=coverage_scope,
        stdout_artifact=stdout_path,
        stderr_artifact=stderr_path,
        raw_artifact=raw_path,
        artifact_sha256=_sha256(attempt.raw_output),
        retry_count=attempt_index,
        failure_class=attempt.failure_class,
        failure_reason=attempt.failure_reason,
        finding_count=attempt.finding_count,
        environment_summary={"orchestrator_version": VERSION},
    )
    record.validate()
    return record


def finalize_evidence(
    records: Sequence[ScannerExecutionRecord],
    *,
    required_tools: Sequence[str],
    allow_degraded: bool = False,
) -> Mapping[str, Any]:
    decision = evaluate_scanner_matrix(records, required_tools=required_tools, allow_degraded=allow_degraded)
    if decision.mode != "complete":
        return {
            "mode": "degraded",
            "client_delivery_allowed": False,
            "score_normalization_allowed": False,
            "incomplete_tools": list(decision.incomplete_tools),
            "report_status": "DRAFT-EVIDENCE-INCOMPLETE",
        }
    return {
        "mode": "complete",
        "client_delivery_allowed": True,
        "score_normalization_allowed": True,
        "incomplete_tools": [],
        "report_status": "FINAL-PENDING-APPROVAL",
    }


def require_exact_revision(records: Sequence[ScannerExecutionRecord], revision: str) -> None:
    mismatched = [record.tool for record in records if record.applicable and (record.immutable_revision != revision or not record.exact_revision_match)]
    if mismatched:
        raise EvidenceContractViolation("Evidence revision mismatch: " + ", ".join(sorted(mismatched)))


__all__ = [
    "ScannerAttempt",
    "ScannerSpec",
    "execute_scanner",
    "finalize_evidence",
    "require_exact_revision",
]
