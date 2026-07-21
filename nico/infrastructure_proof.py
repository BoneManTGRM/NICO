from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class InfrastructureProofError(RuntimeError):
    pass


class StorageKind(str, Enum):
    POSTGRES = "postgres"
    RAILWAY_VOLUME_SQLITE = "railway_volume_sqlite"


@dataclass(frozen=True)
class StoragePolicy:
    kind: StorageKind
    approved_by: str
    approved_at: str
    storage_source: str
    durable: bool
    encrypted_in_transit: bool
    encrypted_at_rest: bool
    single_writer: bool
    backup_enabled: bool
    restore_test_required: bool = True
    notes: str = ""


@dataclass(frozen=True)
class BackupProof:
    backup_id: str
    storage_kind: StorageKind
    exact_sha: str
    created_at: str
    artifact_digest: str
    run_count: int
    encrypted: bool
    immutable_retention_days: int


@dataclass(frozen=True)
class RestoreProof:
    restore_id: str
    backup_id: str
    restored_at: str
    exact_sha: str
    source_run_id: str
    restored_run_id: str
    source_revision: int
    restored_revision: int
    source_integrity_sha256: str
    restored_integrity_sha256: str
    artifact_digest_preserved: bool
    isolated_environment: bool


@dataclass(frozen=True)
class ObservabilityProof:
    checked_at: str
    metrics: tuple[str, ...]
    alerts: tuple[str, ...]
    dashboards: tuple[str, ...]
    log_redaction_verified: bool
    provider_health_visible: bool
    storage_health_visible: bool
    queue_health_visible: bool
    report_health_visible: bool
    delivery_gate_visible: bool


@dataclass(frozen=True)
class RollbackProof:
    tested_at: str
    from_sha: str
    to_sha: str
    procedure_id: str
    dry_run: bool
    completed: bool
    data_loss_observed: bool
    run_identity_preserved: bool
    integrity_preserved: bool
    recovery_time_seconds: float


@dataclass(frozen=True)
class InfrastructureReleaseProof:
    policy: StoragePolicy
    backup: BackupProof
    restore: RestoreProof
    observability: ObservabilityProof
    rollback: RollbackProof
    human_review_required: bool = True
    client_delivery_allowed: bool = False


def _required(value: Any, code: str) -> str:
    token = " ".join(str(value or "").split())
    if not token:
        raise InfrastructureProofError(code)
    return token


def validate_storage_policy(policy: StoragePolicy) -> list[str]:
    issues: list[str] = []
    if not policy.approved_by:
        issues.append("storage_policy_approver_required")
    if not policy.approved_at:
        issues.append("storage_policy_approval_time_required")
    if not policy.storage_source:
        issues.append("storage_policy_source_required")
    if not policy.durable:
        issues.append("storage_policy_must_be_durable")
    if not policy.backup_enabled:
        issues.append("storage_policy_backup_required")
    if policy.kind is StorageKind.POSTGRES:
        if not policy.encrypted_in_transit:
            issues.append("postgres_transport_encryption_required")
        if policy.single_writer:
            issues.append("postgres_must_not_claim_single_writer_requirement")
        if "postgres" not in policy.storage_source.lower() and "database_url" not in policy.storage_source.lower():
            issues.append("postgres_storage_source_not_explicit")
    elif policy.kind is StorageKind.RAILWAY_VOLUME_SQLITE:
        if not policy.single_writer:
            issues.append("volume_sqlite_single_writer_required")
        if not policy.storage_source.startswith("/data/"):
            issues.append("volume_sqlite_must_use_persistent_data_path")
    return issues


