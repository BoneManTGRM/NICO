from __future__ import annotations

import pytest

from nico.evidence_execution_contract_v1 import (
    EvidenceContractViolation,
    ExecutionStatus,
    FailureClass,
    PipelineRunEvidence,
    PipelineStatus,
    ScannerExecutionRecord,
    assessed_revision_health,
    evaluate_scanner_matrix,
)


def _record(tool: str, *, status: ExecutionStatus = ExecutionStatus.COMPLETED_CLEAN) -> ScannerExecutionRecord:
    complete = status in {ExecutionStatus.COMPLETED_CLEAN, ExecutionStatus.COMPLETED_WITH_FINDINGS}
    return ScannerExecutionRecord(
        tool=tool,
        version="1.0.0",
        status=status,
        applicable=True,
        command=(tool, "scan"),
        immutable_revision="a" * 40,
        exact_revision_match=True,
        exit_code=0 if complete else 2,
        started_at="2026-07-28T00:00:00Z",
        finished_at="2026-07-28T00:01:00Z",
        coverage_scope={"paths": ["."]},
        stdout_artifact=f"{tool}.stdout.log",
        stderr_artifact=f"{tool}.stderr.log",
        raw_artifact=f"{tool}.json" if complete else "",
        artifact_sha256="b" * 64 if complete else "",
        failure_class=FailureClass.NONE if complete else FailureClass.INFRASTRUCTURE,
        failure_reason="" if complete else "runner unavailable",
        finding_count=0,
    )


def test_missing_required_scanner_blocks_normal_finalization() -> None:
    records = [_record("semgrep")]

    with pytest.raises(EvidenceContractViolation, match="final report generation is blocked"):
        evaluate_scanner_matrix(records, required_tools=("semgrep", "bandit"))


def test_degraded_mode_never_normalizes_missing_weight_or_allows_delivery() -> None:
    decision = evaluate_scanner_matrix(
        [_record("semgrep"), _record("bandit", status=ExecutionStatus.FAILED)],
        required_tools=("semgrep", "bandit"),
        allow_degraded=True,
    )

    assert decision.mode == "degraded"
    assert decision.incomplete_tools == ("bandit",)
    assert decision.client_delivery_allowed is False
    assert decision.technical_score_may_be_normalized is False
    assert decision.evidence_adjusted_score_required is True


def test_completed_evidence_requires_exact_revision_and_hashed_raw_artifact() -> None:
    record = _record("semgrep")
    object.__setattr__(record, "exact_revision_match", False)

    with pytest.raises(EvidenceContractViolation, match="not bound to the assessed revision"):
        record.validate()


def test_assessed_revision_health_ignores_other_commit_successes() -> None:
    requested = "a" * 40
    runs = [
        PipelineRunEvidence(
            provider="github",
            provider_run_id="1",
            provider_status="success",
            normalized_status=PipelineStatus.SUCCESS,
            immutable_revision="b" * 40,
            exact_revision_match=True,
            branch="main",
            started_at="2026-07-28T00:00:00Z",
            finished_at="2026-07-28T00:01:00Z",
            classification_reason="provider conclusion success",
        )
    ]

    health = assessed_revision_health(runs, requested)

    assert health == {
        "status": "not_observed",
        "green": None,
        "revision": requested,
        "observed_count": 0,
    }
