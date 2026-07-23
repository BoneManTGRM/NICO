from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "scripts" / "two_service_live_acceptance_v3.py"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
CLEANUP_WORKFLOW = ROOT / ".github" / "workflows" / "branch-cleanup.yml"


def test_live_acceptance_reads_exact_values_behind_compact_identifiers() -> None:
    acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "<code title={fullValue || fallback}>" in workspace
    assert "compactIdentifier(fullValue)" in workspace
    assert "querySelector('code')?.getAttribute('title')" in acceptance
    assert "querySelector('button[aria-label]')?.getAttribute('aria-label')" in acceptance
    assert "run_id: find('Run ID')" in acceptance
    assert "commit_sha: find('Immutable commit')" in acceptance
    assert "acceptance.ui_state = _safe_ui_state" in acceptance


def test_branch_cleanup_workflow_quotes_confirmation_description() -> None:
    source = CLEANUP_WORKFLOW.read_text(encoding="utf-8")

    assert 'description: "Execute only: DELETE REVIEWED MERGED BRANCHES"' in source
    assert "description: Execute only: DELETE REVIEWED MERGED BRANCHES" not in source
    assert "workflow_dispatch:" in source
    assert "persist-credentials: false" in source
