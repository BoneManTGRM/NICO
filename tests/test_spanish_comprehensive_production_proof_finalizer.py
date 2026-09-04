from __future__ import annotations

from pathlib import Path


FINALIZER = Path(".github/workflows/spanish-comprehensive-production-proof-finalizer.yml")
SOURCE = Path(".github/workflows/spanish-comprehensive-production-proof.yml")


def test_spanish_proof_finalizer_tracks_completed_source_workflow_on_main() -> None:
    text = FINALIZER.read_text(encoding="utf-8")

    assert "name: Spanish Comprehensive Production Proof Finalizer" in text
    assert "workflow_run:" in text
    assert "- Spanish Comprehensive Production Proof" in text
    assert "- completed" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
    assert "RELEASE_SHA: ${{ github.event.workflow_run.head_sha }}" in text
    assert "SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}" in text
    assert "SOURCE_RUN_ID: ${{ github.event.workflow_run.id }}" in text
    assert "SOURCE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}" in text
    assert "statuses: write" in text


def test_spanish_proof_finalizer_preserves_terminal_truth_and_only_fails_closed() -> None:
    text = FINALIZER.read_text(encoding="utf-8")

    assert 'if observed in {"success", "failure", "error"}:' in text
    assert 'description.startswith(source_marker + " ")' in text
    assert 'observed = str(latest.get("state") or "missing")' in text
    assert '"state": "failure"' in text
    assert '"state": "success"' not in text
    assert "completed without terminal commit status" in text
    assert "ended before terminal publication" in text


def test_spanish_proof_finalizer_reads_exact_sha_status_before_writing() -> None:
    text = FINALIZER.read_text(encoding="utf-8")

    get_status = text.index('f"https://api.github.com/repos/{repository}/commits/{sha}/status"')
    observed = text.index('observed = str(latest.get("state") or "missing")')
    post_status = text.index('f"https://api.github.com/repos/{repository}/statuses/{sha}"')
    assert get_status < observed < post_status


def test_spanish_proof_finalizer_cannot_create_or_approve_assessments() -> None:
    text = FINALIZER.read_text(encoding="utf-8")

    assert "/assessment/comprehensive-intake" not in text
    assert "/continue" not in text
    assert "/approve" not in text
    assert "client_delivery_allowed" not in text
    assert "human_review_required" not in text


def test_source_workflow_still_publishes_pending_before_live_proof() -> None:
    text = SOURCE.read_text(encoding="utf-8")

    pending = text.index("Publish pending Spanish proof status")
    live_proof = text.index("Run fresh authenticated Spanish Comprehensive final-report proof")
    assert pending < live_proof
    assert '"state": "pending"' in text
    assert "NICO Spanish Comprehensive Production Proof" in text
