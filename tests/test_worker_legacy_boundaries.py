"""Owned synthetic records; no scanner thread or assessed code is executed."""
from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from nico import client_job_mode, scanner_recovery, scanner_worker
from nico.snapshot_scanner_resilience_patch import _resume_snapshot_scanner_run
from nico.storage import MemoryAdapter, STORE

JOB = "workerjob_" + "a" * 64


@pytest.fixture
def isolated_store(monkeypatch):
    adapter = MemoryAdapter()
    monkeypatch.setattr(STORE, "adapter", adapter)
    monkeypatch.setattr(scanner_worker, "SCAN_JOBS", {})
    return adapter


@pytest.mark.parametrize("operation", ["read", "create", "export", "exports"])
@pytest.mark.parametrize("exists", [False, True])
def test_public_client_job_routes_cannot_read_overwrite_or_reserve_worker_ids(isolated_store, operation, exists):
    from nico.api.specialist_ship_ready_bootstrap import app
    if exists:
        isolated_store.put("client_jobs", JOB, {"job_id": JOB, "workflow": "assessment_worker_job.v1",
            "customer_id": "owner", "contract": {"private": "scope"}, "lease_id": "e" * 32})
    before = deepcopy(isolated_store.get("client_jobs", JOB))
    with TestClient(app) as client:
        if operation == "read":
            response = client.get("/client-job/" + JOB)
        elif operation == "exports":
            response = client.get("/client-job/" + JOB + "/exports")
        else:
            response = client.post("/client-job/" + ("package" if operation == "create" else "export"),
                json={"job_id": JOB, "customer_id": "another-tenant", "format": "json"})
    assert response.json()["status"] in {"not_found", "blocked"}
    assert "contract" not in response.json() and "lease_id" not in response.json()
    assert isolated_store.get("client_jobs", JOB) == before
    assert isolated_store.list("client_job_exports") == []


def test_direct_client_export_cannot_materialize_worker_payload(isolated_store):
    result = client_job_mode.export_client_job_payload({"job_id": JOB})
    assert result["status"] == "blocked"
    assert isolated_store.list("client_job_exports") == []
    assert isolated_store.get("client_jobs", JOB) is None


def test_ordinary_client_job_retains_create_read_and_export(isolated_store):
    package = client_job_mode.create_client_job_package({"job_id": "client_job_owned_control"})
    assert package["status"] == "ok"
    assert client_job_mode.get_client_job_package(package["job_id"])["human_review_required"]
    exported = client_job_mode.export_client_job_package(package["job_id"])
    assert exported["status"] == "complete" and exported["human_review_required"]
    assert len(client_job_mode.list_client_job_exports(package["job_id"])["exports"]) == 1


def worker_scan(*, marker=True, status="recovery_required"):
    record = {"scan_id": "scan_worker_" + "a" * 40, "run_id": "owned-control-run",
        "customer_id": "owner", "project_id": "owned-control", "repository": "example/owned-control",
        "status": status, "authorized_by": "owned-fixture", "authorization_scope": "synthetic protocol test",
        "snapshot_id": "owned-snapshot", "snapshot_commit_sha": "a" * 40,
        "tools_requested": ["cppcheck"], "updated_at": "2026-01-01T00:00:00Z"}
    if marker:
        record["worker_job_id"] = JOB
    return record


@pytest.mark.parametrize("marker", [True, False])
def test_dedicated_scans_are_not_stale_legacy_work_or_inventory(isolated_store, marker):
    record = worker_scan(marker=marker, status="running")
    isolated_store.put("scanner_runs", record["scan_id"], record)
    assert not scanner_recovery.scanner_is_stale(record)
    assert scanner_recovery._bounded_scanner_records(isolated_store, statuses={"running"}) == []


@pytest.mark.parametrize("marker", [True, False])
@pytest.mark.parametrize("action", ["resume", "snapshot_resume", "close", "transition"])
def test_legacy_recovery_never_mutates_or_executes_dedicated_scans(isolated_store, marker, action):
    record = worker_scan(marker=marker)
    isolated_store.put("scanner_runs", record["scan_id"], record)
    before = deepcopy(isolated_store.get("scanner_runs", record["scan_id"]))
    launched = []
    def capture(**kwargs):
        return SimpleNamespace(start=lambda: launched.append(kwargs))
    if action == "transition":
        result = scanner_recovery.atomic_scanner_transition(record["scan_id"], {"recovery_required"},
            "queued", {}, store=isolated_store)
        assert result is None
    else:
        if action == "close":
            result = scanner_recovery.close_interrupted_scanner_run(record["scan_id"], actor="operator",
                reason_code="no_longer_required", store=isolated_store)
        else:
            resume = _resume_snapshot_scanner_run if action == "snapshot_resume" else scanner_recovery.resume_interrupted_scanner_run
            result = resume(record["scan_id"], actor="operator", store=isolated_store, thread_factory=capture)
        assert result["status"] == "blocked"
        assert result["code"] == "worker_lifecycle_requires_dedicated_job"
    assert launched == []
    assert isolated_store.get("scanner_runs", record["scan_id"]) == before
