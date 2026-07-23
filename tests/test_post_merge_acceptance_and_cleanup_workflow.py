from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "scripts" / "two_service_live_acceptance_v3.py"
CLEANUP_WORKFLOW = ROOT / ".github" / "workflows" / "branch-cleanup.yml"


def test_live_acceptance_reads_full_identifier_values_not_compact_display_text() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")

    assert "const findIdentifier = label =>" in source
    assert "code?.getAttribute('title')?.trim()" in source
    assert "run_id: findIdentifier('Run ID')" in source
    assert "commit_sha: findIdentifier('Immutable commit')" in source
    assert "run_id: findText('Run ID')" not in source
    assert "commit_sha: findText('Immutable commit')" not in source


def test_branch_cleanup_workflow_quotes_confirmation_description() -> None:
    source = CLEANUP_WORKFLOW.read_text(encoding="utf-8")

    assert 'description: "Execute only: DELETE REVIEWED MERGED BRANCHES"' in source
    assert "description: Execute only: DELETE REVIEWED MERGED BRANCHES" not in source
    assert "workflow_dispatch:" in source
    assert "contents: write" in source
    assert 'confirmation != "DELETE REVIEWED MERGED BRANCHES"' in source
