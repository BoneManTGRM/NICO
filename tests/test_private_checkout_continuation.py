from copy import deepcopy
import hashlib
import json
import time
from uuid import uuid4

import pytest

from nico import comprehensive_private_checkout_continuation_v1 as recovery
from nico import comprehensive_native_providers as providers
from nico.comprehensive_run_record import apply_comprehensive_stage_result, create_comprehensive_run_record
from nico.comprehensive_run_service import ComprehensiveRunService
from tests.test_comprehensive_run_service import _store
from tests.test_scanner_recovery import _MemoryStore


@pytest.fixture
def case(tmp_path, monkeypatch):
    from nico.comprehensive_background_stage_execution_v1 import reset_background_stage_tasks_for_tests
    reset_background_stage_tasks_for_tests()
    record = create_comprehensive_run_record(run_id=f"comprun_private_{uuid4().hex}", repository="example/private", commit_sha="a" * 40,
        customer_id="customer", project_id="project", evidence_ledger_id="ledger_private", authorized=True)
    identity = record["identity"]
    snapshot = dict(status="attached", repository=identity["repository"], snapshot_id="snapshot_private",
                    commit_sha=identity["commit_sha"], access_mode="authenticated_read_only", credential_used=True)
    for stage in recovery.COMPREHENSIVE_STAGES[:3]:
        record = apply_comprehensive_stage_result(record, stage_id=stage, result={"status": "complete", "snapshot": snapshot} if stage == "immutable_repository_snapshot" else {"status": "complete"})
    record = apply_comprehensive_stage_result(record, stage_id=recovery.STAGE,
        result={"status": "blocked", "scan_id": "scan_snapshot_private", "reason": "snapshot_scanner_not_verified"})
    prior = dict(scan_id="scan_snapshot_private", run_id=identity["run_id"], customer_id="customer", project_id="project",
        repository=identity["repository"], snapshot_id="snapshot_private", snapshot_commit_sha=identity["commit_sha"],
        status="unavailable", current_stage="snapshot_verification_failed", scanner_results=[], tools_run=[],
        snapshot_match=False, actual_commit_sha="", authorized_by="owner", authorization_scope="private fixture")
    scan = {**prior, "status": "complete", "snapshot_match": True, "actual_commit_sha": identity["commit_sha"],
        "current_stage": "complete", "tools_requested": ["gitleaks", "typescript"], "tools_run": ["gitleaks"],
        "unavailable_tools": ["typescript"], "scanner_results": [{"tool": "gitleaks", "status": "completed"}],
        recovery.MARKER: {"previous_failure": deepcopy(prior), "attempt": 1, "automatic_retry": False,
            "requested_at": "2026-09-08T02:51:36Z", "failure_fingerprint": hashlib.sha256(json.dumps(prior, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}}
    scans = _MemoryStore([scan])
    monkeypatch.setattr(recovery, "STORE", scans)
    monkeypatch.setattr(providers, "get_scan", lambda scan_id: scans.get("scanner_runs", scan_id))
    def no_new_scan(*args, **kwargs):
        pytest.fail("Recovery must use the preserved scan")
    monkeypatch.setattr(providers, "start_snapshot_scan", no_new_scan)
    store = _store(tmp_path / "runs.sqlite")
    store.create(record)
    service = ComprehensiveRunService(store, {"scanner_suite": providers.scanner_suite_provider})
    return record, scans, service


def test_ordinary_service_resumes_terminal_failure_and_preserves_limitations(case):
    before, scans, service = case
    scan_before = deepcopy(scans.records)
    result = service.resume(before["identity"]["run_id"], max_stages=1)
    deadline = time.monotonic() + 2
    while recovery.STAGE not in result["completed_stages"] and result["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = service.resume(before["identity"]["run_id"], max_stages=1)
    assert result["status"] == "running"
    assert result["completed_stages"] == [*before["completed_stages"], recovery.STAGE]
    assert result["identity"] == before["identity"]
    assert result["stage_results"][recovery.STAGE]["scan_id"] == "scan_snapshot_private"
    assert result["stage_results"][recovery.STAGE]["scanner"]["unavailable_tools"] == ["typescript"]
    assert result["recovery_history"][-1]["previous_stage_result"] == before["stage_results"][recovery.STAGE]
    assert scans.records == scan_before
    assert result["human_review_completed"] is False and result["client_delivery_allowed"] is False


@pytest.mark.parametrize("field,value", [("status", "running"), ("snapshot_match", False),
    ("actual_commit_sha", "b" * 40), ("run_id", "comprun_other"), ("customer_id", "other"),
    ("project_id", "other"), ("repository", "other/repo"), ("snapshot_id", "wrong"),
    ("snapshot_commit_sha", "b" * 40), (recovery.MARKER, {})])
def test_incomplete_or_unbound_scan_cannot_reopen_run(case, field, value):
    before, scans, service = case
    scans.records["scan_snapshot_private"][field] = value
    assert service.resume(before["identity"]["run_id"], max_stages=1) == before


def test_changed_prior_failure_cannot_authorize_continuation(case):
    before, scans, service = case
    scans.records["scan_snapshot_private"][recovery.MARKER]["previous_failure"]["authorization_scope"] = "changed"
    assert service.resume(before["identity"]["run_id"], max_stages=1) == before


def test_native_executor_failure_stays_terminal_without_repeat(case):
    before, scans, service = case
    def blocked(context):
        return {"status": "blocked", "reason": "snapshot_scanner_not_verified", "scan_id": "scan_snapshot_private"}
    service._stage_executors[recovery.STAGE] = blocked
    result = service.resume(before["identity"]["run_id"], max_stages=1)
    deadline = time.monotonic() + 2
    while result["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
        result = service.resume(before["identity"]["run_id"], max_stages=1)
    assert result["status"] == "blocked"
    assert result["stage_results"][recovery.STAGE].get("reason") == "snapshot_scanner_not_verified", result["stage_results"][recovery.STAGE]
    assert len(result["recovery_history"]) == 1
    assert service.resume(before["identity"]["run_id"], max_stages=1) == result
