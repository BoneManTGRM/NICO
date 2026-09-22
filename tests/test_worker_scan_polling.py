import pytest

from nico import scanner_worker
from nico.storage import MemoryAdapter


def test_worker_scan_reads_durable_completion_instead_of_cached_queue(monkeypatch):
    store = MemoryAdapter()
    queued = {"scan_id": "remote", "status": "queued", "worker_job_id": "workerjob_test"}
    completed = {**queued, "status": "complete", "receipt_sha256": "a" * 64}
    monkeypatch.setattr(scanner_worker, "STORE", store)
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {"remote": queued})
    store.put("scanner_runs", "remote", completed)
    assert scanner_worker.get_scan("remote") == store.get("scanner_runs", "remote")
    assert scanner_worker.get_scan("remote")["status"] == "complete"


def test_missing_durable_worker_scan_does_not_reuse_cached_success(monkeypatch):
    monkeypatch.setattr(scanner_worker, "STORE", MemoryAdapter())
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {
        "remote": {"scan_id": "remote", "status": "complete", "worker_job_id": "workerjob_test"},
    })
    assert scanner_worker.get_scan("remote") == {"status": "not_found", "scan_id": "remote"}


def test_legacy_in_process_scan_keeps_existing_live_progress(monkeypatch):
    store = MemoryAdapter()
    store.put("scanner_runs", "local", {"scan_id": "local", "status": "queued"})
    live = {"scan_id": "local", "status": "running", "progress_percent": 60}
    monkeypatch.setattr(scanner_worker, "STORE", store)
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {"local": live})
    assert scanner_worker.get_scan("local") == live


def test_public_payload_cannot_select_a_worker_contract(monkeypatch):
    from types import SimpleNamespace
    from nico import snapshot_scanner_worker as snapshot
    from nico import assessment_worker_receipts as receipts
    from nico.storage import STORE
    monkeypatch.setattr(STORE, "adapter", MemoryAdapter())
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {})
    launched = []
    monkeypatch.setattr(snapshot.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: launched.append(kwargs)))
    monkeypatch.setattr(receipts, "enqueue_snapshot_scan", lambda *args: pytest.fail("public payload selected internal worker authority"))
    result = snapshot.start_snapshot_scan({"authorized": True, "authorized_by": "owned_fixture",
        "authorization_scope": "synthetic no-execution fixture", "repository": "example/owned-control",
        "snapshot_id": "fixture", "snapshot_commit_sha": "a" * 40,
        "provider_access_mode": "anonymous_public", "provider_credential_used": False,
        "worker_contract": {"arbitrary": "command"}})
    assert result["status"] == "queued" and "worker_job_id" not in result
    assert len(launched) == 1


def test_ordinary_snapshot_worker_still_reaches_existing_acquisition(monkeypatch):
    from nico import snapshot_scanner_worker as snapshot
    from nico.storage import STORE
    monkeypatch.setattr(STORE, 'adapter', MemoryAdapter())
    monkeypatch.setattr(scanner_worker, 'SCAN_JOBS', {'owned-legacy': {'scan_id': 'owned-legacy'}})
    observed = []
    def acquire(*args):
        observed.append(args[1])
        return None, '', ['Owned fixture has no remote source.']
    monkeypatch.setattr(snapshot, 'clone_repository_at_snapshot', acquire)
    monkeypatch.setattr(snapshot, '_requested_specs', lambda payload: [])
    snapshot._run_snapshot_scan('owned-legacy', {'repository': 'example/owned-control',
        'snapshot_commit_sha': 'a'*40, 'provider_access_mode': 'authenticated_read_only',
        'provider_credential_used': True})
    assert observed == ['a'*40]
    assert scanner_worker.SCAN_JOBS['owned-legacy']['status'] != 'running'
