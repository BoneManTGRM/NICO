from __future__ import annotations

from pathlib import Path


def test_frontend_splits_score_badges_from_assurance() -> None:
    guard = Path("apps/web/app/AssessmentScoreAssuranceGuard.tsx").read_text(encoding="utf-8")
    layout = Path("apps/web/app/layout.tsx").read_text(encoding="utf-8")
    styles = Path("apps/web/styles/score-assurance.css").read_text(encoding="utf-8")

    assert "EXCEPTIONAL" in guard
    assert "STRONG" in guard
    assert "MODERATE" in guard
    assert "WEAK" in guard
    assert "REVIEW LIMITED" in guard
    assert "VERIFIED" in guard
    assert "BLOCKED" in guard
    assert "score >= 90" in guard
    assert "score >= 80" in guard
    assert "score >= 70" in guard
    assert "AssessmentScoreAssuranceGuard" in layout
    assert 'import "../styles/score-assurance.css"' in layout
    assert "data-nico-score-band" in styles
    assert ".assurance-badge" in styles


def test_guard_preserves_canonical_status_as_metadata() -> None:
    guard = Path("apps/web/app/AssessmentScoreAssuranceGuard.tsx").read_text(encoding="utf-8")
    assert "nicoCanonicalStatus" in guard
    assert "Evidence assurance" in guard
    assert "Technical score" in guard


def test_guard_rechecks_the_whole_document_after_react_updates() -> None:
    guard = Path("apps/web/app/AssessmentScoreAssuranceGuard.tsx").read_text(encoding="utf-8")

    assert "function processDocument" in guard
    assert 'document.querySelectorAll<HTMLElement>(".status")' in guard
    assert "new MutationObserver(() => schedule())" in guard
    assert 'window.addEventListener("pageshow", schedule)' in guard
    assert "for (const mutation of mutations)" not in guard
