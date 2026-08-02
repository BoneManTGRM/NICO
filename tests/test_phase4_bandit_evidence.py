from __future__ import annotations

import json
from pathlib import Path

from nico.scanner_evidence_pipeline_v1 import _run_bandit
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _bandit_spec():
    return next(spec for spec in TOOL_SPECS if spec.name == "bandit")


def _runner_with_json(findings: list[dict[str, object]]):
    def runner(command, **kwargs):
        command = tuple(str(part) for part in command)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "errors": [],
                    "generated_at": "2026-08-02T00:00:00Z",
                    "metrics": {},
                    "results": findings,
                }
            ),
            encoding="utf-8",
        )
        stdout_path = kwargs.get("stdout_path")
        if stdout_path:
            Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_path).write_text("Bandit completed\n", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=1 if findings else 0,
            stdout="Bandit completed",
            stderr="",
            stdout_path=str(stdout_path) if stdout_path else None,
            stdout_bytes=17,
            stderr_bytes=0,
        )

    return runner


def test_bandit_retains_complete_parseable_json(monkeypatch, tmp_path: Path) -> None:
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/usr/bin/bandit" if name == "bandit" else None,
    )

    finding = {
        "filename": "nico/example.py",
        "test_name": "request_without_timeout",
        "test_id": "B113",
        "issue_severity": "MEDIUM",
        "issue_confidence": "LOW",
        "issue_text": "Requests call without timeout",
        "line_number": 14,
        "line_range": [14],
        "more_info": "https://bandit.readthedocs.io",
    }
    payload = _run_bandit(_bandit_spec(), workspace, _runner_with_json([finding]))

    assert payload["status"] == "completed"
    assert payload["output_capture_complete"] is True
    assert payload["raw_artifact_capture_complete"] is True
    assert payload["raw_artifact_format"] == "json"
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["line_number"] == 14
    assert payload["execution_source"] == "canonical_bandit_json_v62"
    assert payload["bandit_csv_parser_used"] is False
    assert payload["compact_complete_result"] is True
    assert payload["failure_or_unavailable_reason"] == ""


def test_bandit_zero_findings_is_complete_not_unavailable(monkeypatch, tmp_path: Path) -> None:
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "nico.bandit_json_execution_v61.shutil.which",
        lambda name: "/usr/bin/bandit" if name == "bandit" else None,
    )

    payload = _run_bandit(_bandit_spec(), workspace, _runner_with_json([]))

    assert payload["status"] == "completed"
    assert payload["findings"] == []
    assert payload["findings_count"] == 0
    assert payload["output_capture_complete"] is True
    assert payload["raw_artifact_capture_complete"] is True
    assert payload["raw_artifact_format"] == "json"
