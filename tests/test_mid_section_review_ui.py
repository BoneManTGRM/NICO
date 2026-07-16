from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "web" / "app" / "assessment" / "MidSectionReview.tsx"
SECTION_PORTAL = ROOT / "apps" / "web" / "app" / "MidSectionReviewPortal.tsx"
SCORE_PORTAL = ROOT / "apps" / "web" / "app" / "MidScoreIntelligencePortal.tsx"
LAYOUT = ROOT / "apps" / "web"" / "app" / "layout.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "assessment.module.css"


def test_mid_review_workbench_replaces_oversized_section_cards_with_decision_controls() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "MID REVIEW WORKBENCH" in source
    assert "Review the result by exception" in source
    assert "Scored technical controls" in source
    assert "Human-context modules" in source
    assert "excluded from technical score" in source
    assert "Needs attention" in source
    assert "Verified strength" in source
    assert "Unscored context" in source
    assert "Open attention areas" in source
    assert "Collapse all" in source


def test_mid_review_workbench_preserves_all_review_evidence_categories() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "Evidence reviewed" in source
    assert "Findings" in source
    assert "Limitations and gaps" in source
    assert "Scope and confidence" in source
    assert "Next review action" in source
    assert "direct_repository_proof" in source
    assert "missing_evidence_sources" in source
    assert "failed_evidence_tools" in source
    assert "scope_disclosures" in source


def test_mid_review_workbench_classifies_unscored_context_before_attention() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    unscored_position = source.index("if (isUnscored(section)) return \"neutral\"")
    score_position = source.index("if (score != null && score < 60) return \"critical\"")
    assert unscored_position < score_position
    assert 'filter === "unscored"' in source
    assert "rows.filter(isUnscored).length" in source
    assert 'TECHNICAL_IDS.has(String(section.id || ""))' in source


def test_mid_review_portal_reuses_single_shared_status_transport() -> None:
    score_portal = SCORE_PORTAL.read_text(encoding="utf-8")
    section_portal = SECTION_PORTAL.read_text(encoding="utf-8")

    assert 'const MID_PAYLOAD_EVENT = "nico:mid-status-payload"' in score_portal
    assert "publishMidPayload(parsed)" in score_portal
    assert 'const MID_PAYLOAD_EVENT = "nico:mid-status-payload"' in section_portal
    assert "window.addEventListener(MID_PAYLOAD_EVENT, onPayload)" in section_portal
    assert "window.fetch =" not in section_portal
    assert "MID_RESPONSE_PATH" not in section_portal


def test_mid_review_portal_hides_only_mid_grid_and_restores_fail_safe() -> None:
    portal = SECTION_PORTAL.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'querySelector<HTMLElement>(".results-grid")' in portal
    assert "originalGrid.hidden = true" in portal
    assert "restoreOriginalGrids()" in portal
    assert "grid.hidden = false" in portal
    assert 'import MidSectionReviewPortal from "./MidSectionReviewPortal"' in layout
    assert "<MidSectionReviewPortal />" in layout


def test_mid_review_workbench_has_mobile_and_accessible_presentation_contract() -> None:
    component = COMPONENT.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")

    assert "aria-expanded={expanded}" in component
    assert 'role="group"' in component
    assert "aria-pressed={filter === value}" in component
    assert 'aria-label="Mid assessment section review"' in component
    for class_name in (
        ".sectionReview",
        ".reviewMetrics",
        ".priorityStrip",
        ".reviewToolbar",
        ".reviewGroup",
        ".reviewCard",
        ".reviewToggle",
        ".reviewDetailGrid",
        ".reviewList",
    ):
        assert class_name in css
    assert "@media (max-width: 760px)" in css
    assert "@media (max-width: 520px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
