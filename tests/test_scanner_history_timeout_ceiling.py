from __future__ import annotations

from pathlib import Path

from nico import hosted_secret_scanner_execution_patch as secret
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    root = tmp_path / "workspace"
    (root / "repo").mkdir(parents=True)
    return WorkerWorkspace(root=root)


def _history() -> dict[str, object]:
    return {
        "history_depth": "full",
        "full_history_verified": True,
        "commit_count": 500,
        "head_sha": "a" * 40,
        "reason": "",
    }


def test_gitleaks_timeout_configuration_is_a_hard_ceiling(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", "420")
    monkeypatch.setenv("NICO_GITLEAKS_TIMEOUT_SECONDS", "240")
    monkeypatch.setattr(secret, "_history_metadata", lambda _workspace: _history())
    monkeypatch.setattr(secret.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    observed: dict[str, object] = {}

    def runner(command, *, cwd, limits):
        observed["command"] = command
        observed["cwd"] = cwd
        observed["timeout_seconds"] = limits.timeout_seconds
        observed["max_output_chars"] = limits.max_output_chars
        return WorkerCommandResult(
            args=tuple(command),
            returncode=0,
            stdout="[]",
            stderr="",
        )

    payload = secret._run_secret_tool(
        ScannerToolSpec(
            name="gitleaks",
            command=("gitleaks",),
            category="secret",
            timeout_seconds=900,
            max_output_chars=80_000,
            scans_git_history=True,
        ),
        workspace,
        runner=runner,
    )

    assert observed["timeout_seconds"] == 240
    assert observed["max_output_chars"] == 500_000
    assert payload["status"] == "completed"
    assert payload["requested_timeout_seconds"] == 900
    assert payload["timeout_limit_seconds"] == 240
    assert payload["effective_timeout_seconds"] == 240
    assert payload["timeout_policy"] == "hard_ceiling"
    assert payload["pipeline_blocking_allowed"] is False


def test_trufflehog_uses_its_bounded_tool_ceiling(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", "420")
    monkeypatch.setenv("NICO_TRUFFLEHOG_TIMEOUT_SECONDS", "300")
    monkeypatch.setattr(secret, "_history_metadata", lambda _workspace: _history())
    monkeypatch.setattr(secret.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    observed: dict[str, int] = {}

    def runner(command, *, cwd, limits):
        observed["timeout_seconds"] = limits.timeout_seconds
        return WorkerCommandResult(
            args=tuple(command),
            returncode=0,
            stdout="",
            stderr="",
        )

    payload = secret._run_secret_tool(
        ScannerToolSpec(
            name="trufflehog",
            command=("trufflehog",),
            category="secret",
            timeout_seconds=900,
            scans_git_history=True,
        ),
        workspace,
        runner=runner,
    )

    assert observed["timeout_seconds"] == 300
    assert payload["timeout_limit_seconds"] == 300
    assert payload["effective_timeout_seconds"] == 300
    assert payload["timeout_policy"] == "hard_ceiling"


def test_gitleaks_timeout_remains_unverified_and_nonblocking(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(secret, "_history_metadata", lambda _workspace: _history())
    monkeypatch.setattr(secret.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    def runner(command, *, cwd, limits):
        return WorkerCommandResult(
            args=tuple(command),
            returncode=124,
            stdout="",
            stderr="",
            timed_out=True,
        )

    payload = secret._run_secret_tool(
        ScannerToolSpec(
            name="gitleaks",
            command=("gitleaks",),
            category="secret",
            timeout_seconds=900,
            scans_git_history=True,
        ),
        workspace,
        runner=runner,
    )

    assert payload["status"] == "timeout"
    assert payload["verified_for_this_report"] is False
    assert payload["parser_status"] == "timeout"
    assert payload["pipeline_blocking_allowed"] is False
