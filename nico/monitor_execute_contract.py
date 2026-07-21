from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping


class MonitorExecuteError(RuntimeError):
    pass


class WorkItemState(str, Enum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    CLOSED = "closed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OversightIdentity:
    work_item_id: str
    repository: str
    immutable_sha: str
    customer_id: str
    project_id: str
    evidence_id: str


@dataclass(frozen=True)
class RemediationProposal:
    proposal_id: str
    finding_id: str
    title: str
    rationale: str
    smallest_reversible_change: str
    affected_paths: tuple[str, ...]
    verification_plan: str
    rollback_plan: str
    risk_level: str
    requested_by: str
    created_at: str
    production_impacting: bool = False


@dataclass(frozen=True)
class ApprovalRecord:
    proposal_id: str
    approver_id: str
    approved: bool
    scope: tuple[str, ...]
    approved_at: str
    expires_at: str
    reason: str
    approval_sha256: str


@dataclass(frozen=True)
class ExecutionRecord:
    proposal_id: str
    executor_id: str
    started_at: str
    completed_at: str
    before_sha: str
    after_sha: str
    changed_paths: tuple[str, ...]
    command_fingerprint: str
    outcome: str
    logs_fingerprint: str


@dataclass(frozen=True)
class VerificationRecord:
    proposal_id: str
    verifier_id: str
    verified_at: str
    passed: bool
    exact_sha: str
    checks: tuple[str, ...]
    evidence_fingerprint: str
    residual_risk: str


@dataclass(frozen=True)
class OversightWorkItem:
    identity: OversightIdentity
    state: WorkItemState
    finding: Mapping[str, Any]
    proposal: RemediationProposal | None = None
    approval: ApprovalRecord | None = None
    execution: ExecutionRecord | None = None
    verification: VerificationRecord | None = None
    human_review_required: bool = True
    client_delivery_allowed: bool = False
    revision: int = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise MonitorExecuteError(code)
    return token


def _digest(parts: tuple[str, ...]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def create_work_item(
    *,
    work_item_id: str,
    repository: str,
    immutable_sha: str,
    customer_id: str,
    project_id: str,
    evidence_id: str,
    finding: Mapping[str, Any],
) -> OversightWorkItem:
    identity = OversightIdentity(
        work_item_id=_required(work_item_id, "monitor_work_item_id_required"),
        repository=_required(repository, "monitor_repository_required"),
        immutable_sha=_required(immutable_sha, "monitor_immutable_sha_required"),
        customer_id=_required(customer_id, "monitor_customer_id_required"),
        project_id=_required(project_id, "monitor_project_id_required"),
        evidence_id=_required(evidence_id, "monitor_evidence_id_required"),
    )
    if not isinstance(finding, Mapping) or not finding:
        raise MonitorExecuteError("monitor_finding_required")
    return OversightWorkItem(identity=identity, state=WorkItemState.OBSERVED, finding=dict(finding))


def propose_remediation(
    item: OversightWorkItem,
    *,
    proposal_id: str,
    finding_id: str,
    title: str,
    rationale: str,
    smallest_reversible_change: str,
    affected_paths: tuple[str, ...],
    verification_plan: str,
    rollback_plan: str,
    risk_level: str,
    requested_by: str,
    production_impacting: bool = False,
    created_at: str = "",
) -> OversightWorkItem:
    if item.state is not WorkItemState.OBSERVED:
        raise MonitorExecuteError("monitor_proposal_invalid_state")
    paths = tuple(dict.fromkeys(_required(path, "monitor_affected_path_invalid") for path in affected_paths))
    if not paths:
        raise MonitorExecuteError("monitor_affected_paths_required")
    proposal = RemediationProposal(
        proposal_id=_required(proposal_id, "monitor_proposal_id_required"),
        finding_id=_required(finding_id, "monitor_finding_id_required"),
        title=_required(title, "monitor_proposal_title_required"),
        rationale=_required(rationale, "monitor_proposal_rationale_required"),
        smallest_reversible_change=_required(
            smallest_reversible_change,
            "monitor_reversible_change_required",
        ),
        affected_paths=paths,
        verification_plan=_required(verification_plan, "monitor_verification_plan_required"),
        rollback_plan=_required(rollback_plan, "monitor_rollback_plan_required"),
        risk_level=_required(risk_level, "monitor_risk_level_required"),
        requested_by=_required(requested_by, "monitor_requester_required"),
        created_at=created_at or _utc_now(),
        production_impacting=bool(production_impacting),
    )
    return replace(item, state=WorkItemState.PROPOSED, proposal=proposal, revision=item.revision + 1)


def record_approval(
    item: OversightWorkItem,
    *,
    approver_id: str,
    approved: bool,
    scope: tuple[str, ...],
    reason: str,
    approved_at: str = "",
    expires_at: str = "",
) -> OversightWorkItem:
    if item.state is not WorkItemState.PROPOSED or item.proposal is None:
        raise MonitorExecuteError("monitor_approval_invalid_state")
    normalized_scope = tuple(dict.fromkeys(_required(value, "monitor_approval_scope_invalid") for value in scope))
    if approved and not normalized_scope:
        raise MonitorExecuteError("monitor_approval_scope_required")
    timestamp = approved_at or _utc_now()
    record = ApprovalRecord(
        proposal_id=item.proposal.proposal_id,
        approver_id=_required(approver_id, "monitor_approver_required"),
        approved=bool(approved),
        scope=normalized_scope,
        approved_at=timestamp,
        expires_at=str(expires_at or "").strip(),
        reason=_required(reason, "monitor_approval_reason_required"),
        approval_sha256=_digest(
            (
                item.proposal.proposal_id,
                approver_id,
                str(bool(approved)),
                ",".join(normalized_scope),
                timestamp,
                str(expires_at or ""),
            )
        ),
    )
    next_state = WorkItemState.APPROVED if approved else WorkItemState.REJECTED
    return replace(item, state=next_state, approval=record, revision=item.revision + 1)


def begin_execution(
    item: OversightWorkItem,
    *,
    executor_id: str,
    requested_paths: tuple[str, ...],
    current_sha: str,
) -> OversightWorkItem:
    if item.state is not WorkItemState.APPROVED or item.proposal is None or item.approval is None:
        raise MonitorExecuteError("monitor_execution_requires_approval")
    if not item.approval.approved:
        raise MonitorExecuteError("monitor_execution_approval_rejected")
    if current_sha != item.identity.immutable_sha:
        raise MonitorExecuteError("monitor_execution_snapshot_drift")
    requested = set(requested_paths)
    if not requested or not requested.issubset(set(item.proposal.affected_paths)):
        raise MonitorExecuteError("monitor_execution_outside_proposal_scope")
    if not requested.issubset(set(item.approval.scope)):
        raise MonitorExecuteError("monitor_execution_outside_approval_scope")
    _required(executor_id, "monitor_executor_required")
    return replace(item, state=WorkItemState.EXECUTING, revision=item.revision + 1)


def record_execution(
    item: OversightWorkItem,
    *,
    executor_id: str,
    before_sha: str,
    after_sha: str,
    changed_paths: tuple[str, ...],
    command_fingerprint: str,
    outcome: str,
    logs_fingerprint: str,
    started_at: str,
    completed_at: str,
) -> OversightWorkItem:
    if item.state is not WorkItemState.EXECUTING or item.proposal is None or item.approval is None:
        raise MonitorExecuteError("monitor_execution_record_invalid_state")
    if before_sha != item.identity.immutable_sha:
        raise MonitorExecuteError("monitor_execution_before_sha_mismatch")
    paths = tuple(dict.fromkeys(changed_paths))
    if not paths or not set(paths).issubset(set(item.approval.scope)):
        raise MonitorExecuteError("monitor_execution_changed_paths_outside_scope")
    record = ExecutionRecord(
        proposal_id=item.proposal.proposal_id,
        executor_id=_required(executor_id, "monitor_executor_required"),
        started_at=_required(started_at, "monitor_execution_started_at_required"),
        completed_at=_required(completed_at, "monitor_execution_completed_at_required"),
        before_sha=_required(before_sha, "monitor_execution_before_sha_required"),
        after_sha=_required(after_sha, "monitor_execution_after_sha_required"),
        changed_paths=paths,
        command_fingerprint=_required(command_fingerprint, "monitor_command_fingerprint_required"),
        outcome=_required(outcome, "monitor_execution_outcome_required"),
        logs_fingerprint=_required(logs_fingerprint, "monitor_logs_fingerprint_required"),
    )
    next_state = WorkItemState.VERIFYING if outcome == "success" else WorkItemState.BLOCKED
    return replace(item, state=next_state, execution=record, revision=item.revision + 1)


def record_verification(
    item: OversightWorkItem,
    *,
    verifier_id: str,
    passed: bool,
    exact_sha: str,
    checks: tuple[str, ...],
    evidence_fingerprint: str,
    residual_risk: str,
    verified_at: str = "",
) -> OversightWorkItem:
    if item.state is not WorkItemState.VERIFYING or item.execution is None or item.proposal is None:
        raise MonitorExecuteError("monitor_verification_invalid_state")
    if exact_sha != item.execution.after_sha:
        raise MonitorExecuteError("monitor_verification_sha_mismatch")
    normalized_checks = tuple(dict.fromkeys(_required(check, "monitor_verification_check_invalid") for check in checks))
    if not normalized_checks:
        raise MonitorExecuteError("monitor_verification_checks_required")
    verification = VerificationRecord(
        proposal_id=item.proposal.proposal_id,
        verifier_id=_required(verifier_id, "monitor_verifier_required"),
        verified_at=verified_at or _utc_now(),
        passed=bool(passed),
        exact_sha=exact_sha,
        checks=normalized_checks,
        evidence_fingerprint=_required(
            evidence_fingerprint,
            "monitor_verification_evidence_required",
        ),
        residual_risk=_required(residual_risk, "monitor_residual_risk_required"),
    )
    next_state = WorkItemState.CLOSED if passed else WorkItemState.BLOCKED
    return replace(item, state=next_state, verification=verification, revision=item.revision + 1)


def safe_work_item(item: OversightWorkItem) -> dict[str, Any]:
    return {
        "identity": {
            "work_item_id": item.identity.work_item_id,
            "repository": item.identity.repository,
            "immutable_sha": item.identity.immutable_sha,
            "customer_id": item.identity.customer_id,
            "project_id": item.identity.project_id,
            "evidence_id": item.identity.evidence_id,
        },
        "state": item.state.value,
        "finding": dict(item.finding),
        "proposal": None if item.proposal is None else item.proposal.__dict__,
        "approval": None if item.approval is None else item.approval.__dict__,
        "execution": None if item.execution is None else item.execution.__dict__,
        "verification": None if item.verification is None else item.verification.__dict__,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "production_execution_requires_explicit_approval": True,
        "revision": item.revision,
    }


__all__ = [
    "ApprovalRecord",
    "ExecutionRecord",
    "MonitorExecuteError",
    "OversightIdentity",
    "OversightWorkItem",
    "RemediationProposal",
    "VerificationRecord",
    "WorkItemState",
    "begin_execution",
    "create_work_item",
    "propose_remediation",
    "record_approval",
    "record_execution",
    "record_verification",
    "safe_work_item",
]
