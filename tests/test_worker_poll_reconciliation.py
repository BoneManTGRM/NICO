"""Synthetic lifecycle checks; native PostgreSQL proof covers persistence."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from nico.assessment_worker_jobs import JobConflict, WorkerJobs
from scripts.worker_protocol_fixture import identity


def state(**changes):
    return dict(status="running", deadline_epoch=120, lease_until_epoch=30,
                attempts=1, limits={"max_attempts": 2}, lease_id="e" * 32,
                receipt_sha256="", failure_code="", **changes)


def poll(payload, now):
    jobs = object.__new__(WorkerJobs)
    writes = []
    def transaction(job, operation):
        assert job == identity()
        result, changed = operation(payload, now, None)
        if changed:
            writes.append(deepcopy(payload))
        return result
    jobs._change = transaction
    return jobs.poll(identity()), writes


@pytest.mark.parametrize("now,expected,code", [
    (29, "running", ""), (30, "queued", "worker_lease_expired"),
    (120, "budget_exhausted", "wall_budget_exhausted"),
])
def test_poll_resolves_missing_worker_using_server_deadlines(now, expected, code):
    payload = state()
    result, writes = poll(payload, now)
    assert result["status"] == expected and result["failure_code"] == code
    assert result["attempts"] == 1 and result["deadline_epoch"] == 120
    assert bool(writes) is (now >= 30)
    if now >= 30:
        with pytest.raises(JobConflict):
            WorkerJobs._owned(result, "e" * 32, now)


def test_poll_exhausted_attempts_cannot_queue_another_retry():
    payload = state()
    payload["attempts"] = 2
    result, writes = poll(payload, 30)
    assert result["status"] == "failed"
    assert result["failure_code"] == "attempt_budget_exhausted" and len(writes) == 1


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "budget_exhausted"])
def test_poll_preserves_every_terminal_receipt_even_after_deadline(status):
    payload = state()
    payload.update(status=status, receipt_sha256="f" * 64)
    before = deepcopy(payload)
    result, writes = poll(payload, 1000)
    assert result == before and not writes


def test_public_scan_poll_uses_durable_worker_reconciliation(monkeypatch):
    from nico import scanner_worker
    from nico.storage import MemoryAdapter
    from types import SimpleNamespace
    job = identity()
    store = MemoryAdapter()
    scan = {"scan_id": job.scan_id, "worker_job_id": job.job_id,
            "status": "running", "customer_id": job.customer_id,
            "project_id": job.project_id, "run_id": job.run_id,
            "repository": job.repository_id, "snapshot_commit_sha": job.revision}
    store.put("scanner_runs", job.scan_id, scan)
    monkeypatch.setattr(scanner_worker, "STORE", SimpleNamespace(adapter=store, get=store.get))
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {job.scan_id: scan})
    monkeypatch.setattr(WorkerJobs, "__init__", lambda self, adapter: None)
    monkeypatch.setattr(WorkerJobs, "get_by_id", lambda self, job_id: {"identity": asdict(job)})
    calls = []
    def reconcile(self, actual):
        calls.append(actual)
        store.put("scanner_runs", job.scan_id, {**scan, "status": "failed"})
    monkeypatch.setattr(WorkerJobs, "poll", reconcile, raising=False)
    assert scanner_worker.get_scan(job.scan_id)["status"] == "failed"
    assert calls == [job]
