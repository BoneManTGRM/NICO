from __future__ import annotations

import json
import sys
from pathlib import Path

from nico.hosted_evidence_execution_patch import _enrich_tool_payload
from nico.scanner_complete_output_compat_v3 import install_scanner_complete_output_compat_v3
from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact
from nico.worker_execution import WorkerCommandResult, WorkerLimits, run_command

install_scanner_complete_output_compat_v3()
from nico.scanner_tool_runners import parse_tool_findings

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = ROOT / "nico" / "scanner_tool_runners.py"
COMPAT = ROOT / "nico" / "scanner_complete_output_compat_v3.py"


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

    parsed = parse_tool_findings("bandit", result)

    assert isinstance(parsed, list)
    assert len(parsed) == 250
    assert parsed[-1]["filename"] == "nico/module_249.py"


def test_semgrep_nested_severity_is_promoted_before_scoring(tmp_path: Path) -> None:
    destination = tmp_path / "semgrep.stdout"
    destination.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "check_id": "javascript.lang.security.audit.example",
                        "path": "apps/web/example.ts",
                        "start": {"line": 4, "col": 3},
                        "end": {"line": 4, "col": 12},
                        "extra": {"severity": "WARNING", "message": "Review candidate"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = WorkerCommandResult(
        args=("semgrep",),
        returncode=1,
        stdout="",
        stderr="",
        output_truncated=False,
        stdout_path=str(destination),
        stdout_bytes=destination.stat().st_size,
    )

    parsed = parse_tool_findings("semgrep", result)
    normalized = normalize_scanner_worker_artifact(
        {"tools": {"semgrep": {"status": "completed", "findings": parsed}}}
    )

    assert parsed[0]["severity"] == "warning"
    assert parsed[0]["file_path"] == "apps/web/example.ts"
    assert normalized["tools"]["semgrep"]["severity_counts"] == {"warning": 1}


def test_failed_or_unavailable_tool_is_observed_but_not_verified() -> None:
    failed = _enrich_tool_payload({"status": "failed", "findings": []}, "bandit")
    unavailable = _enrich_tool_payload({"status": "unavailable", "findings": []}, "eslint")

    assert failed["execution_observed_for_this_report"] is True
    assert failed["verified_for_this_report"] is False
    assert unavailable["execution_observed_for_this_report"] is True
    assert unavailable["verified_for_this_report"] is False


def test_project_analyzers_use_exact_lockfile_and_local_binaries() -> None:
    source = RUNNERS.read_text(encoding="utf-8")
    compat = COMPAT.read_text(encoding="utf-8")
    assert '"ci",' in source
    assert '"--ignore-scripts"' in source
    assert 'web_dir / "node_modules" / ".bin" / bin_name' in source
    assert 'ScannerToolSpec("eslint", ("eslint"' in source
    assert 'ScannerToolSpec("typescript", ("tsc"' in source
    assert '"npx"' not in source
    assert "output_capture_complete" in source
    assert "returncode_valid" in source
    assert "legacy_findings_list_contract" in compat
    assert '"artifact_schema": "nico.scanner_worker.v2"' in compat
    assert "gitleaks_full_history_restored" in compat
    assert "bandit_generated_paths_excluded" in compat
    assert "eslint_without_configuration_inapplicable" in compat
