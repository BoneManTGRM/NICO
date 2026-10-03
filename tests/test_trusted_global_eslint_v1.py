from pathlib import Path
import json
import os

import pytest

from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import trusted_global_eslint_v1 as static
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerWorkspace, WorkerCommandResult

SPEC = next(x for x in TOOL_SPECS if x.name == "eslint")


@pytest.fixture
def owned(tmp_path, monkeypatch):
    workspace = WorkerWorkspace(tmp_path / "worker")
    workspace.repo_dir.mkdir(parents=True)
    (workspace.repo_dir / "owned.js").write_text("const value = 42;\n")
    (workspace.repo_dir / "typed.ts").write_text("const value: number = 42;\n")
    image = tmp_path / "image"
    modules = image / "node_modules"
    for package, version in static.PINS.items():
        folder = modules / package
        folder.mkdir(parents=True)
        (folder / "package.json").write_text(json.dumps({"name": package, "version": version}))
    for relative in ("eslint/bin/eslint.js", "eslint/lib/api.js", "@typescript-eslint/parser/dist/index.js"):
        path = modules / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// trusted owned image fixture; fake runner handles invocation\n")
    node = image / "node"
    node.write_text("owned trusted node placeholder\n")
    node.chmod(0o755)
    monkeypatch.setattr(static, "MODULE_ROOTS", (modules,))
    monkeypatch.setattr(static, "NODE_BINARIES", (node,))
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "false")
    calls = []

    def deny(*args, **kwargs):
        pytest.fail("project preparation, local configuration, module resolution or environment executed")

    for name in ("prepare_project_commands", "_eslint_config", "_node_env", "resolve_node_project_dir", "_scanner_version"):
        monkeypatch.setattr(pipeline, name, deny)

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        calls.append({"args": args, "cwd": cwd, "limits": limits, "env": extra_env})
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        if args[-1] == "--version":
            stdout_path.write_text("v" + static.PINS["eslint"] + "\n")
        else:
            targets = json.loads(Path(args[-1]).read_text())
            stdout_path.write_text(json.dumps([
                {"filePath": path, "messages": [], "errorCount": 0, "fatalErrorCount": 0, "warningCount": 0}
                for path in targets
            ]))
        return WorkerCommandResult(tuple(args), 0, "", "", stdout_path=str(stdout_path),
                                   stdout_bytes=stdout_path.stat().st_size)

    return workspace, modules, node, calls, runner


@pytest.mark.parametrize("bootstrap", ["pipeline", "phase6"])
def test_false_policy_executes_only_image_global_source_data_contract(owned, monkeypatch, bootstrap):
    workspace, modules, node, calls, runner = owned
    (workspace.repo_dir / "eslint.config.cjs").write_text("throw new Error('MUST_NOT_EXECUTE_CUSTOMER_CONFIG');\n")
    (workspace.repo_dir / "package.json").write_text(json.dumps({"scripts": {"lint": "MUST_NOT_EXECUTE_SCRIPT"}}))
    (workspace.repo_dir / "node_modules" / "@typescript-eslint/parser").mkdir(parents=True)
    (workspace.repo_dir / "node_modules" / "@typescript-eslint/parser/package.json").write_text(
        '{"main":"MUST_NOT_LOAD_CUSTOMER_MODULE.js"}')
    monkeypatch.setenv("NICO_NODE_OPTIONS", "--require=/customer/MUST_NOT_LOAD.js")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/customer/MUST_NOT_LOAD.js")
    monkeypatch.setenv("NODE_PATH", str(workspace.repo_dir / "node_modules"))
    monkeypatch.setenv("NICO_ESLINT_MODULE_ROOT", str(workspace.repo_dir / "node_modules"))
    original = pipeline._run_eslint
    if bootstrap == "phase6":
        from nico import phase6_final_remediation_v1 as phase6
        phase6._patch_scanner_runners()
    try:
        payload = pipeline._run_eslint(SPEC, workspace, runner, None)
    finally:
        pipeline._run_eslint = original
    assert payload["status"] == "completed"
    assert payload["execution_source"] == static.VERSION
    assert payload["project_commands_executed"] is False
    assert payload["repository_configuration_loaded"] is False
    assert payload["scanner_tool_version"] == static.PINS["eslint"]
    assert payload["required_input_count"] == payload["observed_input_count"] == 3
    assert len(calls) == 2
    for call in calls:
        assert call["args"][0] == str(node.resolve())
        assert call["env"]["NODE_OPTIONS"] == call["env"]["NODE_PATH"] == ""
        assert str(workspace.repo_dir) not in call["env"]["PATH"]
    assert calls[0]["cwd"] != workspace.repo_dir
    config = Path(calls[1]["args"][3]).read_text()
    program = Path(calls[1]["args"][1]).read_text()
    assert str(modules / "@typescript-eslint/parser/dist/index.js") in config
    assert "projectService: false" in config and "project: false" in config
    assert "allowInlineConfig: false" in program
    assert "MUST_NOT_" not in config + program


@pytest.mark.parametrize("fault", ["wrong_package_name", "wrong_package_version", "missing_api", "symlink_api"])
def test_unverified_image_tools_never_execute(owned, fault):
    workspace, modules, _, calls, runner = owned
    package = modules / "eslint/package.json"
    if fault == "wrong_package_name":
        package.write_text('{"name":"customer-eslint","version":"9.39.3"}')
    elif fault == "wrong_package_version":
        package.write_text('{"name":"eslint","version":"0.0.0"}')
    else:
        api = modules / "eslint/lib/api.js"
        api.unlink()
        if fault == "symlink_api":
            api.symlink_to(workspace.repo_dir / "owned.js")
    result = static.run_global_static_eslint(SPEC, workspace, runner)
    assert result["status"] == "unavailable"
    assert not calls


