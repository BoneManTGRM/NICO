from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/exact-comprehensive-verifier-finalizer.yml")
SOURCE = Path(".github/workflows/verify-comprehensive-recovery-9984.yml")


def test_finalizer_observes_completion_of_exact_verifier_on_main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_run:" in text
    assert "Verify Comprehensive Recovery 9984" in text
    assert "types:\n      - completed" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
    assert "RELEASE_SHA: ${{ github.event.workflow_run.head_sha }}" in text
    assert "SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}" in text
    assert "cancel-in-progress: false" in text


def test_finalizer_only_repairs_missing_or_pending_terminal_status() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'if observed in {"success", "failure", "error"}:' in text
    assert 'state = "failure"' in text
    assert "completed without publishing an exact-run terminal status" in text
    assert "ended before terminal proof" in text
    assert '"context": status_context' in text
    assert '"state": state' in text
    assert "fail-closed orchestration evidence" in text


def test_finalizer_never_manufactures_success_or_mutates_assessment_state() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'state = "success"' not in text
    assert "/continue" not in text
    assert "/assessment/" not in text
    assert "client_delivery_allowed" not in text
    assert "human_review_required" not in text
    assert "/approve" not in text


def test_original_verifier_can_outlive_its_explicit_status_path_without_finalizer() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "timeout-minutes: 120" in source
    assert "deadline = time.time() + 12 * 60" in source
    assert "for attempt in range(1, 31):" in source
    assert 'post_status("success"' in source
    assert 'post_status("failure"' in source
    # This proves why a workflow_run finalizer is required: the original job can hit
    # the outer watchdog before Python reaches either explicit post_status call.
    assert "if: failure()" not in source
