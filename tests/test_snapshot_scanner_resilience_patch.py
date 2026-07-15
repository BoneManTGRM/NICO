from __future__ import annotations

from typing import Any

from nico import scanner_recovery, scanner_worker, snapshot_scanner_worker
from nico.mid_assessment_api import MidAssessmentStatusRequest
from nico.mid_live_progress_patch import attach_mid_live_progress
from nico.snapshot_scanner_resilience_patch import _run_with_failure_boundary
from nico.storage import MemoryAdapter


def _snapshot_record(scan_id: str = "scan_snapshot_recovery_test") -> dict[str, Any]:
    return {
        "scan_id": scan_id,
        "run_id": "midrun_recovery_test",
        "customer_id": "customer_recovery",
        "project_id": "project_recovery",
        "repository": "owner/repository",
        "status": scanner_recovery.RECOVERY_REQUIRED_STATUS,
        "authorized_by": "authorized_operator",
        "authorization_scope": "authorized defensive repository assessment",
        "tools_requested": ["gitleaks", "trufflehog"],
        "snapshot_id": "snapshot_github_recovery_test",
        "snapshot_commit_sha": "a" * 40,
        "created_at": "2026-07-15T20:00:00Z",
        "updated_at": "2026-07-15T20:20:00Z",
        "recovery": {
            "state": scanner_recovery.RECOVERY_REQUIRED_STATUS,
            "reason": "stale_process_local_execution",
            "attempt": 0,
            "resume_allowed": True,
        },
    }


def test_mid_status_contract_accepts_exact_scanner_identity() -> None:
    request = MidAssessmentStatusRequest(
        repository="owner/repository",
        scan_id="scan_snapshot_exact_status",
        customer_id="customer_recovery",
        project_id="project_recovery",
        authorization_confirmed=True,
        authorized=True,
        auto_continue=True,
    )
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()

    assert payload["scan_id"] == "scan_snapshot_exact_status"
    assert payload["repository"] == "owner/repository"
    assert payload["customer_id"] == "customer_recovery"
    assert payload["project_id"] == "project_recovery"
    assert payload["auto_continue"] is True


def test_snapshot_recovery_reuses_exact_scan_run_and_snapshot_identity() -> None:
    store = MemoryAdapter()
    record = _snapshot_record()
    store.put("scanner_runs", record["scan_id"], record)
    captured: dict[str, Any] = {}

    class FakeThread:
        def __init__(self, *, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            captured.update({"target": target, "args": args, "daemon": daemon})

        def start(self) -> None:
            captured["started"] = True

    try:
        result = scanner_recovery.resume_interrupted_scanner_run(
            record["scan_id"],
            actor="operator",
            store=store,
            thread_factory=FakeThread,
        )

        assert result["status"] == "queued"
        assert result["resume"]["same_scan_id"] is True
        assert result["resume"]["same_run_id"] is True
        assert result["resume"]["same_snapshot_id"] is True
        assert result["resume"]["same_snapshot_commit_sha"] is True
        assert captured["target"] is snapshot_scanner_worker._run_snapshot_scan
        assert captured["started"] is True
        resumed_scan_id, payload = captured["args"]
        assert resumed_scan_id == record["scan_id"]
        assert payload["scan_id"] == record["scan_id"]
        assert payload["run_id"] == record["run_id"]
        assert payload["repository"] == record["repository"]
        assert payload["tools"] == record["tools_requested"]
        assert payload["snapshot_id"] == record["snapshot_id"]
        assert payload["snapshot_commit_sha"] == record["snapshot_commit_sha"]
    finally:
        scanner_worker.SCAN_JOBS.pop(record["scan_id"], None)


def test_unexpected_snapshot_worker_exception_becomes_terminal_failed_evidence() -> None:
    store = MemoryAdapter()
    scan_id = "scan_snapshot_worker_failure"
    initial = {
        **_snapshot_record(scan_id),
        "status": "running",
        "current_stage": "scanner_suite",
        "active_tool": "trufflehog",
    }
    store.put("scanner_runs", scan_id, initial)
    scanner_worker.SCAN_JOBS[scan_id] = dict(initial)

    def explode(_scan_id: str, _payload: dict[str, Any]) -> None:
        raise RuntimeError("post-scanner serialization failed")

    try:
        assert _run_with_failure_boundary(explode, scan_id, {}, store=store) is None
        failed = store.get("scanner_runs", scan_id)
        assert failed["status"] == "failed"
        assert failed["current_stage"] == "worker_failed"
        assert failed["active_tool"] == ""
        assert failed["failure_type"] == "RuntimeError"
        assert failed["completed_at"]
        assert failed["human_review_required"] is True
        assert failed["client_delivery_allowed"] is False
    finally:
        scanner_worker.SCAN_JOBS.pop(scan_id, None)


def test_mid_live_progress_advances_with_the_active_scanner_tool() -> None:
    result = {
        "status": "running",
        "assessment_type": "mid",
        "report_generation_status": "mid_report_generation_pending",
        "scanner": {
            "status": "running",
            "progress_percent": 78,
            "active_tool": "gitleaks",
            "tools_requested": ["pip-audit", "bandit", "gitleaks", "trufflehog"],
            "tools_run": ["pip-audit", "bandit"],
        },
        "progress": [
            {"step": "repo_evidence", "status": "complete"},
            {
                "step": "scanner_worker",
                "status": "running",
                "message": "Snapshot-bound scanner is running gitleaks.",
                "evidence": {"scanner_progress_percent": 78, "active_tool": "gitleaks"},
            },
            {"step": "evidence_attachment", "status": "pending"},
        ],
    }

    output = attach_mid_live_progress(result)

    assert output["current_stage"] == "scanner_worker"
    assert output["scanner_progress_percent"] == 78
    assert output["progress_percent"] == 52
    assert output["progress_percent"] != 42


def test_mid_terminal_success_reaches_100_only_after_report_and_review_request() -> None:
    core_complete = attach_mid_live_progress(
        {
            "status": "complete",
            "report_generation_status": "mid_report_generation_pending",
            "approval_request": {},
            "progress": [{"step": "reports", "status": "planned"}],
        }
    )
    assert core_complete["progress_percent"] == 86
    assert core_complete["progress_percent"] != 100

    final = attach_mid_live_progress(
        {
            "status": "complete",
            "report_generation_status": "complete",
            "approval_request": {"approval_id": "approval_mid_test", "status": "pending"},
            "progress": [{"step": "approval_request", "status": "complete"}],
        }
    )
    assert final["current_stage"] == "complete"
    assert final["progress_percent"] == 100
