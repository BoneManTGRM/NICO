"""Exercise the installed snapshot worker, including durable nonexecution bytes."""
import os
import subprocess
import sys

import pytest


SCRIPT = r'''
import importlib, json, shutil, sqlite3, subprocess, sys
from pathlib import Path
from tempfile import TemporaryDirectory
importlib.import_module("nico.api.specialist_ship_ready_bootstrap")
from nico import snapshot_scanner_worker as worker
from nico import scanner_worker, scanner_tool_runners as runners
from nico import v2_snapshot_scanner_authority as authority
from nico import scanner_raw_artifact_storage_v1 as storage
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.storage import MemoryAdapter

order, applicable = json.loads(sys.argv[1])
with TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "source"
    source.mkdir()
    (source / "standalone.js").write_text("console.log(1);")
    if applicable:
        (source / "package.json").write_text('{"devDependencies":{"typescript":"6.0.3"}}')
        (source / "index.ts").write_text('export const n: number = 1;')
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=OpenAI Codex test", "-c", "user.email=codex-test@example.invalid", "commit", "-qm", "Labeled scanner regression fixture")
    commit = git("rev-parse", "HEAD")
    def clone(repository, expected, workspace, env):
        assert expected == commit
        shutil.copytree(source, workspace / "repo")
        return workspace / "repo", commit, []
    worker.clone_repository_at_snapshot = clone
    worker.STORE = MemoryAdapter()
    database = root / "artifacts.sqlite3"
    def reopen():
        return storage.ScannerArtifactStore(lambda: sqlite3.connect(database), dialect="sqlite")
    reopen().ensure_schema()
    storage._default_store = reopen
    raw_root = root / "raw"
    pipeline.DEFAULT_RAW_ROOT = authority.DEFAULT_RAW_ROOT = str(raw_root)
    called = []
    def prepare(workspace, **kwargs):
        generated = workspace.repo_dir / "node_modules/typescript"
        generated.mkdir(parents=True, exist_ok=True)
        (generated / "package.json").write_text('{"name":"typescript"}')
        (generated / "generated.d.ts").write_text("declare const generated: string;")
        return runners.ProjectCommandPreparation("unavailable", workspace.repo_dir, False, "labeled test preparation")
    authority.prepare_project_commands = prepare
    original_problem = authority._run_problem_tool
    def problem(spec, workspace, runner, preparation):
        called.append(spec.name)
        if spec.name == "eslint" or applicable:
            return pipeline._unavailable(spec, "labeled delegated scanner test", source="test")
        return original_problem(spec, workspace, runner, preparation)
    authority._run_problem_tool = problem
    selected = {spec.name: spec for spec in runners.TOOL_SPECS}
    worker._requested_specs = lambda payload: [selected[name] for name in order]
    scan = "scan_snapshot_labeled_node_test"
    binding = dict(run_id="comprun_labeled_node_test", scan_id=scan, customer_id="test-owner", project_id="test-project", repository="example/authorized", snapshot_commit_sha=commit)
    scanner_worker.SCAN_JOBS[scan] = dict(binding)
    worker._run_snapshot_scan(scan, binding)
    records = {r["tool"]: r for r in scanner_worker.SCAN_JOBS[scan]["scanner_results"]}
    for name in ("npm-audit", "typescript"):
        record = records[name]
        if applicable:
            assert name in called and record["status"] != "not_applicable", record
            continue
        assert record["status"] == "not_applicable", record
        assert name not in called
        assert not record["completed"] and not record["verified"]
        assert record["execution_observed_for_this_report"] is False
        assert not record.get("failure_reason"), record
        assert record["applicability_evidence"]["commit_sha"] == commit
        assert record["applicability_evidence"]["typescript_input_paths"] == []
        read_binding = {key: record[key] for key in storage.BINDING_FIELDS}
        result = storage.read_scanner_artifact(record, binding=read_binding)
        assert result.metadata["availability"] == "verified", result.metadata
        assert json.loads(result.raw)["inventory"] == record["applicability_evidence"]
        wrong = {**read_binding, "run_id": "comprun_other_owner"}
        assert storage.read_scanner_artifact(record, binding=wrong).metadata["availability"] == "source_mismatch"
    print("installed snapshot path verified; applicability is not scanner completion")
'''


@pytest.mark.parametrize("order", [
    ["eslint", "npm-audit", "typescript"],
    ["typescript", "npm-audit", "eslint"],
])
@pytest.mark.parametrize("applicable", [False, True])
def test_installed_snapshot_worker_retains_applicability_before_preparation(order, applicable):
    import json
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, json.dumps([order, applicable])],
        env={**os.environ, "NICO_DISABLE_POSTGRES": "true", "NICO_ALLOW_PROJECT_COMMANDS": "true"},
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