@pytest.mark.parametrize("fault", ["source_symlink", "directory_symlink", "output_symlink"])
def test_source_and_output_boundaries_reject_symlinks_before_execution(owned, tmp_path, fault):
    workspace, _, _, calls, runner = owned
    if fault == "source_symlink":
        (workspace.repo_dir / "escape.js").symlink_to(tmp_path / "outside.js")
    elif fault == "directory_symlink":
        (workspace.repo_dir / "escape").symlink_to(tmp_path, target_is_directory=True)
    else:
        (workspace.root / "trusted-global-eslint").symlink_to(workspace.repo_dir, target_is_directory=True)
    result = static.run_global_static_eslint(SPEC, workspace, runner)
    assert result["status"] == "unavailable"
    assert not calls


@pytest.mark.parametrize("fault", ["missing_target", "duplicate_target", "wrong_target", "outside_target",
                                 "malformed_json", "source_changed", "source_replaced_by_symlink",
                                 "incorrect_count", "wrong_native_exit", "unconfigured_input", "ignored_input"])
def test_native_result_population_faults_fail_with_original_raw_evidence(owned, fault):
    workspace, _, _, _, normal = owned

    def runner(args, **kwargs):
        result = normal(args, **kwargs)
        if args[-1] == "--version":
            return result
        raw = kwargs["stdout_path"]
        rows = json.loads(raw.read_text())
        if fault == "missing_target":
            rows.pop()
        elif fault == "duplicate_target":
            rows.append(rows[0])
        elif fault == "wrong_target":
            rows[0]["filePath"] = str(workspace.repo_dir / "package.json")
        elif fault == "outside_target":
            rows[0]["filePath"] = "/must-not-read-unrelated-files/secret.js"
        elif fault == "source_replaced_by_symlink":
            source = workspace.repo_dir / "owned.js"
            source.unlink()
            source.symlink_to(workspace.root / "missing-unrelated.js")
        elif fault in {"unconfigured_input", "ignored_input"}:
            message = ("File ignored because no matching configuration was supplied."
                       if fault == "unconfigured_input" else
                       "File ignored because of a matching ignore pattern.")
            rows[0].update(warningCount=1, messages=[{
                "ruleId": None, "fatal": False, "severity": 1,
                "message": message, "nodeType": None
            }])
        elif fault == "incorrect_count":
            rows[0]["errorCount"] = 5
        elif fault == "wrong_native_exit":
            raw.write_text(json.dumps(rows))
            return WorkerCommandResult(tuple(args), 1, "", "", stdout_path=str(raw), stdout_bytes=raw.stat().st_size)
        elif fault == "malformed_json":
            raw.write_text("{invalid")
            return result
        else:
            (workspace.repo_dir / "owned.js").write_text("const changed = true;\n")
        raw.write_text(json.dumps(rows))
        return result

    payload = static.run_global_static_eslint(SPEC, workspace, runner)
    assert payload["status"] == "failed"
    assert payload["output_capture_complete"] is False
    assert payload["raw_artifact_capture_complete"] is True
    assert payload["verified_for_this_report"] is False


def test_real_target_lint_failure_remains_completed_execution_and_preserves_finding(owned):
    workspace, _, _, _, normal = owned

    def runner(args, **kwargs):
        result = normal(args, **kwargs)
        if args[-1] == "--version":
            return result
        raw = kwargs["stdout_path"]
        rows = json.loads(raw.read_text())
        rows[0].update(errorCount=1, messages=[{
            "ruleId": "no-unreachable", "severity": 2, "message": "Unreachable code.", "line": 1
        }])
        raw.write_text(json.dumps(rows))
        return WorkerCommandResult(tuple(args), 1, "", "", stdout_path=str(raw), stdout_bytes=raw.stat().st_size)

    payload = static.run_global_static_eslint(SPEC, workspace, runner)
    assert payload["status"] == "completed"
    assert payload["returncode"] == 1
    assert payload["output_capture_complete"] is True
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["ruleId"] == "no-unreachable"


def test_large_population_uses_complete_input_data_with_bounded_argv(owned):
    workspace, _, _, calls, runner = owned
    for i in range(1025):
        (workspace.repo_dir / f"file-{i:04}.js").write_text("const value = 1;\n")
    payload = static.run_global_static_eslint(SPEC, workspace, runner)
    assert payload["status"] == "completed"
    assert payload["required_input_count"] == payload["observed_input_count"] == 1027
    assert len(calls[1]["args"]) == 6
    assert len(json.loads(Path(calls[1]["args"][-1]).read_text())) == 1027


def test_existing_image_pins_match_source_contract():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert f"ARG NICO_ESLINT_VERSION={static.PINS['eslint']}" in dockerfile
    assert f"ARG NICO_TYPESCRIPT_ESLINT_VERSION={static.PINS['@typescript-eslint/parser']}" in dockerfile


def test_verified_qt_translation_does_not_enter_typescript_lint_population(owned):
    workspace, _, _, calls, runner = owned
    (workspace.repo_dir / "owned.js").unlink()
    (workspace.repo_dir / "typed.ts").unlink()
    (workspace.repo_dir / "translation.ts").write_text(
        '<TS version="2.1" language="es_MX"><context><name>Owned</name>'
        '<message><source>Hello</source><translation>Hola</translation></message>'
        '</context></TS>')
    result = static.run_global_static_eslint(SPEC, workspace, runner)
    assert result["status"] == "unavailable"
    assert "No applicable JavaScript or TypeScript source inputs" in result["reason"]
    assert not calls
