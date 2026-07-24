from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_assessment_exposes_one_canonical_strategic_workflow() -> None:
    source = _read("apps/web/app/UnifiedAssessmentPublicGuard.tsx")
    layout = _read("apps/web/app/layout.tsx")

    assert 'import UnifiedAssessmentPublicGuard from "./UnifiedAssessmentPublicGuard";' in layout
    assert "<UnifiedAssessmentPublicGuard />" in layout
    assert 'url.searchParams.set("tier", "comprehensive")' in source
    assert 'main.dataset.assessmentServiceCount = "1"' in source
    assert 'main.dataset.canonicalAssessment = "strategic"' in source
    assert "One assessment. One evidence ledger. One decision-grade report." in source
    assert "everything useful from Express, Mid, and Comprehensive" in source
    assert "Run NICO Assessment" in source
    assert 'grid.hidden = true' in source
    assert "comprehensive.click()" in source


def test_operator_workspaces_are_not_public_assessment_navigation() -> None:
    source = _read("apps/web/app/UnifiedAssessmentPublicGuard.tsx")

    assert "hideOperatorNavigation" in source
    assert 'if (!isAssessmentPath(pathname)) return;' in source
    assert 'group.hidden = true' in source
    assert "operator workspaces" in source
    assert "espacios de trabajo del operador" in source


def test_one_system_keeps_human_review_and_read_only_contracts() -> None:
    layout = _read("apps/web/app/layout.tsx")

    assert "continues through required human review" in layout
    assert "never approves findings" in layout
    assert "Operator-only deployment controls" in layout
    assert 'href="/assessment?tier=comprehensive#assessment"' in layout
