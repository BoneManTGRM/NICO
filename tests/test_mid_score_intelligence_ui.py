from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "web" / "app" / "assessment" / "MidScoreIntelligence.tsx"
PORTAL = ROOT / "apps" / "web" / "app" / "MidScoreIntelligencePortal.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "assessment.module.css"


def test_mid_score_intelligence_explains_contract_constraints_and_projection() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "What the score means and what constrains it" in source
    assert "Express is a faster baseline" in source
    assert "seven fixed technical weights" in source
    assert "Verified-fix scenario" in source
    assert "requires reassessment" in source
    assert "Show all weighted score contributions" in source
    assert "Gray, unscored business-context sections are excluded" in source
    assert "Client delivery remains blocked" in source


def test_mid_score_portal_captures_exact_mid_responses_and_mounts_near_score_cards() -> None:
    portal = PORTAL.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert "assessment\\/mid-run" in portal
    assert 'section[aria-live="polite"]' in portal
    assert 'querySelectorAll(".target-grid")' in portal
    assert 'insertAdjacentElement("afterend", mount)' in portal
    assert "createPortal" in portal
    assert "nico:assessment-tier-selected" in portal
    assert 'import MidScoreIntelligencePortal from "./MidScoreIntelligencePortal"' in layout
    assert "<MidScoreIntelligencePortal />" in layout


def test_mid_score_intelligence_has_mobile_readable_styles() -> None:
    css = STYLES.read_text(encoding="utf-8")

    for class_name in (
        ".scoreIntelligence",
        ".scoreIntelligenceHead",
        ".scoreMetrics",
        ".constraintGrid",
        ".weightTable",
        ".weightHeader",
    ):
        assert class_name in css
    assert "overflow-x: auto" in css
    assert "@media (max-width: 760px)" in css
    assert ".scoreMetrics," in css
    assert ".constraintGrid" in css
