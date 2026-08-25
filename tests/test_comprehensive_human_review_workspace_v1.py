from __future__ import annotations

from pathlib import Path


WORKSPACE = Path("apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx")
OPERATIONS_PAGE = Path("apps/web/app/operations/final-review/page.tsx")
LEGACY_PAGE = Path("apps/web/app/final-review/page.tsx")


def test_visible_final_review_is_comprehensive_only_and_not_legacy_service_selectable() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    page = OPERATIONS_PAGE.read_text(encoding="utf-8")

    assert 'import ComprehensiveFinalReviewWorkspace from "./ComprehensiveFinalReviewWorkspace"' in page
    assert "<ComprehensiveFinalReviewWorkspace />" in page
    assert 'data-review-contract="accepted-edition-v2"' in workspace
    assert 'comprehensive: "Comprehensive"' in workspace
    assert 'value={copy.comprehensive} readOnly' in workspace
    assert "Strategic" not in workspace
    assert 'value="express"' not in workspace
    assert "express_run_" not in workspace
    assert "/operations/final-review/${service}" not in workspace


def test_final_review_uses_protected_exact_run_comprehensive_endpoints() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert '"X-NICO-Admin-Token": adminToken.trim()' in workspace
    assert 'type="password"' in workspace
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}" in workspace
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/review" in workspace
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId.trim())}/approved-delivery-package" in workspace
    assert 'review_authorized: true' in workspace
    assert 'authorization_confirmed: true' in workspace
    assert 'reviewer: reviewer.trim()' in workspace
    assert 'reviewer_role: reviewerRole.trim()' in workspace
    assert 'decision_reason: reason' in workspace


def test_final_review_preserves_exact_run_when_opening_exception_review_queue() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "/operations/reviewer-queue?run_id=${encodeURIComponent(runId.trim())}" in workspace
    assert "&lang=${encodeURIComponent(locale)}" in workspace


def test_legacy_final_review_cannot_reenter_retired_express_workflow() -> None:
    legacy = LEGACY_PAGE.read_text(encoding="utf-8")

    assert 'window.location.replace(`/operations/final-review${query}`)' in legacy
    assert 'window.location.search || ""' in legacy
    assert "/reports/" not in legacy
    assert "Express assessment" not in legacy
    assert "transitionReview" not in legacy
