from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "web" / "app" / "assessment" / "MidSectionReview.tsx"
SECTION_PORTAL = ROOT / "apps" / "web" / "app" / "MidSectionReviewPortal.tsx"
SCORE_PORTAL = ROOT / "apps" / "web" / "app" / "MidScoreIntelligencePortal.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "midReview.module.css"


def test_mid_review_is_one_client_facing_decision_surface() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "NICO MID ASSESSMENT" in source
    assert "Mid Assessment Review" in source
    assert "Review the result by exception, not by scrolling" not in source
    assert "Technical score" in source
    assert "Evidence readiness" in source
    assert "Draft report" in source
    assert "Human review" in source
    assert "Highest-value controls" in source
    assert "Additional evidence requested" in source


def test_mid_review_uses_one_bounded_canonical_score_and_artifact_truth() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "weightedTotal === 100" in source
    assert "rows.reduce((total, row) => total + row.score * row.weight / 100" in source
    assert "function bounded" in source
    assert "completeScorecard" in source
    assert "reportReady = pdfReady || markdownReady" in source
    assert 'reportStatusClaimsReady ? "Artifact unavailable"' in source
    assert 'reviewApproved ? "Approved" : reviewBlocked ? "Blocked" : "Required"' in source
    assert "Client delivery blocked" in source
    assert "verified-fix scenario" in source
    assert "score == null || !completeScorecard" in source


def test_mid_review_rejects_false_artifacts_and_handles_malformed_payload_values() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "function hasArtifact" in source
    assert '["base64", "data", "content", "bytes"]' in source
    assert "Object.keys(value).length > 0" not in source
    assert "function cleanText" in source
    assert "function displayText" in source
    assert "score?: unknown" in source
    assert "summary?: unknown" in source
    assert "evidence?: unknown" in source
    assert "Artifact unavailable" in source


def test_mid_review_preserves_evidence_findings_limitations_and_scope() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "Evidence" in source
    assert "Findings" in source
    assert "Limitations" in source
    assert "Scope" in source
    assert "direct_repository_proof" in source
    assert "missing_evidence_sources" in source
    assert "failed_evidence_tools" in source
    assert "scope_disclosures" in source
    assert "Bandit did not provide accepted exact-snapshot evidence" in source
    assert "Gitleaks did not provide accepted same-run history evidence" in source


def test_mid_review_portal_merges_partial_status_monotonically_and_is_tier_safe() -> None:
    score_portal = SCORE_PORTAL.read_text(encoding="utf-8")
    section_portal = SECTION_PORTAL.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'const MID_PAYLOAD_EVENT = "nico:mid-status-payload"' in score_portal
    assert "publishMidPayload(parsed)" in score_portal
    assert "createPortal" not in score_portal
    assert "return null" in score_portal
    assert "window.addEventListener(MID_PAYLOAD_EVENT, onPayload)" in section_portal
    assert "if (!midSelectedRef.current) return" in section_portal
    assert "mergePayloadRecord(previous, incoming)" in section_portal
    assert "isMeaningful(incomingValue)" in section_portal
    assert "incomingValue.length" in section_portal
    assert 'window.addEventListener("popstate", syncFromLocation)' in section_portal
    assert "hideLegacySurface(panel, mount)" in section_portal
    assert "restoreLegacySurface()" in section_portal
    assert "child.hidden = true" in section_portal
    assert "element.hidden = false" in section_portal
    assert "<MidSectionReview payload={payload} />" in section_portal
    assert 'import MidSectionReviewPortal from "./MidSectionReviewPortal"' in layout


def test_mid_review_retains_report_and_human_review_actions_with_failure_feedback() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "Download draft PDF" in source
    assert "Copy Markdown" in source
    assert "Open human review" in source
    assert "clickLegacyAction" in source
    assert "runLegacyAction" in source
    assert "actionNotice" in source
    assert 'role="status"' in source
    assert 'data-nico-mid-legacy-hidden="true"' in source


def test_mid_review_is_compact_mobile_safe_and_accessible() -> None:
    component = COMPONENT.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")

    assert 'aria-label="Mid assessment review"' in component
    assert "aria-expanded={expanded}" in component
    assert 'role="group"' in component
    assert "aria-pressed={filter === value}" in component
    for class_name in (
        ".unifiedReview",
        ".statusGrid",
        ".actionBar",
        ".priorityList",
        ".filterChips",
        ".controlRow",
        ".detailGrid",
        ".contextPanel",
    ):
        assert class_name in css
    assert "env(safe-area-inset-bottom)" in css
    assert "overflow-x: auto" in css
    assert "@media (max-width: 760px)" in css
    assert "@media (max-width: 520px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
