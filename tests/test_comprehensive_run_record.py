from datetime import UTC, datetime

import pytest

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    restore_comprehensive_run_record,
    validate_comprehensive_run_record,
)


def _record() -> dict:
    return create_comprehensive_run_record(
        run_id="comprun_123",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_123",
        customer_id="customer_nico",
        project_id="project_nico",
        authorized=True,
        now=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
    )


def test_new_record_is_identity_bound_and_valid() -> None:
    record = _record()
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    assert record["service_id"] == "comprehensive"
    assert record["progress_percent"] == 0.0
    assert record["human_review_required"] is True
    assert record["client_delivery_allowed"] is False


def test_stage_results_advance_only_in_contract_order() -> None:
    record = _record()
    first = COMPREHENSIVE_STAGES[0]
    updated = apply_comprehensive_stage_result(record, stage_id=first, result={"status": "complete"})
    assert updated["completed_stages"] == [first]
    assert updated["progress_percent"] > 0
    assert validate_comprehensive_run_record(updated)["status"] == "valid"

    with pytest.raises(ValueError, match="unexpected_stage"):
        apply_comprehensive_stage_result(updated, stage_id=COMPREHENSIVE_STAGES[2], result={"status": "complete"})


def test_identity_drift_is_rejected() -> None:
    record = _record()
    with pytest.raises(ValueError, match="commit_sha_identity_drift"):
        apply_comprehensive_stage_result(
            record,
            stage_id=COMPREHENSIVE_STAGES[0],
            result={"status": "complete", "commit_sha": "different"},
        )


def test_failed_stage_blocks_without_false_progress() -> None:
    record = _record()
    blocked = apply_comprehensive_stage_result(
        record,
        stage_id=COMPREHENSIVE_STAGES[0],
        result={"status": "failed", "error": "scanner unavailable"},
    )
    assert blocked["status"] == "blocked"
    assert blocked["terminal"] is True
    assert blocked["completed_stages"] == []
    assert blocked["progress_percent"] == 0.0
    assert blocked["client_delivery_allowed"] is False


def test_integrity_tampering_prevents_restore() -> None:
    record = _record()
    record["identity"]["commit_sha"] = "tampered"
    with pytest.raises(ValueError, match="integrity_hash_mismatch"):
        restore_comprehensive_run_record(record)


def test_explicit_authorization_is_required() -> None:
    with pytest.raises(ValueError, match="explicit_authorization_required"):
        create_comprehensive_run_record(
            run_id="comprun_123",
            repository="BoneManTGRM/NICO",
            commit_sha="abc123",
            evidence_ledger_id="ledger_123",
            customer_id="customer_nico",
            project_id="project_nico",
            authorized=False,
        )
