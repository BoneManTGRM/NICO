from __future__ import annotations

import json
from pathlib import Path

from nico import hosted_secret_scanner_execution_patch as secret
from nico import hosted_static_scanner_execution_patch as static
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    root = tmp_path / "workspace"
    (root / "repo").mkdir(parents=True)
    return WorkerWorkspace(root=root)


def _result(
    stdout: str,
    *,
    returncode: int = 0,
    stderr: str = "",
    timed_out: bool = False,
    output_truncated: bool = False,
) -> WorkerCommandResult:
    return WorkerCommandResult(
        args=("scanner",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_truncated=output_truncated,
    )


def _spec(name: str, category: str = "static") -> ScannerToolSpec:
    return ScannerToolSpec(name=name, command=(name,), category=category)


def test_typescript_lint_script_is_not_relabelled_as_eslint(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    web = workspace.repo_dir / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(
        json.dumps({"scripts": {"lint": "tsc --noEmit"}}),
        encoding="utf-8",
    )
    (web / "tsconfig.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOW_PROJECT_COMMANDS", "true")

    eslint_command, eslint_cwd, eslint_reason, eslint_source = static._eslint_command(workspace)
    ts_command, ts_cwd, ts_reason, ts_source = static._typescript_command(workspace)

    assert eslint_command is None
    assert eslint_cwd == web
    assert "does not execute ESLint" in str(eslint_reason)
    assert eslint_source == "eslint_contract_unavailable"
    assert ts_command == ("npm", "run", "lint")
    assert ts_cwd == web
    assert ts_reason is None
    assert ts_source == "typescript_npm_script"


def test_semgrep_invalid_json_fails_closed_even_with_zero_exit(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = static._completed(
        _spec("semgrep"),
        _result("not-json", returncode=0),
        cwd=workspace.repo_dir,
        command=("semgrep", "scan", "--json"),
        source="test",
    )

    assert payload["status"] == "failed"
    assert payload["verified_for_this_report"] is False
    assert payload["output_parseable"] is False
    assert payload["parser_status"] == "invalid_json"


def test_semgrep_parseable_json_is_verified_when_execution_completes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = static._completed(
        _spec("semgrep"),
        _result('{"results": [], "errors": []}', returncode=0),
        cwd=workspace.repo_dir,
        command=("semgrep", "scan", "--json"),
        source="test",
    )

    assert payload["status"] == "completed"
    assert payload["verified_for_this_report"] is True
    assert payload["output_parseable"] is True
    assert payload["parser_status"] == "parseable_json"


def test_truncated_static_output_cannot_be_verified(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = static._completed(
        _spec("bandit"),
        _result('{"results": []}', output_truncated=True),
        cwd=workspace.repo_dir,
        command=("bandit", "-r", ".", "-f", "json"),
        source="test",
    )

    assert payload["status"] == "failed"
    assert payload["verified_for_this_report"] is False
    assert payload["parser_status"] == "output_truncated"


def test_gitleaks_command_uses_bounded_report_file(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(secret.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    command, cwd, reason = secret._gitleaks_command(workspace)

    assert cwd == workspace.repo_dir
    assert reason is None
    assert command is not None
    assert "--report-path" in command
    report_index = command.index("--report-path")
    assert command[report_index + 1] == str(workspace.root / "gitleaks-report.json")


def test_clean_gitleaks_exit_zero_is_explicit_empty_verified_report(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = secret._completed(
        _spec("gitleaks", "secret"),
        _result("", returncode=0),
        cwd=workspace.repo_dir,
        command=("gitleaks", "detect", "--report-format", "json"),
        history={"full_history_verified": True, "history_depth": "full"},
        source="test",
    )

    assert payload["status"] == "completed"
    assert payload["findings_count"] == 0
    assert payload["verified_for_this_report"] is True
    assert payload["output_parseable"] is True
    assert payload["parser_status"] == "parseable_json"


def test_empty_gitleaks_nonzero_exit_is_not_treated_as_clean(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = secret._completed(
        _spec("gitleaks", "secret"),
        _result("", returncode=1),
        cwd=workspace.repo_dir,
        command=("gitleaks", "detect", "--report-format", "json"),
        history={"full_history_verified": True, "history_depth": "full"},
        source="test",
    )

    assert payload["status"] == "failed"
    assert payload["verified_for_this_report"] is False
    assert payload["parser_status"] == "empty_output"


def test_invalid_trufflehog_json_lines_fail_closed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = secret._completed(
        _spec("trufflehog", "secret"),
        _result('{"DetectorName":"Example"}\nnot-json', returncode=0),
        cwd=workspace.repo_dir,
        command=("trufflehog", "git", "file://repo", "--json"),
        history={"full_history_verified": True, "history_depth": "full"},
        source="test",
    )

    assert payload["status"] == "failed"
    assert payload["verified_for_this_report"] is False
    assert payload["parser_status"] == "invalid_json_line"


def test_secret_timeout_never_becomes_verified(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    payload = secret._completed(
        _spec("trufflehog", "secret"),
        _result("", returncode=124, timed_out=True),
        cwd=workspace.repo_dir,
        command=("trufflehog", "git", "file://repo", "--json"),
        history={"full_history_verified": True, "history_depth": "full"},
        source="test",
    )

    assert payload["status"] == "timeout"
    assert payload["verified_for_this_report"] is False
    assert payload["output_parseable"] is False
    assert payload["parser_status"] == "timeout"
