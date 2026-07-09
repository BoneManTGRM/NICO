from pathlib import Path

from nico.hosted_evidence_execution_patch import build_bandit_triage, summarize_bandit_triage
from nico.scanner_tool_runners import ScannerToolSpec, run_scanner_tool, run_scanner_tools
from nico.worker_execution import WorkerWorkspace


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def test_bandit_triage_defaults_findings_to_blocking_until_approved():
    triage = build_bandit_triage(
        [
            {
                "test_id": "B608",
                "filename": "nico/example.py",
                "line_number": 42,
                "issue_severity": "MEDIUM",
                "issue_confidence": "HIGH",
                "issue_text": "Possible SQL injection vector.",
            }
        ]
    )
    summary = summarize_bandit_triage(triage)

    assert triage[0]["finding_id"] == "B608"
    assert triage[0]["triage_status"] == "blocker"
    assert triage[0]["approved_by"] is None
    assert summary["blocker_count"] == 1
    assert summary["static_lift_allowed"] is False


def test_missing_scanner_tool_returns_verified_current_run_unavailable(tmp_path):
    spec = ScannerToolSpec("missing-test-tool", ("definitely-not-installed-nico-tool", "--version"), "static")

    result = run_scanner_tool(spec, _workspace(tmp_path))

    assert result["tool"] == "missing-test-tool"
    assert result["status"] == "unavailable"
    assert result["current_run"] is True
    assert result["verified_for_this_report"] is True
    assert result["findings_count"] == 0
    assert "not installed" in result["reason"]


def test_scanner_artifact_includes_tool_records_for_current_run(tmp_path):
    spec = ScannerToolSpec("missing-test-tool", ("definitely-not-installed-nico-tool", "--version"), "static")

    artifact = run_scanner_tools(_workspace(tmp_path), specs=(spec,))

    assert artifact["tool_records"]
    record = artifact["tool_records"][0]
    assert record["tool"] == "missing-test-tool"
    assert record["status"] == "unavailable"
    assert record["current_run"] is True
    assert record["verified_for_this_report"] is True


def test_empty_bandit_triage_allows_static_lift_only_when_zero_findings():
    summary = summarize_bandit_triage([])

    assert summary["total_findings"] == 0
    assert summary["blocker_count"] == 0
    assert summary["static_lift_allowed"] is True
