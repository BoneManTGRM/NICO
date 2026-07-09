from pathlib import Path

from nico import scanner_tool_runners
from nico.hosted_bandit_triage_workflow_patch import (
    apply_bandit_triage_to_tool_payload,
    bandit_finding_id,
    build_bandit_triage_summary,
    install_bandit_triage_workflow_patch,
    load_bandit_triage_records,
)
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def bandit_finding(**overrides):
    finding = {
        "filename": "nico/example.py",
        "line_number": 12,
        "test_id": "B602",
        "test_name": "subprocess_popen_with_shell_equals_true",
        "issue_severity": "HIGH",
        "issue_confidence": "HIGH",
        "issue_text": "subprocess call with shell=True identified",
    }
    finding.update(overrides)
    return finding


def test_bandit_finding_id_is_stable():
    finding = bandit_finding()

    first = bandit_finding_id(finding)
    second = bandit_finding_id(dict(finding))

    assert first == second
    assert first.startswith("bandit_")


def test_high_risk_finding_without_triage_blocks_score_lift():
    summary = build_bandit_triage_summary([bandit_finding()], [])

    assert summary["total_findings"] == 1
    assert summary["needs_review_count"] == 1
    assert summary["unresolved_high_confidence_count"] == 1
    assert summary["score_lift_allowed"] is False
    assert summary["human_review_required"] is True


def test_accepted_risk_requires_signed_fields():
    finding = bandit_finding()
    finding_id = bandit_finding_id(finding)

    summary = build_bandit_triage_summary(
        [finding],
        [{"finding_id": finding_id, "status": "accepted-risk", "reason": "Controlled internal tool path."}],
    )

    assert summary["invalid_triage_records"]
    assert summary["score_lift_allowed"] is False
    assert summary["human_review_required"] is True


def test_signed_accepted_risk_allows_score_lift_for_high_risk_finding():
    finding = bandit_finding()
    finding_id = bandit_finding_id(finding)

    summary = build_bandit_triage_summary(
        [finding],
        [
            {
                "finding_id": finding_id,
                "status": "accepted-risk",
                "reason": "Subprocess input is fixed and not user-controlled in this authorized scanner path.",
                "approved_by": "security-reviewer",
                "approved_at": "2026-07-09T20:30:00Z",
            }
        ],
    )

    assert summary["approved_count"] == 1
    assert summary["unresolved_high_confidence_count"] == 0
    assert summary["score_lift_allowed"] is True
    assert summary["human_review_required"] is False


def test_load_bandit_triage_records_from_repo_file(tmp_path):
    ws = workspace(tmp_path)
    triage_dir = ws.repo_dir / ".nico"
    triage_dir.mkdir()
    (triage_dir / "bandit-triage.json").write_text(
        '{"records":[{"finding_id":"bandit_abc","status":"needs-review","reason":"needs owner review"}]}',
        encoding="utf-8",
    )

    records, notes = load_bandit_triage_records(ws.repo_dir)

    assert records[0]["finding_id"] == "bandit_abc"
    assert "Loaded Bandit triage file" in notes[0]


def test_apply_bandit_triage_to_tool_payload_marks_human_review(tmp_path):
    ws = workspace(tmp_path)
    tool_payload = {"tool": "bandit", "status": "completed", "findings": [bandit_finding()], "findings_count": 1}

    enriched = apply_bandit_triage_to_tool_payload(tool_payload, ws.repo_dir)

    assert enriched["bandit_triage"]["total_findings"] == 1
    assert enriched["bandit_triage"]["score_lift_allowed"] is False
    assert enriched["human_review_required"] is True


def test_patched_bandit_runner_attaches_triage(monkeypatch, tmp_path):
    ws = workspace(tmp_path)
    install_bandit_triage_workflow_patch()

    def fake_runner(command, *, cwd, limits):
        return WorkerCommandResult(args=tuple(command), returncode=1, stdout='{"results":[{"filename":"nico/example.py","line_number":12,"test_id":"B602","issue_severity":"HIGH","issue_confidence":"HIGH","issue_text":"subprocess"}]}', stderr="")

    monkeypatch.setattr("nico.scanner_tool_runners.shutil.which", lambda name: "/usr/bin/bandit" if name == "bandit" else None)
    spec = ScannerToolSpec("bandit", ("bandit", "-r", ".", "-f", "json"), "static", timeout_seconds=120)
    result = scanner_tool_runners.run_scanner_tool(spec, ws, runner=fake_runner)

    assert result["status"] == "completed"
    assert result["bandit_triage"]["artifact_schema"] == "nico.bandit_triage.v1"
    assert result["bandit_triage"]["score_lift_allowed"] is False
