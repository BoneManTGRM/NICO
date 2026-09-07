from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest


def sha(value): return hashlib.sha256(value).hexdigest()


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    from nico import scanner_raw_artifact_storage_v1 as module
    database = tmp_path / "durable.sqlite3"
    def reopen(): return module.ScannerArtifactStore(lambda: sqlite3.connect(database), dialect="sqlite")
    store = reopen()
    store.ensure_schema()
    monkeypatch.setattr(module, "_default_store", lambda: store)
    root = tmp_path / "disposable"
    root.mkdir()
    raw = b'{"results":[{"message":"synthetic retained scanner evidence"}]}'
    compressed = gzip.compress(raw, mtime=0)
    path = root / "scanner.gz"
    path.write_bytes(compressed)
    binding = {"run_id": "comprun_bytes", "scan_id": "scan_snapshot_bytes", "customer_id": "customer-bytes", "project_id": "project-bytes", "repository": "example/authorized", "commit_sha": "a" * 40, "scanner_name": "semgrep"}
    record = {"tool": "semgrep", "status": "completed", "commit_sha": "a" * 40, "raw_artifact_retention_complete": True, "raw_artifact_sha256": sha(raw), "raw_artifact": {"storage_key": "scanner.gz", "sha256": sha(raw), "gzip_sha256": sha(compressed), "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True}, "completed": True, "verified": True}
    return module, store, reopen, root, path, binding, record, raw, compressed


def test_original_bytes_survive_disposable_file_loss_and_database_reopen(artifacts, monkeypatch):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    persisted = m.persist_scanner_result(record, binding=binding, raw_root=root)
    assert persisted["raw_artifact"]["storage_backend"] == "postgres"
    assert persisted["raw_artifact_retention_complete"] is True
    assert "gzip_hex" not in json.dumps(persisted)
    assert "gzip_blob" not in json.dumps(persisted)
    path.unlink()
    monkeypatch.setattr(m, "_default_store", reopen)
    result = m.read_scanner_artifact(persisted, binding=binding, raw_root=root)
    assert result.metadata["availability"] == "verified"
    assert result.metadata["storage_backend"] == "postgres"
    assert result.compressed == compressed
    assert result.raw == raw
    assert sha(result.compressed) == record["raw_artifact"]["gzip_sha256"]
    assert sha(result.raw) == record["raw_artifact"]["sha256"]
    # Read-only inspection must not backfill or recreate files.
    assert not path.exists()


@pytest.mark.parametrize("field", ["run_id", "scan_id", "customer_id", "project_id", "repository", "commit_sha", "scanner_name"])
def test_durable_reader_rejects_every_wrong_binding(artifacts, field):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    persisted = m.persist_scanner_result(record, binding=binding, raw_root=root)
    wrong = {**binding, field: "wrong"}
    result = m.read_scanner_artifact(persisted, binding=wrong, raw_root=root)
    assert result.metadata["availability"] == "source_mismatch"
    assert result.raw is None and result.compressed is None


def test_immutable_insert_is_idempotent_and_conflicting_bytes_cannot_overwrite(artifacts):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    persisted = m.persist_scanner_result(record, binding=binding, raw_root=root)
    assert m.persist_scanner_result(record, binding=binding, raw_root=root)["raw_artifact"] == persisted["raw_artifact"]
    changed = b'{"different":"synthetic observation"}'
    other = gzip.compress(changed, mtime=0)
    path.write_bytes(other)
    update = deepcopy(record)
    update["raw_artifact"].update(sha256=sha(changed), gzip_sha256=sha(other), retained_bytes=len(changed), gzip_bytes=len(other))
    update["raw_artifact_sha256"] = sha(changed)
    rejected = m.persist_scanner_result(update, binding=binding, raw_root=root)
    assert rejected["raw_artifact_retention_complete"] is False
    assert rejected["raw_artifact_durability"]["reason"] == "immutable_artifact_conflict"
    assert m.read_scanner_artifact(persisted, binding=binding, raw_root=root).compressed == compressed


@pytest.mark.parametrize("failure", ["memory", "database", "bad_hash", "missing_file"])
def test_write_failure_never_claims_retained_success(artifacts, monkeypatch, failure):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    if failure == "memory": monkeypatch.setattr(m, "_default_store", lambda: None)
    if failure == "database":
        def fail(*args, **kwargs): raise RuntimeError("DO-NOT-DISCLOSE-CONNECTION-DETAILS")
        monkeypatch.setattr(store, "put", fail)
    if failure == "bad_hash": record["raw_artifact"]["gzip_sha256"] = "b" * 64
    if failure == "missing_file": path.unlink()
    output = m.persist_scanner_result(record, binding=binding, raw_root=root)
    assert output["raw_artifact_retention_complete"] is False
    assert output["verified"] is False and output["completed"] is False
    assert output["status"] == "failed"
    assert "DO-NOT-DISCLOSE" not in json.dumps(output)


def test_legacy_missing_is_explicit_and_never_backfilled(artifacts, monkeypatch):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    path.unlink()
    monkeypatch.setattr(m, "_default_store", lambda: pytest.fail("legacy file read must not discover or write database records"))
    result = m.read_scanner_artifact(record, binding=binding, raw_root=root)
    assert result.metadata["availability"] == "missing"
    assert result.raw is None


def test_database_corruption_and_missing_binding_fail_closed(artifacts):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    persisted = m.persist_scanner_result(record, binding=binding, raw_root=root)
    result = m.read_scanner_artifact(persisted, binding=None, raw_root=root)
    assert result.metadata["availability"] == "source_mismatch"
    with store.connect() as conn:
        conn.execute("UPDATE scanner_raw_artifacts SET gzip_blob=?", (b"corrupted",))
    result = m.read_scanner_artifact(persisted, binding=binding, raw_root=root)
    assert result.metadata["availability"] == "compressed_checksum_mismatch"
    assert result.raw is None and result.compressed is None


def test_nonapplicability_is_preserved_without_completion_credit(artifacts):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    native = {"tool": "osv-scanner", "status": "not_applicable", "applicable": False, "evidence_required": False, "applicability_evidence": {"manifest_count": 0}, "completed": False}
    result = m.persist_scanner_result(native, binding={**binding, "scanner_name": "osv-scanner"}, raw_root=root)
    assert result["status"] == "not_applicable"
    assert result["completed"] is False


@pytest.mark.parametrize("failure", [False, True])
def test_snapshot_worker_persists_before_publishing_tool_retention(artifacts, monkeypatch, failure):
    from types import SimpleNamespace
    from nico import snapshot_scanner_worker as worker
    from nico import scanner_evidence_pipeline_v1 as pipeline
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    monkeypatch.setattr(pipeline, "DEFAULT_RAW_ROOT", str(root))
    if failure:
        monkeypatch.setattr(m, "_default_store", lambda: None)
    saved = []
    def put(table, item_id, payload):
        if payload.get("scanner_results"):
            result = payload["scanner_results"][0]
            if result.get("raw_artifact_retention_complete"):
                assert store.get(result["raw_artifact"]["artifact_id"], limit=100000)["compressed"] == compressed
        saved.append(deepcopy(payload))
    monkeypatch.setattr(worker, "STORE", SimpleNamespace(put=put, audit=lambda *args, **kwargs: None))
    def clone(repository, commit, workspace, environment):
        repo = workspace / "repo"
        repo.mkdir()
        return repo, commit, []
    monkeypatch.setattr(worker, "clone_repository_at_snapshot", clone)
    monkeypatch.setattr(worker, "_requested_specs", lambda payload: [SimpleNamespace(name="semgrep")])
    monkeypatch.setattr(worker.tool_runners, "run_scanner_tool", lambda *args: deepcopy(record))
    monkeypatch.setattr(worker.base, "SCAN_JOBS", {binding["scan_id"]: {"scan_id": binding["scan_id"], "run_id": binding["run_id"]}})
    worker._run_snapshot_scan(binding["scan_id"], {**binding, "snapshot_commit_sha": binding["commit_sha"]})
    final = saved[-1]
    retained = final["scanner_results"][0]
    assert retained["raw_artifact_retention_complete"] is (not failure)
    if failure:
        assert retained["verified"] is False
        assert final["tools_run"] == []
        assert final["failed_tools"] == ["semgrep"]
    else:
        assert final["tools_run"] == ["semgrep"]


def test_durable_missing_never_falls_back_to_disposable_file(artifacts):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    persisted = m.persist_scanner_result(record, binding=binding, raw_root=root)
    with store.connect() as conn:
        conn.execute("DELETE FROM scanner_raw_artifacts")
    assert path.exists()
    assert m.read_scanner_artifact(persisted, binding=binding, raw_root=root).metadata["availability"] == "missing"


def test_wrong_source_cannot_be_written_as_current_scan(artifacts):
    m, store, reopen, root, path, binding, record, raw, compressed = artifacts
    record["repository"] = "example/another"
    result = m.persist_scanner_result(record, binding=binding, raw_root=root)
    assert result["raw_artifact_durability"]["reason"] == "source_mismatch"
    assert result["raw_artifact_retention_complete"] is False
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM scanner_raw_artifacts").fetchone()[0] == 0
