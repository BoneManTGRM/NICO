from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_stage_watchdog_v1 import (
    STALL_REASON,
    apply_stage_watchdog,
    is_recoverable_stage_stall,
    rewind_stalled_stage_for_retry,
)


def _record() -> dict:
    return create_comprehensive_run_record(
        run_id="comprun_watchdog",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger-watchdog",
        customer_id="customer",
        project_id="project",
        authorized=True,
    )


def _apply_active(record: dict, result: dict, instant: datetime) -> dict:
    stage_id = COMPREHENSIVE_STAGES[len(record["completed_stages"])]
    watched = apply_stage_watchdog(
        record,
        stage_id=stage_id,
        result=result,
        now=instant,
    )
    return apply_comprehensive_stage_result(
        record,
        stage_id=stage_id,
        result=watched,
        now=instant,
    )


def test_revision_and_heartbeat_only_changes_do_not_count_as_progress(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_MAX_NO_PROGRESS_ATTEMPTS", "2")
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_STALL_TIMEOUT_SECONDS", "600")
    started = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    record = _record()

    record = _apply_active(
        record,
        {
            "status": "running",
            "stage_progress_percent": 74,
            "heartbeat_at": "2026-08-02T12:00:00Z",
            "revision": 10,
            "scanner": {"status": "running", "active_tool": "osv-scanner"},
        },
        started,
    )
    first = record["stage_results"][COMPREHENSIVE_STAGES[0]]["watchdog"]
    assert first["no_progress_attempts"] == 0
    assert first["progress_changed"] is True

    record = _apply_active(
        record,
        {
            "status": "running",
            "stage_progress_percent": 74,
            "heartbeat_at": "2026-08-02T12:00:10Z",
            "revision": 11,
            "scanner": {"status": "running", "active_tool": "osv-scanner"},
        },
        started + timedelta(seconds=10),
    )
    second = record["stage_results"][COMPREHENSIVE_STAGES[0]]["watchdog"]
    assert second["no_progress_attempts"] == 1
    assert second["progress_changed"] is False
    assert record["terminal"] is False

    record = _apply_active(
        record,
        {
            "status": "running",
            "stage_progress_percent": 74,
            "heartbeat_at": "2026-08-02T12:00:20Z",
            "revision": 12,
            "scanner": {"status": "running", "active_tool": "osv-scanner"},
        },
        started + timedelta(seconds=20),
    )
    result = record["stage_results"][COMPREHENSIVE_STAGES[0]]
    assert record["status"] == "blocked"
    assert record["terminal"] is True
    assert result["reason"] == STALL_REASON
    assert result["error_code"] == STALL_REASON
    assert result["retryable"] is True
    assert result["cancelable"] is True
    assert result["watchdog"]["scanner_evidence_preserved"] is True
    assert validate_comprehensive_run_record(record)["status"] == "valid"


def test_meaningful_progress_resets_stall_counter(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_MAX_NO_PROGRESS_ATTEMPTS", "2")
    started = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    record = _record()
    record = _apply_active(
        record,
        {"status": "running", "stage_progress_percent": 10},
        started,
    )
    record = _apply_active(
        record,
        {"status": "running", "stage_progress_percent": 10},
        started + timedelta(seconds=5),
    )
    record = _apply_active(
        record,
        {"status": "running", "stage_progress_percent": 20},
        started + timedelta(seconds=10),
    )
    watchdog = record["stage_results"][COMPREHENSIVE_STAGES[0]]["watchdog"]
    assert watchdog["progress_changed"] is True
    assert watchdog["no_progress_attempts"] == 0
    assert record["terminal"] is False


def test_stalled_stage_can_be_retried_once_without_losing_completed_evidence(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_STAGE_MAX_NO_PROGRESS_ATTEMPTS", "1")
    started = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    record = _record()
    record = _apply_active(
        record,
        {
            "status": "running",
            "stage_progress_percent": 74,
            "evidence": {"artifact_hash": "b" * 64},
        },
        started,
    )
    record = _apply_active(
        record,
        {
            "status": "running",
            "stage_progress_percent": 74,
            "evidence": {"artifact_hash": "b" * 64},
        },
        started + timedelta(seconds=5),
    )
    assert is_recoverable_stage_stall(record) is True
    blocked_revision = record["revision"]

    recovered = rewind_stalled_stage_for_retry(
        record,
        now=started + timedelta(seconds=10),
    )
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == record["completed_stages"]
    assert COMPREHENSIVE_STAGES[0] not in recovered["stage_results"]
    assert recovered["revision"] == blocked_revision + 1
    history = recovered["recovery_history"][-1]
    assert history["recovery_type"] == STALL_REASON
    assert history["stalled_stage_evidence_preserved_in_history"] is True
    assert history["source_watchdog"]["stalled"] is True
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"

    # The retained recovery history prevents automatic unlimited retries.
    reblocked = dict(record)
    reblocked["recovery_history"] = recovered["recovery_history"]
    from nico.comprehensive_run_record import _record_hash

    reblocked["integrity_sha256"] = _record_hash(reblocked)
    assert is_recoverable_stage_stall(reblocked) is False
