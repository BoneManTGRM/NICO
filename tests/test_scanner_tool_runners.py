from __future__ import annotations

from pathlib import Path

import pytest

from nico.scanner_tool_runners import (
    ScannerToolSpec,
    parse_tool_findings,
    redact_payload,
    redact_text,
    run_scanner_tool,
    run_scanner_tools,
    write_scanner_artifact,
)
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def test_redact_text_masks_common_secret_shapes():
    text = "token = ghp_1234567890abcdefghijklmnop and password = abcdefghijklmnop"

    redacted = redact_text(text)

    assert "ghp_1234567890abcdefghijklmnop" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_payload_recurses_through_dicts_and_lists():
    payload = {"nested": [{"api_key": "api_key = 1234567890abcdef"}]}

    redacted = redact_payload(payload)

    assert redacted["nested"][0]["api_key"] == "api_key = [REDACTED]"


def test_parse_bandit_findings():
    result = WorkerCommandResult(
        args=("bandit",),
        returncode=1,
        stdout='{"results": [{"issue_text": "x"}, {"issue_text": "y"}]}',
        stderr="",
    )

    assert len(parse_tool_findings("bandit", result)) == 2


def test_parse_trufflehog_json_lines():
    result = WorkerCommandResult(
        args=("trufflehog",),
        returncode=183,
        stdout='{"SourceMetadata": {}}\n{"DetectorName": "test"}\nnot-json',
        stderr="",
    )

    assert len(parse_tool_findings("trufflehog", result)) == 2


def test_run_scanner_tool_marks_missing_executable_unavailable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: None)
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()

    payload = run_scanner_tool(ScannerToolSpec("bandit", ("bandit", "-r", "."), "static"), workspace)

    assert payload["status"] == "unavailable"
    assert payload["findings"] == []


def test_run_scanner_tool_uses_safe_runner(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: f"/usr/bin/{name}")
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    calls = []

    def fake_runner(args, *, cwd, limits):
        calls.append((tuple(args), cwd, limits.timeout_seconds))
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout='{"results": []}', stderr="")

    payload = run_scanner_tool(
        ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static", timeout_seconds=7),
        workspace,
        runner=fake_runner,
    )

    assert payload["status"] == "completed"
    assert payload["findings"] == []
    assert calls == [(("bandit", "-r", ".", "-f", "json"), workspace.repo_dir, 7)]


def test_run_scanner_tools_requires_checked_out_repo(tmp_path: Path):
    with pytest.raises(ValueError):
        run_scanner_tools(WorkerWorkspace(root=tmp_path), specs=())


def test_run_scanner_tools_returns_normalized_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: f"/usr/bin/{name}")
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()

    def fake_runner(args, *, cwd, limits):
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout='{"results": []}', stderr="")

    payload = run_scanner_tools(
        workspace,
        specs=(ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static"),),
        runner=fake_runner,
    )

    assert payload["artifact_schema"] == "nico.scanner_worker.v1"
    assert payload["normalized"]["static_tools_completed"] == ["bandit"]
    assert "semgrep" in payload["normalized"]["missing_static_tools"]


def test_write_scanner_artifact_redacts_before_disk(tmp_path: Path):
    output = write_scanner_artifact(
        {"token": "token = 1234567890abcdef"},
        tmp_path / "out" / "artifact.json",
    )

    text = output.read_text(encoding="utf-8")
    assert "1234567890abcdef" not in text
    assert "[REDACTED]" in text
