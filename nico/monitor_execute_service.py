from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping

from nico.monitor_execute_contract import (
    ApprovalRecord,
    ExecutionRecord,
    OversightIdentity,
    OversightWorkItem,
    RemediationProposal,
    VerificationRecord,
    WorkItemState,
    begin_execution,
    create_work_item,
    propose_remediation,
    record_approval,
    record_execution,
    record_verification,
    safe_work_item,
)


class MonitorStoreError(RuntimeError):
    pass


class MonitorItemMissing(MonitorStoreError):
    pass


class MonitorItemDuplicate(MonitorStoreError):
    pass


class MonitorRevisionConflict(MonitorStoreError):
    pass


class MonitorIntegrityError(MonitorStoreError):
    pass


@dataclass(frozen=True)
class StoredMonitorItem:
    item: OversightWorkItem
    integrity_sha256: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(item: OversightWorkItem) -> str:
    return json.dumps(safe_work_item(item), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity(payload_json: str) -> str:
    return f"sha256:{sha256(payload_json.encode('utf-8')).hexdigest()}"


def _deserialize(payload_json: str) -> OversightWorkItem:
    try:
        data = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise MonitorIntegrityError("monitor_payload_json_invalid") from exc
    identity_data = data.get("identity") or {}
    identity = OversightIdentity(
        work_item_id=str(identity_data.get("work_item_id") or ""),
        repository=str(identity_data.get("repository") or ""),
        immutable_sha=str(identity_data.get("immutable_sha") or ""),
        customer_id=str(identity_data.get("customer_id") or ""),
        project_id=str(identity_data.get("project_id") or ""),
        evidence_id=str(identity_data.get("evidence_id") or ""),
    )
    proposal_data = data.get("proposal")
    proposal = None
    if isinstance(proposal_data, Mapping):
        proposal = RemediationProposal(
            proposal_id=str(proposal_data.get("proposal_id") or ""),
            finding_id=str(proposal_data.get("finding_id") or ""),
            title=str(proposal_data.get("title") or ""),
            rationale=str(proposal_data.get("rationale") or ""),
            smallest_reversible_change=str(proposal_data.get("smallest_reversible_change") or ""),
            affected_paths=tuple(str(item) for item in proposal_data.get("affected_paths") or ()),
            verification_plan=str(proposal_data.get("verification_plan") or ""),
            rollback_plan=str(proposal_data.get("rollback_plan") or ""),
            risk_level=str(proposal_data.get("risk_level") or ""),
            requested_by=str(proposal_data.get("requested_by") or ""),
            created_at=str(proposal_data.get("created_at") or ""),
            production_impacting=bool(proposal_data.get("production_impacting")),
        )
    approval_data = data.get("approval")
    approval = None
    if isinstance(approval_data, Mapping):
        approval = ApprovalRecord(
            proposal_id=str(approval_data.get("proposal_id") or ""),
            approver_id=str(approval_data.get("approver_id") or ""),
            approved=bool(approval_data.get("approved")),
            scope=tuple(str(item) for item in approval_data.get("scope") or ()),
            approved_at=str(approval_data.get("approved_at") or ""),
            expires_at=str(approval_data.get("expires_at") or ""),
            reason=str(approval_data.get("reason") or ""),
            approval_sha256=str(approval_data.get("approval_sha256") or ""),
        )
    execution_data = data.get("execution")
    execution = None
    if isinstance(execution_data, Mapping):
        execution = ExecutionRecord(
            proposal_id=str(execution_data.get("proposal_id") or ""),
            executor_id=str(execution_data.get("executor_id") or ""),
            started_at=str(execution_data.get("started_at") or ""),
            completed_at=str(execution_data.get("completed_at") or ""),
            before_sha=str(execution_data.get("before_sha") or ""),
            after_sha=str(execution_data.get("after_sha") or ""),
            changed_paths=tuple(str(item) for item in execution_data.get("changed_paths") or ()),
            command_fingerprint=str(execution_data.get("command_fingerprint") or ""),
            outcome=str(execution_data.get("outcome") or ""),
            logs_fingerprint=str(execution_data.get("logs_fingerprint") or ""),
        )
    verification_data = data.get("verification")
    verification = None
    if isinstance(verification_data, Mapping):
        verification = VerificationRecord(
            proposal_id=str(verification_data.get("proposal_id") or ""),
            verifier_id=str(verification_data.get("verifier_id") or ""),
            verified_at=str(verification_data.get("verified_at") or ""),
            passed=bool(verification_data.get("passed")),
            exact_sha=str(verification_data.get("exact_sha") or ""),
            checks=tuple(str(item) for item in verification_data.get("checks") or ()),
            evidence_fingerprint=str(verification_data.get("evidence_fingerprint") or ""),
            residual_risk=str(verification_data.get("residual_risk") or ""),
        )
    return OversightWorkItem(
        identity=identity,
        state=WorkItemState(str(data.get("state") or "observed")),
        finding=dict(data.get("finding") or {}),
        proposal=proposal,
        approval=approval,
        execution=execution,
        verification=verification,
        human_review_required=True,
        client_delivery_allowed=False,
        revision=int(data.get("revision") or 1),
    )


class MonitorExecuteStore:
    def __init__(self, connection_factory: Callable[[], Any], *, dialect: str = "sqlite") -> None:
        self._connection_factory = connection_factory
        self.dialect = dialect
        if dialect not in {"sqlite", "postgres"}:
            raise ValueError("monitor_store_dialect_unsupported")

    @property
    def _placeholder(self) -> str:
        return "?" if self.dialect == "sqlite" else "%s"

    def ensure_schema(self) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS nico_monitor_work_items (
                    work_item_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    immutable_sha TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nico_monitor_scope
                ON nico_monitor_work_items (customer_id, project_id, updated_at)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def create(self, item: OversightWorkItem) -> StoredMonitorItem:
        payload = _canonical_json(item)
        integrity = _integrity(payload)
        updated_at = _utc_now()
        values = (
            item.identity.work_item_id,
            item.identity.repository,
            item.identity.immutable_sha,
            item.identity.customer_id,
            item.identity.project_id,
            item.state.value,
            item.revision,
            payload,
            integrity,
            updated_at,
        )
        placeholders = ",".join([self._placeholder] * len(values))
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"""
                    INSERT INTO nico_monitor_work_items (
                        work_item_id, repository, immutable_sha, customer_id, project_id,
                        state, revision, payload_json, integrity_sha256, updated_at
                    ) VALUES ({placeholders})
                    """,
                    values,
                )
            except Exception as exc:
                connection.rollback()
                raise MonitorItemDuplicate("monitor_work_item_already_exists") from exc
            connection.commit()
        finally:
            connection.close()
        return StoredMonitorItem(item, integrity, updated_at)

    def load(self, work_item_id: str) -> StoredMonitorItem:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT payload_json, integrity_sha256, updated_at FROM nico_monitor_work_items WHERE work_item_id = {self._placeholder}",
                (work_item_id,),
            )
            row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            raise MonitorItemMissing("monitor_work_item_not_found")
        payload, integrity, updated_at = str(row[0]), str(row[1]), str(row[2])
        if integrity != _integrity(payload):
            raise MonitorIntegrityError("monitor_work_item_integrity_mismatch")
        return StoredMonitorItem(_deserialize(payload), integrity, updated_at)

    def save(self, item: OversightWorkItem, *, expected_revision: int) -> StoredMonitorItem:
        if item.revision != expected_revision + 1:
            raise MonitorRevisionConflict("monitor_revision_increment_invalid")
        payload = _canonical_json(item)
        integrity = _integrity(payload)
        updated_at = _utc_now()
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                UPDATE nico_monitor_work_items
                SET state = {self._placeholder}, revision = {self._placeholder},
                    payload_json = {self._placeholder}, integrity_sha256 = {self._placeholder},
                    updated_at = {self._placeholder}
                WHERE work_item_id = {self._placeholder} AND revision = {self._placeholder}
                """,
                (
                    item.state.value,
                    item.revision,
                    payload,
                    integrity,
                    updated_at,
                    item.identity.work_item_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise MonitorRevisionConflict("monitor_revision_conflict")
            connection.commit()
        finally:
            connection.close()
        return StoredMonitorItem(item, integrity, updated_at)


class MonitorExecuteService:
    def __init__(self, store: MonitorExecuteStore) -> None:
        self.store = store

    @staticmethod
    def _response(stored: StoredMonitorItem) -> dict[str, Any]:
        return {**safe_work_item(stored.item), "integrity_sha256": stored.integrity_sha256, "updated_at": stored.updated_at}

    def status(self, work_item_id: str) -> dict[str, Any]:
        return self._response(self.store.load(work_item_id))

    def create(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        item = create_work_item(
            work_item_id=str(payload.get("work_item_id") or ""),
            repository=str(payload.get("repository") or ""),
            immutable_sha=str(payload.get("immutable_sha") or ""),
            customer_id=str(payload.get("customer_id") or ""),
            project_id=str(payload.get("project_id") or ""),
            evidence_id=str(payload.get("evidence_id") or ""),
            finding=payload.get("finding") if isinstance(payload.get("finding"), Mapping) else {},
        )
        return self._response(self.store.create(item))

    def _mutate(self, work_item_id: str, operation: Callable[[OversightWorkItem], OversightWorkItem]) -> dict[str, Any]:
        stored = self.store.load(work_item_id)
        updated = operation(stored.item)
        return self._response(self.store.save(updated, expected_revision=stored.item.revision))

    def propose(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._mutate(work_item_id, lambda item: propose_remediation(
            item,
            proposal_id=str(payload.get("proposal_id") or ""),
            finding_id=str(payload.get("finding_id") or ""),
            title=str(payload.get("title") or ""),
            rationale=str(payload.get("rationale") or ""),
            smallest_reversible_change=str(payload.get("smallest_reversible_change") or ""),
            affected_paths=tuple(str(value) for value in payload.get("affected_paths") or ()),
            verification_plan=str(payload.get("verification_plan") or ""),
            rollback_plan=str(payload.get("rollback_plan") or ""),
            risk_level=str(payload.get("risk_level") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            production_impacting=bool(payload.get("production_impacting")),
            created_at=str(payload.get("created_at") or ""),
        ))

    def approve(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._mutate(work_item_id, lambda item: record_approval(
            item,
            approver_id=str(payload.get("approver_id") or ""),
            approved=bool(payload.get("approved")),
            scope=tuple(str(value) for value in payload.get("scope") or ()),
            reason=str(payload.get("reason") or ""),
            approved_at=str(payload.get("approved_at") or ""),
            expires_at=str(payload.get("expires_at") or ""),
        ))

    def begin(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._mutate(work_item_id, lambda item: begin_execution(
            item,
            executor_id=str(payload.get("executor_id") or ""),
            requested_paths=tuple(str(value) for value in payload.get("requested_paths") or ()),
            current_sha=str(payload.get("current_sha") or ""),
        ))

    def complete_execution(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._mutate(work_item_id, lambda item: record_execution(
            item,
            executor_id=str(payload.get("executor_id") or ""),
            before_sha=str(payload.get("before_sha") or ""),
            after_sha=str(payload.get("after_sha") or ""),
            changed_paths=tuple(str(value) for value in payload.get("changed_paths") or ()),
            command_fingerprint=str(payload.get("command_fingerprint") or ""),
            outcome=str(payload.get("outcome") or ""),
            logs_fingerprint=str(payload.get("logs_fingerprint") or ""),
            started_at=str(payload.get("started_at") or ""),
            completed_at=str(payload.get("completed_at") or ""),
        ))

    def verify(self, work_item_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._mutate(work_item_id, lambda item: record_verification(
            item,
            verifier_id=str(payload.get("verifier_id") or ""),
            passed=bool(payload.get("passed")),
            exact_sha=str(payload.get("exact_sha") or ""),
            checks=tuple(str(value) for value in payload.get("checks") or ()),
            evidence_fingerprint=str(payload.get("evidence_fingerprint") or ""),
            residual_risk=str(payload.get("residual_risk") or ""),
            verified_at=str(payload.get("verified_at") or ""),
        ))


__all__ = [
    "MonitorExecuteService",
    "MonitorExecuteStore",
    "MonitorIntegrityError",
    "MonitorItemDuplicate",
    "MonitorItemMissing",
    "MonitorRevisionConflict",
    "MonitorStoreError",
    "StoredMonitorItem",
]
