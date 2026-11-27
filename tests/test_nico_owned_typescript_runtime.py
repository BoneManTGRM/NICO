"""Contracts at the production scanner seam; synthetic receipts aren't live proof."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from nico import nico_owned_typescript_install_v1 as owned
from nico import nico_ci_typescript_typegen_inputs_v1 as sealer
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.worker_execution import WorkerWorkspace


def _native():
    value = {
        "compiler_version": "6.0.3",
        "roots": ["/project/apps/web/index.ts"],
        "program_inputs": ["/project/apps/web/index.ts"],
        "read_inputs": {"/project/apps/web/index.ts": "6" * 64},
        "diagnostics": [],
    }
    document = {
        "repository": sealer.REPO, "commit": sealer.HISTORICAL_COMMIT,
        "tree": sealer.HISTORICAL_TREE, "result": value,
    }
    raw = json.dumps(document).encode()
    return {
        "outcome": "compiler_observed", "native": value, "_native_stdout": raw,
        "_native_argv": ("/opt/nico-owned-typecheck/node", "--permission"),
        "native_sha256": hashlib.sha256(raw).hexdigest(), "producer_commit": "a" * 40,
        "target_commit": sealer.HISTORICAL_COMMIT, "target_tree": sealer.HISTORICAL_TREE,
    }


def _spec():
    return next(spec for spec in pipeline.TOOL_SPECS if spec.name == "typescript")


def test_same_run_scanner_path_keeps_actual_bytes_then_durable_authority_binds_run(tmp_path):
    workspace = WorkerWorkspace(tmp_path / "work")
    workspace.repo_dir.mkdir(parents=True)
    result = pipeline._owned_typescript_payload(_spec(), workspace, _native())
    blob = result.pop("_raw_artifact_blob")
    assert result["status"] == "completed" and result["execution_observed_for_this_report"] is True
    assert result["scanner_tool_version"] == "TypeScript 6.0.3"
    assert result["scanner_execution_receipt"]["exit_code"] == 0
    assert result["scanner_execution_receipt"]["argv"][-1] == "--permission"
    artifact = {"tools": {"typescript": result}, "raw_artifact_blobs": {"typescript": blob}}
    routine = pipeline.materialize_raw_artifacts
    routine(artifact, tmp_path / "retained", repository=sealer.REPO,
            commit_sha=sealer.HISTORICAL_COMMIT, run_id="actual-release-fixture")
    saved = artifact["raw_artifacts"]["typescript"]
    assert saved["storage_key"].endswith(f"/{sealer.HISTORICAL_COMMIT}/actual-release-fixture/typescript.json.gz")
    data = gzip.decompress((tmp_path / "retained" / saved["storage_key"]).read_bytes())
    assert hashlib.sha256(data).hexdigest() == saved["sha256"]
    assert json.loads(data)["commit"] == sealer.HISTORICAL_COMMIT


@pytest.mark.parametrize("kind", ("absent", "bytes_changed", "reported_tree_changed", "version_changed"))
def test_unverified_native_is_never_current_completion(tmp_path, kind):
    observed = _native()
    if kind == "absent":
        observed = {"outcome": "unavailable", "reason": "no_runtime"}
    elif kind == "bytes_changed":
        observed["_native_stdout"] += b" "
    elif kind == "reported_tree_changed":
        observed["target_tree"] = "c" * 40
    else:
        observed["native"]["compiler_version"] = "5.9.3"
    result = pipeline._owned_typescript_payload(_spec(), WorkerWorkspace(tmp_path), observed)
    assert result["status"] == "unavailable" and result["execution_observed_for_this_report"] is False
    assert "_raw_artifact_blob" not in result


def test_only_the_owned_assessed_revision_is_admitted(monkeypatch, tmp_path):
    monkeypatch.setattr(owned, "ROOT", tmp_path / "missing")
    assert owned.observe(tmp_path, target_repo="Some/Other", target_commit=sealer.HISTORICAL_COMMIT,
                         target_tree=sealer.HISTORICAL_TREE) is None
    assert owned.observe(tmp_path, target_repo=sealer.REPO, target_commit="0" * 40,
                         target_tree=sealer.HISTORICAL_TREE) is None
    assert owned.observe(tmp_path, target_repo=sealer.REPO, target_commit=sealer.HISTORICAL_COMMIT,
                         target_tree=sealer.HISTORICAL_TREE) is None


def test_provider_producer_cannot_come_from_application_fallback(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_REPO_OWNER", "BoneManTGRM")
    monkeypatch.setenv("RAILWAY_GIT_REPO_NAME", "NICO")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("NICO_RELEASE_SHA", "1" * 40)
    with pytest.raises(ValueError):
        owned._provider_producer()
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    assert owned._provider_producer() == "a" * 40
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "other")
    with pytest.raises(ValueError):
        owned._provider_producer()


def test_normal_dispatch_uses_fresh_owned_bridge_with_exact_checkout(monkeypatch, tmp_path):
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir()
    monkeypatch.setattr(pipeline, "_owned_nico_ci", lambda w: True)
    commits = {("rev-parse", "HEAD"): sealer.HISTORICAL_COMMIT,
               ("rev-parse", "HEAD^{tree}"): sealer.HISTORICAL_TREE}
    monkeypatch.setattr(pipeline, "_git_text", lambda w, *args: commits[args])

    def fresh(repo, **identity):
        assert repo == workspace.repo_dir
        assert identity == dict(target_repo=sealer.REPO, target_commit=sealer.HISTORICAL_COMMIT,
                                target_tree=sealer.HISTORICAL_TREE)
        return _native()

    monkeypatch.setattr(owned, "observe", fresh)
    result = pipeline._run_typescript(_spec(), workspace, None, None)
    assert result["execution_source"] == "owned_confined_native_typescript"
    assert result["current_run"] and result["verified_for_this_report"]
    assert result["_raw_artifact_blob"]["present"]


def test_existing_historical_fallback_cannot_turn_into_fresh_proof(monkeypatch, tmp_path):
    from nico import nico_ci_typescript_consumer_v1 as historical
    workspace = WorkerWorkspace(tmp_path)
    monkeypatch.setattr(pipeline, "_owned_nico_ci", lambda w: True)
    monkeypatch.setattr(pipeline, "_git_text", lambda w, *args: "a" * 40)
    monkeypatch.setattr(owned, "observe", lambda *a, **kw: None)
    old = {"current_run": False, "execution_observed_for_this_report": False}
    monkeypatch.setattr(historical, "run", lambda *a: old)
    assert pipeline._run_typescript(_spec(), workspace, None, None) is old
