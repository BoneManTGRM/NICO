from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping

from nico.monitor_execute_contract import ApprovalRecord, MonitorExecuteError, OversightWorkItem, WorkItemState
from nico.monitor_execute_service import MonitorExecuteService, MonitorExecuteStore


class ApprovalGovernanceError(MonitorExecuteError):
    pass


class ApprovalRevocationMissing(ApprovalGovernanceError):
    pass


@dataclass(frozen=True)
class ApprovalRevocation:
    approval_sha256: str
    proposal_id: str
    work_item_id: str
    revoked_by: str
    revoked_at: str
    reason: str
    revocation_sha256: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str, *, code: str) -> datetime:
    token = str(value or "").strip()
    if not token:
        raise ApprovalGovernanceError(code)
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise ApprovalGovernanceError(code) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise ApprovalGovernanceError(code)
    return token


def _digest(parts: tuple[str, ...]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


class ApprovalRevocationStore:
    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("approval_revocation_dialect_unsupported")
        self._connection_factory = connection_factory
        self.dialect = dialect

    @property
    def _placeholder(self) -> str:
        return "?" if self.dialect == "sqlite" else "%s"

    def ensure_schema(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_approval_revocations (
                    approval_sha256 TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    work_item_id TEXT NOT NULL,
                    revoked_by TEXT NOT NULL,
                    revoked_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    revocation_sha256 TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def revoke(
        self,
        *,
        approval: ApprovalRecord,
        work_item_id: str,
        revoked_by: str,
        reason: str,
        revoked_at: str = "",
    ) -> ApprovalRevocation:
        if not approval.approved:
            raise ApprovalGovernanceError("approval_rejected_record_cannot_be_revoked")
        timestamp = revoked_at or _iso(_utc_now())
        _parse_time(timestamp, code="approval_revocation_time_invalid")
        record = ApprovalRevocation(
            approval_sha256=_required(approval.approval_sha256, "approval_identity_required"),
            proposal_id=_required(approval.proposal_id, "approval_proposal_required"),
            work_item_id=_required(work_item_id, "approval_work_item_required"),
            revoked_by=_required(revoked_by, "approval_revoker_required"),
            revoked_at=timestamp,
            reason=_required(reason, "approval_revocation_reason_required"),
            revocation_sha256=_digest(
                (
                    approval.approval_sha256,
                    approval.proposal_id,
                    work_item_id,
                    revoked_by,
                    timestamp,
                    reason,
                )
            ),
        )
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            values = (
                record.approval_sha256,
                record.proposal_id,
                record.work_item_id,
                record.revoked_by,
                record.revoked_at,
                record.reason,
                record.revocation_sha256,
            )
            placeholders = ",".join([self._placeholder] * len(values))
            try:
                cursor.execute(
                    f"""
                    INSERT INTO nico_monitor_approval_revocations (
                        approval_sha256, proposal_id, work_item_id, revoked_by,
                        revoked_at, reason, revocation_sha256
                    ) VALUES ({placeholders})
                    """,
                    values,
                )
            except Exception as exc:
                connection.rollback()
                raise ApprovalGovernanceError("approval_already_revoked") from exc
            connection.commit()
        finally:
            connection.close()
        return record

    def find(self, approval_sha256: str) -> ApprovalRevocation | None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT proposal_id, work_item_id, revoked_by, revoked_at, reason, revocation_sha256
                FROM nico_monitor_approval_revocations
                WHERE approval_sha256 = {self._placeholder}
                """,
                (approval_sha256,),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return ApprovalRevocation(
            approval_sha256=approval_sha256,
            proposal_id=str(row[0]),
            work_item_id=str(row[1]),
            revoked_by=str(row[2]),
            revoked_at=str(row[3]),
            reason=str(row[4]),
            revocation_sha256=str(row[5]),
        )


def validate_active_approval(
    item: OversightWorkItem,
    *,
    revocations: ApprovalRevocationStore,
    now: datetime | None = None,
) -> ApprovalRecord:
    if item.state is not WorkItemState.APPROVED or item.approval is None or item.proposal is None:
        raise ApprovalGovernanceError("monitor_execution_requires_approval")
    approval = item.approval
    if not approval.approved:
        raise ApprovalGovernanceError("monitor_execution_approval_rejected")
    if approval.proposal_id != item.proposal.proposal_id:
        raise ApprovalGovernanceError("approval_proposal_identity_mismatch")
    if revocations.find(approval.approval_sha256) is not None:
        raise ApprovalGovernanceError("monitor_execution_approval_revoked")
    current = now or _utc_now()
    approved_at = _parse_time(approval.approved_at, code="approval_approved_at_invalid")
    if approved_at > current:
        raise ApprovalGovernanceError("approval_not_yet_valid")
    if approval.expires_at:
        expires = _parse_time(approval.expires_at, code="approval_expiry_invalid")
        if expires <= approved_at:
            raise ApprovalGovernanceError("approval_expiry_must_follow_approval")
        if current >= expires:
            raise ApprovalGovernanceError("monitor_execution_approval_expired")
    return approval


class GovernedMonitorExecuteService(MonitorExecuteService):
    """Monitor service that enforces approval expiry and durable revocation before execution."""

    def __init__(
        self,
        store: MonitorExecuteStore,
        revocations: ApprovalRevocationStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        super().__init__(store)
        self.revocations = revocations
        self._clock = clock

    def begin(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        stored = self.store.load(work_item_id)
        validate_active_approval(stored.item, revocations=self.revocations, now=self._clock())
        return super().begin(work_item_id, payload)

    def revoke(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        stored = self.store.load(work_item_id)
        item = stored.item
        if item.approval is None:
            raise ApprovalGovernanceError("approval_record_not_found")
        record = self.revocations.revoke(
            approval=item.approval,
            work_item_id=work_item_id,
            revoked_by=str(payload.get("revoked_by") or ""),
            reason=str(payload.get("reason") or ""),
            revoked_at=str(payload.get("revoked_at") or ""),
        )
        return {
            **self._response(stored),
            "approval_active": False,
            "approval_revocation": record.__dict__,
            "production_execution_requires_explicit_approval": True,
            "client_delivery_allowed": False,
        }

    def approval_status(self, work_item_id: str) -> dict[str, Any]:
        stored = self.store.load(work_item_id)
        item = stored.item
        if item.approval is None:
            return {**self._response(stored), "approval_active": False, "approval_reason": "not_approved"}
        revoked = self.revocations.find(item.approval.approval_sha256)
        try:
            validate_active_approval(item, revocations=self.revocations, now=self._clock())
            active = True
            reason = "active"
        except ApprovalGovernanceError as exc:
            active = False
            reason = str(exc)
        return {
            **self._response(stored),
            "approval_active": active,
            "approval_reason": reason,
            "approval_revocation": None if revoked is None else revoked.__dict__,
        }


__all__ = [
    "ApprovalGovernanceError",
    "ApprovalRevocation",
    "ApprovalRevocationMissing",
    "ApprovalRevocationStore",
    "GovernedMonitorExecuteService",
    "validate_active_approval",
]
