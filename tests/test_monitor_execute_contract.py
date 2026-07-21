from __future__ import annotations

import pytest

from nico.monitor_execute_contract import (
    MonitorExecuteError,
    WorkItemState,
    begin_execution,
    create_work_item,
    propose_remediation,
    record_approval,
    record_execution,
    record_verification,
    safe_work_item,
)


def _proposed():
    item = create_work_item(
        work_item_id="work-1",
        repository="BoneManTGRM/NICO",
        immutable_sha="a" * 40,
        customer_id="customer-1",
        project_id="project-1",
        evidence_id="evidence-1",
        finding={"finding_id": "F-1", "severity": "high"},
    )
    return propose_remediation(
        item,
        proposal_id="proposal-1",
        finding_id="F-1",
        title="Repair exact unsafe branch",
        rationale="The exact evidence supports a bounded repair.",
        smallest_reversible_change="Change one guarded path.",
        affected_paths=("nico/example.py",),
        verification_plan="Run focused and full regression suites.",
        rollback_plan="Revert the exact repair commit.",
        risk_level="moderate",
        requested_by="nico-monitor",
        production_impacting=True,
        created_at="2026-07-21T00:00:00Z",
    )


def test_execution_cannot_begin_without_explicit_approval() -> None:
    item = _proposed()
    with pytest.raises(MonitorExecuteError, match="monitor_execution_requires_approval"):
        begin_execution(
            item,
            executor_id="worker-1",
            requested_paths=("nico/example.py",),
            current_sha="a" * 40,
        )


def test_approval_scope_and_snapshot_are_enforced() -> None:
    item = record_approval(
        _proposed(),
        approver_id="human-1",
        approved=True,
        scope=("nico/example.py",),
        reason="Approved bounded exact-snapshot repair.",
        approved_at="2026-07-21T00:01:00Z",
    )
    assert item.state is WorkItemState.APPROVED

    with pytest.raises(MonitorExecuteError, match="monitor_execution_snapshot_drift"):
        begin_execution(
            item,
            executor_id="worker-1",
            requested_paths=("nico/example.py",),
            current_sha="b" * 40,
        )
    with pytest.raises(MonitorExecuteError, match="monitor_execution_outside_proposal_scope"):
        begin_execution(
            item,
            executor_id="worker-1",
            requested_paths=("nico/other.py",),
            current_sha="a" * 40,
        )


def test_complete_approved_execution_requires_exact_verification() -> None:
    item = record_approval(
        _proposed(),
        approver_id="human-1",
        approved=True,
        scope=("nico/example.py",),
        reason="Approved.",
        approved_at="2026-07-21T00:01:00Z",
    )
    item = begin_execution(
        item,
        executor_id="worker-1",
        requested_paths=("nico/example.py",),
        current_sha="a" * 40,
    )
    item = record_execution(
        item,
        executor_id="worker-1",
        before_sha="a" * 40,
        after_sha="b" * 40,
        changed_paths=("nico/example.py",),
        command_fingerprint="sha256:command",
        outcome="success",
        logs_fingerprint="sha256:logs",
        started_at="2026-07-21T00:02:00Z",
        completed_at="2026-07-21T00:03:00Z",
    )
    assert item.state is WorkItemState.VERIFYING

    with pytest.raises(MonitorExecuteError, match="monitor_verification_sha_mismatch"):
        record_verification(
            item,
            verifier_id="verifier-1",
            passed=True,
            exact_sha="c" * 40,
            checks=("pytest",),
            evidence_fingerprint="sha256:evidence",
            residual_risk="low",
        )

    item = record_verification(
        item,
        verifier_id="verifier-1",
        passed=True,
        exact_sha="b" * 40,
        checks=("focused-tests", "full-ci", "production-smoke"),
        evidence_fingerprint="sha256:evidence",
        residual_risk="low",
        verified_at="2026-07-21T00:04:00Z",
    )
    assert item.state is WorkItemState.CLOSED
    safe = safe_work_item(item)
    assert safe["human_review_required"] is True
    assert safe["client_delivery_allowed"] is False
    assert safe["production_execution_requires_explicit_approval"] is True


def test_rejected_proposal_cannot_execute() -> None:
    item = record_approval(
        _proposed(),
        approver_id="human-1",
        approved=False,
        scope=(),
        reason="Risk exceeds approved boundary.",
    )
    assert item.state is WorkItemState.REJECTED
    with pytest.raises(MonitorExecuteError, match="monitor_execution_requires_approval"):
        begin_execution(
            item,
            executor_id="worker-1",
            requested_paths=("nico/example.py",),
            current_sha="a" * 40,
        )
