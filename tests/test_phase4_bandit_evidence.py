from __future__ import annotations

from pathlib import Path

from nico.scanner_evidence_pipeline_v1 import _run_bandit
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _bandit_spec():
    return next(spec for spec in TOOL_SPECS if spec.name == "bandit")


def _runner_with_csv(rows: list[str]):
    def runner(command, **kwargs):
        command = tuple(str(part) for part in command)
        report_path = Path(command[command.index("-o") + 1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        header = "filename,test_name,test_id,issue_severity,issue_confidence,issue_text,line_number,line_range,more_info\n"
        report_path.write_text(header + "".join(rows), encoding="utf-8")
        stdout_path = kwargs.get("stdout_path")
        if stdout_path:
            Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_path).write_text("Bandit completed\n", encoding="utf-8")
        return WorkerCommandResult(
            args=command,
            returncode=1 if rows else 0,
            stdout="Bandit completed",
            stderr="",
            stdout_path=str(stdout_path) if stdout_path else None,
            stdout_bytes=17,
            stderr_bytes=0,
        )

    return runner


def test_bandit_retains_complete_parseable_csv(monkeypatch, tmp_path: Path) -> None:
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    monkeypatch.setattr("nico.scanner_evidence_pipeline_v1.shutil.which", lambda name: "/usr/bin/bandit" if name == "bandit" else None)

    row = "nico/example.py,request_without_timeout,B113,MEDIUM,LOW,Requests call without timeout,14,[14],https://bandit.readthedocs.io\n"
    payload = _run_bandit(_bandit_spec(), workspace, _runner_with_csv([row]))

    assert payload["status"] == "completed"
    assert payload["output_capture_complete"] is True
    assert payload["raw_artifact_capture_complete"] is True
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["line_number"] == 14
    assert payload["execution_source"] == "canonical_bandit_csv"
    assert payload["compact_complete_result"] is True
    assert payload["failure_or_unavailable_reason"] == ""


def test_bandit_zero_findings_is_complete_not_unavailable(monkeypatch, tmp_path: Path) -> None:
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    monkeypatch.setattr("nico.scanner_evidence_pipeline_v1.shutil.which", lambda name: "/usr/bin/bandit" if name == "bandit" else None)

    payload = _run_bandit(_bandit_spec(), workspace, _runner_with_csv([]))

    assert payload["status"] == "completed"
    assert payload["findings"] == []
    assert payload["findings_count"] == 0
    assert payload["output_capture_complete"] is True
    assert payload["raw_artifact_capture_complete"] is True
