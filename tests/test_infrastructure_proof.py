from __future__ import annotations

from nico.infrastructure_proof import (
    BackupProof,
    InfrastructureReleaseProof,
    ObservabilityProof,
    RestoreProof,
    RollbackProof,
    StorageKind,
    StoragePolicy,
    infrastructure_verdict,
    validate_storage_policy,
)


def _proof() -> InfrastructureReleaseProof:
    exact_sha = "a" * 40
    policy = StoragePolicy(
        kind=StorageKind.POSTGRES,
        approved_by="owner-1",
        approved_at="2026-07-21T00:00:00Z",
        storage_source="DATABASE_URL:railway-postgres",
        durable=True,
        encrypted_in_transit=True,
        encrypted_at_rest=True,
        single_writer=False,
        backup_enabled=True,
    )
    backup = BackupProof(
        backup_id="backup-1",
        storage_kind=StorageKind.POSTGRES,
        exact_sha=exact_sha,
        created_at="2026-07-21T00:01:00Z",
        artifact_digest="sha256:backup",
        run_count=4,
        encrypted=True,
        immutable_retention_days=90,
    )
    restore = RestoreProof(
        restore_id="restore-1",
        backup_id="backup-1",
        restored_at="2026-07-21T00:02:00Z",
        exact_sha=exact_sha,
        source_run_id="run-1",
        restored_run_id="run-1",
        source_revision=14,
        restored_revision=14,
        source_integrity_sha256="sha256:integrity",
        restored_integrity_sha256="sha256:integrity",
        artifact_digest_preserved=True,
        isolated_environment=True,
    )
    observability = ObservabilityProof(
        checked_at="2026-07-21T00:03:00Z",
        metrics=(
            "storage_availability",
            "storage_latency",
            "queue_depth",
            "provider_collection_failures",
            "report_generation_failures",
            "delivery_gate_blocks",
        ),
        alerts=("storage-unavailable", "queue-stalled", "provider-outage"),
        dashboards=("production-health",),
        log_redaction_verified=True,
        provider_health_visible=True,
        storage_health_visible=True,
        queue_health_visible=True,
        report_health_visible=True,
        delivery_gate_visible=True,
    )
    rollback = RollbackProof(
        tested_at="2026-07-21T00:04:00Z",
        from_sha=exact_sha,
        to_sha="b" * 40,
        procedure_id="rollback-v1",
        dry_run=True,
        completed=True,
        data_loss_observed=False,
        run_identity_preserved=True,
        integrity_preserved=True,
        recovery_time_seconds=120,
    )
    return InfrastructureReleaseProof(policy, backup, restore, observability, rollback)


def test_complete_postgres_proof_passes() -> None:
    verdict = infrastructure_verdict(_proof(), expected_sha="a" * 40)
    assert verdict["status"] == "passed"
    assert verdict["issues"] == []
    assert verdict["human_review_required"] is True
    assert verdict["client_delivery_allowed"] is False


def test_restore_identity_drift_fails() -> None:
    proof = _proof()
    broken = InfrastructureReleaseProof(
        proof.policy,
        proof.backup,
        RestoreProof(
            **{
                **proof.restore.__dict__,
                "restored_run_id": "different-run",
                "restored_integrity_sha256": "sha256:different",
            }
        ),
        proof.observability,
        proof.rollback,
    )
    issues = infrastructure_verdict(broken, expected_sha="a" * 40)["issues"]
    assert "restore_run_identity_mismatch" in issues
    assert "restore_integrity_hash_mismatch" in issues


def test_volume_sqlite_requires_persistent_path_and_single_writer() -> None:
    policy = StoragePolicy(
        kind=StorageKind.RAILWAY_VOLUME_SQLITE,
        approved_by="owner",
        approved_at="2026-07-21T00:00:00Z",
        storage_source="/tmp/nico.sqlite3",
        durable=True,
        encrypted_in_transit=False,
        encrypted_at_rest=True,
        single_writer=False,
        backup_enabled=True,
    )
    issues = validate_storage_policy(policy)
    assert "volume_sqlite_single_writer_required" in issues
    assert "volume_sqlite_must_use_persistent_data_path" in issues


def test_observability_and_rollback_fail_closed() -> None:
    proof = _proof()
    broken_observability = ObservabilityProof(
        checked_at=proof.observability.checked_at,
        metrics=("storage_availability",),
        alerts=(),
        dashboards=(),
        log_redaction_verified=False,
        provider_health_visible=False,
        storage_health_visible=True,
        queue_health_visible=False,
        report_health_visible=False,
        delivery_gate_visible=False,
    )
    broken_rollback = RollbackProof(
        **{
            **proof.rollback.__dict__,
            "completed": False,
            "data_loss_observed": True,
            "recovery_time_seconds": 901,
        }
    )
    verdict = infrastructure_verdict(
        InfrastructureReleaseProof(
            proof.policy,
            proof.backup,
            proof.restore,
            broken_observability,
            broken_rollback,
        ),
        expected_sha="a" * 40,
    )
    assert verdict["status"] == "failed"
    assert "observability_required_metrics_missing" in verdict["issues"]
    assert "rollback_proof_incomplete" in verdict["issues"]
    assert "rollback_data_loss_detected" in verdict["issues"]
    assert "rollback_recovery_time_exceeded" in verdict["issues"]
