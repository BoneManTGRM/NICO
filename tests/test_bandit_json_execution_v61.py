from __future__ import annotations

import json
from pathlib import Path

from nico.bandit_json_execution_v61 import (
    _EXCLUDES,
    install_bandit_json_execution_v61,
    run_bandit_json,
)
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    return workspace


def test_bandit_json_retains_large_finding_without_csv_field_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/tools/bandit" if name == "bandit" else None,
    )
    large_message = "x" * 300_000

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        command = tuple(str(part) for part in args)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "errors": [],
                    "generated_at": "2026-08-02T00:00:00Z",
                    "metrics": {},
                    "results": [
                        {
                            "filename": "nico/example.py",
                            "line_number": 14,
                            "issue_severity": "MEDIUM",
                            "issue_confidence": "HIGH",
                            "issue_text": large_message,
                            "test_id": "B113",
                            "test_name": "request_without_timeout",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("Bandit completed\n", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=1,
            stdout="Bandit completed",
            stderr="",
            stdout_path=str(stdout_path),
            stdout_bytes=17,
            stderr_bytes=0,
        )

    result = run_bandit_json(
        ScannerToolSpec(
            "bandit",
            ("bandit",),
            "static",
            timeout_seconds=30,
            max_output_chars=100,
        ),
        workspace,
        runner,
    )

    assert result["status"] == "completed"
    assert result["output_capture_complete"] is True
    assert result["raw_artifact_capture_complete"] is True
    assert result["raw_artifact_format"] == "json"
    assert result["findings_count"] == 1
    assert result["findings"][0]["line_number"] == 14
    assert len(result["findings"][0]["issue_text"]) == len(large_message)
    assert result["execution_source"] == "canonical_bandit_json_v62"
    assert result["bandit_csv_parser_used"] is False
    assert result["failure_or_unavailable_reason"] == ""
    command = result["command_intent"]
    assert "-f json" in command
    assert "tests" in command
    assert "audit-results" in command


def test_bandit_json_zero_findings_is_verified_completion(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/tools/bandit" if name == "bandit" else None,
    )

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        command = tuple(str(part) for part in args)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"errors": [], "metrics": {}, "results": []}),
            encoding="utf-8",
        )
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("Bandit completed\n", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=0,
            stdout="Bandit completed",
            stderr="",
            stdout_path=str(stdout_path),
            stdout_bytes=17,
            stderr_bytes=0,
        )

    result = run_bandit_json(
        ScannerToolSpec("bandit", ("bandit",), "static", timeout_seconds=30),
        workspace,
        runner,
    )

    assert result["status"] == "completed"
    assert result["findings"] == []
    assert result["findings_count"] == 0
    assert result["verified_for_this_report"] is True
    assert result["raw_artifact_capture_complete"] is True


def test_bandit_json_invalid_artifact_remains_failed(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/tools/bandit" if name == "bandit" else None,
    )

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        command = tuple(str(part) for part in args)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("not json", encoding="utf-8")
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("Bandit failed\n", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=1,
            stdout="",
            stderr="",
            stdout_path=str(stdout_path),
        )

    result = run_bandit_json(
        ScannerToolSpec("bandit", ("bandit",), "static", timeout_seconds=30),
        workspace,
        runner,
    )

    assert result["status"] == "failed"
    assert result["verified_for_this_report"] is False
    assert result["output_capture_complete"] is False
    assert "could not be parsed" in result["failure_or_unavailable_reason"]


def test_bandit_json_installer_rebinds_named_and_authoritative_dispatch() -> None:
    from nico import scanner_evidence_pipeline_v1 as pipeline

    result = install_bandit_json_execution_v61()

    assert result["status"] == "installed"
    assert result["bound"] is True
    assert result["named_bandit_delegate_bound"] is True
    assert result["problem_dispatch_bound"] is True
    assert getattr(
        pipeline._run_problem_tool,
        "_nico_bandit_json_problem_dispatch_v62",
        False,
    ) is True
    assert pipeline._run_bandit is run_bandit_json
    assert "tests" in _EXCLUDES
    assert "audit-results" in _EXCLUDES


def test_authoritative_problem_dispatch_bypasses_restored_csv_delegate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from nico import scanner_evidence_pipeline_v1 as pipeline

    install_bandit_json_execution_v61()
    workspace = _workspace(tmp_path)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/tools/bandit" if name == "bandit" else None,
    )

    def stale_csv(*args, **kwargs):
        raise AssertionError("legacy Bandit CSV delegate must not execute")

    monkeypatch.setattr(pipeline, "_run_bandit", stale_csv)

    def runner(args, *, cwd, limits, stdout_path, extra_env):
        del cwd, limits, extra_env
        command = tuple(str(part) for part in args)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"errors": [], "metrics": {}, "results": []}),
            encoding="utf-8",
        )
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text("Bandit completed\n", encoding="utf-8")
        return WorkerCommandResult(args=command, returncode=0, stdout="", stderr="")

    result = pipeline._run_problem_tool(
        ScannerToolSpec("bandit", ("bandit",), "static", timeout_seconds=30),
        workspace,
        runner,
        None,
    )

    assert result["status"] == "completed"
    assert result["execution_source"] == "canonical_bandit_json_v62"
    assert result["raw_artifact_format"] == "json"
