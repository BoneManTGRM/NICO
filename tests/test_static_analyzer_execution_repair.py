from __future__ import annotations

import json
import sys
from pathlib import Path

from nico.scanner_tool_runners import parse_tool_findings
from nico.worker_execution import WorkerCommandResult, WorkerLimits, run_command


ROOT = Path(__file__).resolve().parents[1]
RUNNERS = ROOT / "nico" / "scanner_tool_runners.py"


def test_worker_keeps_complete_stdout_file_while_bounding_preview(tmp_path: Path) -> None:
    destination = tmp_path / "scanner-output" / "bandit.stdout"
    result = run_command(
        (sys.executable, "-c", "print('x' * 5000)"),
        cwd=tmp_path,
        limits=WorkerLimits(timeout_seconds=30, max_output_chars=200),
        stdout_path=destination,
    )

    assert result.returncode == 0
    assert result.stdout_path == str(destination.resolve())
    assert result.output_truncated is True
    assert result.stdout_bytes > 5000
    assert len(result.stdout) <= 200
    assert len(destination.read_text(encoding="utf-8")) > 5000


def test_bandit_parser_reads_complete_json_not_truncated_preview(tmp_path: Path) -> None:
    destination = tmp_path / "bandit.stdout"
    findings = [
        {
            "filename": f"nico/module_{index}.py",
            "line_number": index + 1,
            "issue_severity": "MEDIUM",
            "issue_confidence": "HIGH",
            "test_id": "B101",
        }
        for index in range(250)
    ]
    destination.write_text(json.dumps({"results": findings}), encoding="utf-8")
    result = WorkerCommandResult(
        args=("bandit",),
        returncode=1,
        stdout="{\"results\": [ ...[truncated by NICO worker]",
        stderr="",
        output_truncated=True,
        stdout_path=str(destination),
        stdout_bytes=destination.stat().st_size,
    )

    parsed, complete, reason = parse_tool_findings("bandit", result)

    assert complete is True
    assert reason == ""
    assert len(parsed) == 250
    assert parsed[-1]["filename"] == "nico/module_249.py"


def test_project_analyzers_use_exact_lockfile_and_local_binaries() -> None:
    source = RUNNERS.read_text(encoding="utf-8")

    assert '"ci",' in source
    assert '"--ignore-scripts"' in source
    assert 'web_dir / "node_modules" / ".bin" / bin_name' in source
    assert 'ScannerToolSpec("eslint", ("eslint"' in source
    assert 'ScannerToolSpec("typescript", ("tsc"' in source
    assert '"npx"' not in source
    assert "output_capture_complete" in source
    assert "returncode_valid" in source
