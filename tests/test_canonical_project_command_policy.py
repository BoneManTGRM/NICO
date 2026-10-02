from __future__ import annotations

from pathlib import Path

import pytest

from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import scanner_tool_runners as tools
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def workspace_at(tmp_path):
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    (workspace.repo_dir / "source.ts").write_text("export const owned = 1;\n")
    (workspace.repo_dir / "package.json").write_text("{}")
    (workspace.repo_dir / "package-lock.json").write_text('{"lockfileVersion":3}')
    (workspace.repo_dir / "tsconfig.json").write_text("{}")
    bins = workspace.repo_dir / "node_modules" / ".bin"
    bins.mkdir(parents=True)
    for name in ("eslint", "tsc"):
        (bins / name).write_text("owned executable fixture")
    return workspace


def forbid(*args, **kwargs):
    pytest.fail("denied project command reached preparation, resolution or execution")


@pytest.fixture(params=["canonical", "phase6_installed"])
def handler_installation(request, monkeypatch):
    if request.param == "phase6_installed":
        from nico import phase6_final_remediation_v1 as phase6
        # Force the same scanner replacement used by terminal_authority_bootstrap.
        for name in ("_run_bandit", "_run_eslint", "_run_gitleaks", "_run_trufflehog"):
            monkeypatch.setattr(pipeline, name, getattr(pipeline, name))
        monkeypatch.setattr(pipeline, "_run_bandit", lambda *args: None)
        phase6._patch_scanner_runners()
    return request.param


@pytest.mark.parametrize("policy", [None, "false", "0", "invalid", " true "])
@pytest.mark.parametrize("tool", ["eslint", "typescript"])
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("requires_project_commands", [False, True])
def test_canonical_project_handlers_deny_before_any_execution(monkeypatch, tmp_path, policy, tool, cached, requires_project_commands, handler_installation):
    workspace = workspace_at(tmp_path)
    if policy is None:
        monkeypatch.delenv("NICO_ALLOW_PROJECT_COMMANDS", raising=False)
    else:
        monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", policy)
    monkeypatch.setattr(pipeline.shutil, "which", forbid)
    monkeypatch.setattr(pipeline, "_eslint_config", forbid)
    preparation = tools.ProjectCommandPreparation("completed", workspace.repo_dir, True) if cached else None
    # Caller-controlled spec metadata and cached node_modules are not authority.
    spec = tools.ScannerToolSpec(tool, (tool,), "static", requires_project_commands=requires_project_commands)
    handler = pipeline._run_eslint if tool == "eslint" else pipeline._run_typescript
    payload = handler(spec, workspace, forbid, preparation)
    assert payload["status"] == "unavailable"
    assert payload["verified_for_this_report"] is False
    assert payload["findings"] == []
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in payload["reason"]
    assert not (workspace.root / "scanner-raw").exists()


@pytest.mark.parametrize("policy", [None, "false", "invalid"])
def test_direct_dependency_preparation_obeys_policy(monkeypatch, tmp_path, policy):
    workspace = workspace_at(tmp_path)
    if policy is None:
        monkeypatch.delenv("NICO_ALLOW_PROJECT_COMMANDS", raising=False)
    else:
        monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", policy)
    monkeypatch.setattr(tools.shutil, "which", forbid)
    preparation = tools.prepare_project_commands(workspace, runner=forbid)
    assert preparation.status == "unavailable"
    assert preparation.node_modules_ready is False
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in preparation.reason


@pytest.mark.parametrize("policy", ["true", "TRUE"])
@pytest.mark.parametrize("tool", ["eslint", "typescript"])
def test_explicit_opt_in_preserves_canonical_execution(monkeypatch, tmp_path, policy, tool, handler_installation):
    workspace = workspace_at(tmp_path)
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", policy)
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)
    config = workspace.root / "nico-eslint.config.cjs"
    config.write_text("module.exports = [];")
    monkeypatch.setattr(pipeline, "_eslint_config", lambda *args: (config, ""))
    calls = []

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        calls.append((tuple(args), cwd))
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("[]" if tool == "eslint" else "")
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="", stderr="")

    preparation = tools.ProjectCommandPreparation("completed", workspace.repo_dir, True)
    spec = next(spec for spec in tools.TOOL_SPECS if spec.name == tool)
    handler = pipeline._run_eslint if tool == "eslint" else pipeline._run_typescript
    payload = handler(spec, workspace, runner, preparation)
    assert payload["status"] == "completed"
    assert payload["verified_for_this_report"] is True
    assert len(calls) == 1
    assert calls[0][1] == workspace.repo_dir
    if tool == "typescript":
        assert calls[0][0][-1] == str(workspace.repo_dir / "tsconfig.json")


def test_policy_denial_keeps_inventory_and_other_analyzers(monkeypatch, tmp_path):
    workspace = workspace_at(tmp_path)
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "false")
    commit = "a" * 40
    monkeypatch.setattr(pipeline, "_git_text", lambda *args: commit)
    monkeypatch.setattr("nico.scanner_package_inventory_v1.inspect_package_sources", lambda *args: {})
    inventory_calls = []
    monkeypatch.setattr("nico.node_scanner_applicability_v1.inspect_node_inputs",
                        lambda *args: inventory_calls.append(args) or {})
    monkeypatch.setattr(pipeline, "node_inapplicability_result", lambda *args: None)
    monkeypatch.setattr(pipeline, "prepare_project_commands", forbid)
    monkeypatch.setattr(pipeline, "verify_source_checkout", lambda payload, *args: payload)
    monkeypatch.setattr(pipeline, "_scanner_provenance", lambda *args: {
        "target_commit_sha": commit, "target_repository": "owned/fixture",
        "application_commit_sha": commit, "target_exact_commit_verified": True,
    })
    calls = []
    monkeypatch.setattr("nico.bandit_json_execution_v61.shutil.which", lambda name: f"/tools/{name}")

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        assert Path(args[0]).name == "bandit"
        calls.append("bandit")
        Path(args[args.index("-o") + 1]).write_text('{"errors":[],"metrics":{},"results":[]}')
        stdout_path.write_text("")
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout="", stderr="")
    specs = tuple(next(spec for spec in tools.TOOL_SPECS if spec.name == name)
                  for name in ("eslint", "typescript", "bandit"))
    artifact = pipeline.run_canonical_scanner_tools(workspace, specs, runner=runner)
    assert len(inventory_calls) == 1
    assert calls == ["bandit"]
    assert artifact["tools"]["bandit"]["status"] == "completed"
    for name in ("eslint", "typescript"):
        assert artifact["tools"][name]["status"] == "unavailable"
        assert artifact["tools"][name]["verified_for_this_report"] is False
    assert artifact["project_preparation"]["status"] == "unavailable"
    assert artifact["project_preparation"]["node_modules_ready"] is False
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in artifact["project_preparation"]["reason"]
    assert artifact["required_scanner_completion"] is False
    assert artifact["raw_artifact_capture_complete"] is False
