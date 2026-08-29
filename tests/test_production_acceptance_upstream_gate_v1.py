from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIFIED_WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"
BINDER_WORKFLOW = ROOT / ".github" / "workflows" / "phase1-completion-bound-report.yml"


def test_failed_spanish_source_cannot_start_the_completion_report_binder() -> None:
    unified = UNIFIED_WORKFLOW.read_text(encoding="utf-8")
    binder = BINDER_WORKFLOW.read_text(encoding="utf-8")

    contract = unified.split("  contract:\n", 1)[1].split("\n  live-production:\n", 1)[0]
    source_guard = contract.split(
        "      - name: Require successful main Spanish source proof\n", 1
    )[1].split("\n      - name: Check out exact commit\n", 1)[0]

    assert "if: github.event_name == 'workflow_run'" in source_guard
    assert "SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}" in source_guard
    assert "SOURCE_HEAD_BRANCH: ${{ github.event.workflow_run.head_branch }}" in source_guard
    assert 'test "${SOURCE_CONCLUSION}" = "success"' in source_guard
    assert 'test "${SOURCE_HEAD_BRANCH}" = "main"' in source_guard
    assert "continue-on-error" not in source_guard

    live = unified.split("\n  live-production:\n", 1)[1]
    assert "github.event.workflow_run.conclusion == 'success'" in live
    assert "github.event.workflow_run.head_branch == 'main'" in live

    assert 'workflows: ["Unified Production Acceptance"]' in binder
    assert "github.event.workflow_run.conclusion == 'success'" in binder
    assert "github.event.workflow_run.head_branch == 'main'" in binder
