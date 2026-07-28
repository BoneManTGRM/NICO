from __future__ import annotations

from nico.phase6_sql_dispositions_v1 import (
    SQL_DISPOSITIONS,
    disposition_for,
    source_review_coverage,
)


EXPECTED_PATHS = {
    "nico/infrastructure_backup_runtime.py",
    "nico/comprehensive_run_store.py",
    "nico/monitor_approval_governance.py",
    "nico/monitor_execute_service.py",
    "nico/monitor_runtime.py",
    "nico/durable_runtime_storage.py",
    "nico/notification_delivery.py",
    "nico/provider_credential_rotation.py",
    "nico/provider_sync_service.py",
    "nico/runtime_heartbeat_atomic_patch.py",
    "nico/storage.py",
    "nico/storage_schema_readiness.py",
}


def test_every_observed_bandit_b608_path_has_source_specific_disposition() -> None:
    assert set(SQL_DISPOSITIONS) == EXPECTED_PATHS
    for path, record in SQL_DISPOSITIONS.items():
        assert len(record["rationale"]) >= 80, path
        assert len(record["verification"]) >= 60, path
        assert record["classification"].startswith("source_reviewed_")


def test_sql_disposition_is_traceable_and_source_change_sensitive() -> None:
    record = disposition_for(
        "nico/comprehensive_run_store.py",
        "Possible SQL injection vector through string-based query construction.",
    )

    assert record is not None
    assert record["status"] == "approved_nonblocking"
    assert record["scope"] == "nico/comprehensive_run_store.py"
    assert record["source_reviewed"] is True
    assert record["expires_on_source_change"] is True
    assert record["human_review_required"] is True
    assert "parameter" in record["rationale"].lower()


def test_non_sql_message_does_not_receive_sql_exception() -> None:
    assert disposition_for("nico/comprehensive_run_store.py", "Dynamic eval execution") is None


def test_source_review_coverage_is_complete() -> None:
    coverage = source_review_coverage()

    assert coverage["reviewed_path_count"] == len(EXPECTED_PATHS)
    assert coverage["reviewed_paths"] == sorted(EXPECTED_PATHS)
    assert coverage["every_record_has_rationale"] is True
    assert coverage["every_record_has_verification"] is True
    assert coverage["dispositions_are_source_change_sensitive"] is True
