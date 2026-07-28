from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "web" / "app" / "assessment" / "MidSectionReview.tsx"
SECTION_PORTAL = ROOT / "apps" / "web" / "app" / "MidSectionReviewPortal.tsx"
SCORE_PORTAL = ROOT / "apps" / "web" / "app" / "MidScoreIntelligencePortal.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "midReview.module.css"


def test_assessment_review_is_one_comprehensive_decision_surface() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "COMPREHENSIVE ASSESSMENT" in source
    assert "MID ASSESSMENT" not in source
    assert "Engineering decision review" in source
    assert "Technical score" in source
    assert "Evidence readiness" in source
    assert "Report package" in source
    assert "Human review" in source
    assert "What should change first" in source
    assert "Additional evidence and scope" in source


def test_assessment_review_uses_one_bounded_canonical_score_and_artifact_truth() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "rows.length === TECHNICAL_IDS.length" in source
    assert "rows.reduce((total, row) => total + row.weight, 0) === 100" in source
    assert "rows.reduce((total, row) => total + row.score * row.weight / 100" in source
    assert "function bounded" in source
    assert "completeScorecard" in source
    assert "function deriveArtifacts" in source
    assert 'claimsReady ? "Artifact unavailable"' in source
    assert 'reviewApproved ? "Approved" : reviewBlocked ? "Blocked" : "Required"' in source
    assert "Projected after verified remediation" in source
    assert "score == null || !completeScorecard" in source


def test_assessment_review_rejects_false_artifacts_and_handles_malformed_payload_values() -> None:
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


def test_assessment_review_preserves_evidence_findings_limitations_and_scope() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    for label in ("Evidence", "Findings", "Limitations", "Scope"):
        assert label in source
    assert "direct_repository_proof" in source
    assert "missing_evidence_sources" in source
    assert "failed_evidence_tools" in source
    assert "scope_disclosures" in source
    assert "Bandit did not provide accepted exact-snapshot evidence" in source
    assert "Gitleaks did not provide accepted evidence for this exact snapshot" in source


def test_legacy_transport_portals_remain_unmounted_and_monotonic() -> None:
    score_portal = SCORE_PORTAL.read_text(encoding="utf-8")
    section_portal = SECTION_PORTAL.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'const MID_PAYLOAD_EVENT = "nico:mid-status-payload"' in score_portal
    assert "publishMidPayload(parsed)" in score_portal
    assert "createPortal" not in score_portal
    assert "return null" in score_portal
    assert "window.addEventListener(MID_PAYLOAD_EVENT, onPayload)" in section_portal
    assert "mergePayloadRecord(previous, incoming)" in section_portal
    assert "DURABLE_ARRAY_KEYS" in section_portal
    assert "DURABLE_SCALAR_KEYS" in section_portal
    assert "MONOTONIC_TRUE_KEYS" in section_portal
    assert "MONOTONIC_STATUS_KEYS" in section_portal
    assert "statusRank(previousValue) > statusRank(incomingValue)" in section_portal
    assert "hideLegacySurface(panel, mount)" in section_portal
    assert "restoreLegacySurface()" in section_portal
    assert "MidSectionReviewPortal" not in layout
    assert "MidScoreIntelligencePortal" not in layout
    assert 'href="/assessment?tier=comprehensive#assessment"' in layout


def test_assessment_review_retains_report_and_human_review_actions_with_feedback() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "Request review" in source
    assert "Open report" in source
    assert "clickLegacyAction" in source
    assert "requestReview" in source
    assert "openReport" in source
    assert "actionNotice" in source
    assert 'role="status"' in source
    assert 'data-nico-mid-legacy-hidden="true"' in source


def test_assessment_review_is_mobile_safe_and_accessible() -> None:
    component = COMPONENT.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")

    assert 'aria-label="Comprehensive assessment review"' in component
    assert "aria-expanded={expanded}" in component
    assert 'role="group"' in component
    assert "aria-pressed={filter === item}" in component
    for class_name in (
        ".workspace",
        ".summaryGrid",
        ".headerActions",
        ".priorityGrid",
        ".filterGroup",
        ".controlRow",
        ".detailGrid",
        ".contextPanel",
    ):
        assert class_name in css
    assert "env(safe-area-inset-bottom)" in css
    assert "overflow-x:auto" in css
    assert "@media (max-width:760px)" in css
    assert "@media (max-width:520px)" in css
    assert "@media (prefers-reduced-motion:reduce)" in css
