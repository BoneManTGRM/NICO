"""Regression through interfaces present before and after the durability repair.

Only external Git/tool execution and the SQL driver's connection boundary are
substituted. Actual PostgresAdapter SQL, native worker publication, scanner-store
reload, owner authentication and the inventory route execute on both revisions.
SQLite executes the bound SQL locally; this is not native PostgreSQL deployment
proof. No repair-only module or function is imported by this test.
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import comprehensive_scanner_inventory_v1 as inventory
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import snapshot_scanner_worker as worker
from nico.specialist_access_v1 import install_specialist_access
from nico.storage import STORE, PostgresAdapter


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.cursor()

    def execute(self, sql, parameters=()):
        sql = sql.replace("%s", "?").replace("octet_length(", "length(")
        if not parameters and sql.count(";") > 1:
            self.cursor.executescript(sql)
        else:
            self.cursor.execute(sql, parameters)
        return self

    @staticmethod
    def _row(row):
        if row is None:
            return None
        output = dict(row)
        for key in ("payload", "metadata", "authorization_scope"):
            if key in output and isinstance(output[key], str):
                output[key] = json.loads(output[key])
        return output

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()


class _Connection:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def cursor(self):
        return _Cursor(self.connection)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()


def test_original_scanner_bytes_remain_verified_after_runtime_file_loss_and_store_reopen(tmp_path, monkeypatch):
    database = tmp_path / "existing-postgres-driver-boundary.sqlite3"

    def reopen():
        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._connect = lambda: _Connection(database)
        adapter._jsonb = lambda value: json.dumps(value)
        adapter._init_schema()
        return adapter

    monkeypatch.setattr(STORE, "adapter", reopen())
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "synthetic-retention-owner")
    root = tmp_path / "disposable-runtime-artifacts"
    root.mkdir()
    monkeypatch.setattr(pipeline, "DEFAULT_RAW_ROOT", str(root))
    monkeypatch.setattr(inventory, "DEFAULT_RAW_ROOT", str(root))
    raw = b'{"results":[{"rule_id":"synthetic-rule","message":"Original retained bytes"}]}'
    compressed = gzip.compress(raw, mtime=0)
    raw_hash = hashlib.sha256(raw).hexdigest()
    gzip_hash = hashlib.sha256(compressed).hexdigest()
    blob = root / "original-scanner.json.gz"
    blob.write_bytes(compressed)
    run_id, scan_id, commit = "comprun_retention_regression", "scan_snapshot_retention_regression", "a" * 40
    identity = {"run_id": run_id, "customer_id": "retention-customer", "project_id": "retention-project", "repository": "example/authorized-fixture", "commit_sha": commit}
    native_result = {
        "tool": "semgrep", "status": "completed", "commit_sha": commit,
        "snapshot_commit_sha": commit, "completed": True, "verified": True,
        "raw_artifact_retention_complete": True, "raw_artifact_sha256": raw_hash,
        "raw_artifact": {"storage_key": blob.name, "sha256": raw_hash,
                         "gzip_sha256": gzip_hash, "retained_bytes": len(raw),
                         "gzip_bytes": len(compressed), "redacted": True},
        "scanner_tool_version": "semgrep 1.130.0", "returncode": 0,
        "output_capture_complete": True, "execution_observed_for_this_report": True,
        "findings": [],
    }

    def clone(repository, expected_commit, workspace, environment):
        assert repository == identity["repository"] and expected_commit == commit
        repo = workspace / "repo"
        repo.mkdir()
        return repo, commit, []

    monkeypatch.setattr(worker, "clone_repository_at_snapshot", clone)
    monkeypatch.setattr(worker, "_requested_specs", lambda payload: [SimpleNamespace(name="semgrep")])
    monkeypatch.setattr(worker.tool_runners, "run_scanner_tool", lambda *args: deepcopy(native_result))
    monkeypatch.setattr(worker.base, "SCAN_JOBS", {scan_id: {**identity, "scan_id": scan_id}})
    worker._run_snapshot_scan(scan_id, {**identity, "snapshot_commit_sha": commit})
    published = STORE.get("scanner_runs", scan_id)
    assert published["tools_run"] == ["semgrep"]
    assert published["scanner_results"][0]["raw_artifact_retention_complete"] is True

    run = {"identity": identity, "revision": 1, "stage_results": {"dependency_security_static_analysis": {"scan_id": scan_id}}}
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(_service=SimpleNamespace(load_read_only=lambda requested: deepcopy(run)))
    install_specialist_access(app)
    inventory.install_comprehensive_scanner_inventory(app)
    client = TestClient(app)
    route = f"/assessment/comprehensive-run/{run_id}/scanner-evidence"
    headers = {"X-NICO-Admin-Token": "synthetic-retention-owner"}
    before = client.get(route, headers=headers)
    assert before.status_code == 200
    assert before.json()["scanner_records"][0]["raw_artifact"]["availability"] == "verified"

    # Simulate replacement of the application filesystem and process memory,
    # preserving only the existing database. No scanner rerun or reconstruction.
    blob.unlink()
    worker.base.SCAN_JOBS.clear()
    monkeypatch.setattr(STORE, "adapter", reopen())
    response = client.get(route, headers=headers)
    assert response.status_code == 200
    metadata = response.json()["scanner_records"][0]["raw_artifact"]
    assert metadata["availability"] == "verified", "Published successful retention lost its original scanner bytes after runtime replacement"
    assert metadata["sha256"] == raw_hash
    assert metadata["gzip_sha256"] == gzip_hash
    assert metadata["actual_raw_bytes"] == len(raw)
    assert metadata["actual_compressed_bytes"] == len(compressed)
    assert not blob.exists(), "Inventory GET must not reconstruct or backfill local files"