def validate_infrastructure_proof(
    proof: InfrastructureReleaseProof,
    *,
    expected_sha: str,
    max_rollback_seconds: float = 900.0,
) -> list[str]:
    issues = validate_storage_policy(proof.policy)
    backup = proof.backup
    restore = proof.restore
    observe = proof.observability
    rollback = proof.rollback

    if backup.storage_kind is not proof.policy.kind:
        issues.append("backup_storage_kind_mismatch")
    if backup.exact_sha != expected_sha:
        issues.append("backup_exact_sha_mismatch")
    if not backup.backup_id or not backup.artifact_digest.startswith("sha256:"):
        issues.append("backup_identity_and_digest_required")
    if backup.run_count < 1:
        issues.append("backup_must_include_at_least_one_run")
    if not backup.encrypted:
        issues.append("backup_encryption_required")
    if backup.immutable_retention_days < 30:
        issues.append("backup_retention_too_short")

    if restore.backup_id != backup.backup_id:
        issues.append("restore_backup_identity_mismatch")
    if restore.exact_sha != expected_sha:
        issues.append("restore_exact_sha_mismatch")
    if not restore.isolated_environment:
        issues.append("restore_must_use_isolated_environment")
    if restore.source_run_id != restore.restored_run_id:
        issues.append("restore_run_identity_mismatch")
    if restore.source_revision != restore.restored_revision:
        issues.append("restore_revision_mismatch")
    if restore.source_integrity_sha256 != restore.restored_integrity_sha256:
        issues.append("restore_integrity_hash_mismatch")
    if not restore.artifact_digest_preserved:
        issues.append("restore_artifact_digest_not_preserved")

    required_metrics = {
        "storage_availability",
        "storage_latency",
        "queue_depth",
        "provider_collection_failures",
        "report_generation_failures",
        "delivery_gate_blocks",
    }
    if not required_metrics.issubset(set(observe.metrics)):
        issues.append("observability_required_metrics_missing")
    if not observe.alerts:
        issues.append("observability_alert_routes_required")
    if not observe.dashboards:
        issues.append("observability_dashboards_required")
    if not observe.log_redaction_verified:
        issues.append("observability_log_redaction_required")
    for key, value in {
        "provider": observe.provider_health_visible,
        "storage": observe.storage_health_visible,
        "queue": observe.queue_health_visible,
        "report": observe.report_health_visible,
        "delivery": observe.delivery_gate_visible,
    }.items():
        if not value:
            issues.append(f"observability_{key}_health_missing")

    if rollback.from_sha != expected_sha:
        issues.append("rollback_from_sha_mismatch")
    if not rollback.to_sha or rollback.to_sha == rollback.from_sha:
        issues.append("rollback_target_sha_invalid")
    if not rollback.procedure_id:
        issues.append("rollback_procedure_required")
    if not rollback.completed:
        issues.append("rollback_proof_incomplete")
    if rollback.data_loss_observed:
        issues.append("rollback_data_loss_detected")
    if not rollback.run_identity_preserved:
        issues.append("rollback_run_identity_not_preserved")
    if not rollback.integrity_preserved:
        issues.append("rollback_integrity_not_preserved")
    if rollback.recovery_time_seconds < 0 or rollback.recovery_time_seconds > max_rollback_seconds:
        issues.append("rollback_recovery_time_exceeded")

    if not proof.human_review_required:
        issues.append("infrastructure_human_review_must_remain_required")
    if proof.client_delivery_allowed:
        issues.append("infrastructure_client_delivery_must_remain_blocked")
    return issues


def infrastructure_verdict(
    proof: InfrastructureReleaseProof,
    *,
    expected_sha: str,
    max_rollback_seconds: float = 900.0,
) -> dict[str, Any]:
    issues = validate_infrastructure_proof(
        proof,
        expected_sha=expected_sha,
        max_rollback_seconds=max_rollback_seconds,
    )
    return {
        "status": "passed" if not issues else "failed",
        "expected_sha": expected_sha,
        "storage_kind": proof.policy.kind.value,
        "storage_source": proof.policy.storage_source,
        "backup_id": proof.backup.backup_id,
        "restore_id": proof.restore.restore_id,
        "rollback_procedure_id": proof.rollback.procedure_id,
        "issues": issues,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def storage_policy_from_mapping(data: Mapping[str, Any]) -> StoragePolicy:
    return StoragePolicy(
        kind=StorageKind(_required(data.get("kind"), "storage_policy_kind_required")),
        approved_by=_required(data.get("approved_by"), "storage_policy_approver_required"),
        approved_at=_required(data.get("approved_at"), "storage_policy_approval_time_required"),
        storage_source=_required(data.get("storage_source"), "storage_policy_source_required"),
        durable=bool(data.get("durable")),
        encrypted_in_transit=bool(data.get("encrypted_in_transit")),
        encrypted_at_rest=bool(data.get("encrypted_at_rest")),
        single_writer=bool(data.get("single_writer")),
        backup_enabled=bool(data.get("backup_enabled")),
        restore_test_required=bool(data.get("restore_test_required", True)),
        notes=str(data.get("notes") or ""),
    )


__all__ = [
    "BackupProof",
    "InfrastructureProofError",
    "InfrastructureReleaseProof",
    "ObservabilityProof",
    "RestoreProof",
    "RollbackProof",
    "StorageKind",
    "StoragePolicy",
    "infrastructure_verdict",
    "storage_policy_from_mapping",
    "validate_infrastructure_proof",
    "validate_storage_policy",
]
