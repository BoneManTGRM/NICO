from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "ReportPresentationGuard.tsx"
HELPER = ROOT / "apps" / "web" / "app" / "MidEvidencePacketHelper.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_report_guard_replaces_only_empty_score_denominators_with_not_scored():
    source = GUARD.read_text(encoding="utf-8")

    assert "EMPTY_SCORE" in source
    assert "NOT SCORED" in source
    assert "null|undefined|nan" in source
    assert "normalizeScoreLabels" in source
    assert "Numeric values such as 85/100" in source
    assert "if (!EMPTY_SCORE.test(current)) return;" in source
    assert r"(?:^|\s*·\s*)" in source
    assert r"(?:\s*·\s*)?" not in source


def test_report_guard_preserves_semantic_findings_and_collapses_mobile_cards():
    source = GUARD.read_text(encoding="utf-8")

    assert "removeDuplicateDetail" in source
    assert "seenParagraphs" in source
    assert "seenItems" in source
    assert 'querySelectorAll<HTMLParagraphElement>("p")' in source
    assert 'querySelectorAll<HTMLElement>("details, ul, ol")' in source
    assert 'querySelectorAll<HTMLLIElement>("li")' in source
    assert 'querySelectorAll<HTMLElement>("p, li")' not in source
    assert "a finding identical to the card summary is not removed" in source
    assert 'matchMedia("(max-width: 900px)")' in source
    assert 'removeAttribute("open")' in source
    assert "MutationObserver" in source


def test_mid_evidence_helper_submits_only_human_review_bound_repository_context():
    source = HELPER.read_text(encoding="utf-8")
    payload_source = source.lower().split("packetpayload", 1)[1].split("export default", 1)[0]

    assert "docs/mid-evidence/ARCHITECTURE.md" in source
    assert "docs/mid-evidence/DEPLOYMENT.md" in source
    assert "docs/mid-evidence/QA.md" in source
    assert "docs/mid-evidence/PRODUCT_CONTEXT.md" in source
    assert "docs/mid-evidence/ROADMAP.md" in source
    assert "score" not in payload_source
    assert "human-review-bound" in source
    assert "does not change scores automatically" in source
    assert "Native iOS and Android parity remains unavailable" in source


def test_mid_evidence_helper_tracks_new_session_run_without_reload():
    source = HELPER.read_text(encoding="utf-8")

    assert "syncSession" in source
    assert "window.setInterval(syncSession, 1000)" in source
    assert 'window.addEventListener("focus", syncSession)' in source
    assert "window.clearInterval(timer)" in source


def test_mid_evidence_packet_auto_attaches_once_and_keeps_manual_retry():
    source = HELPER.read_text(encoding="utf-8")

    assert "PACKET_PREFIX" in source
    assert "packetAttached" in source
    assert "void attachPacket(true)" in source
    assert "window.setTimeout" in source
    assert 'sessionStorage.setItem(PACKET_PREFIX + runId, "1")' in source
    assert "attached automatically to this exact Mid run" in source
    assert 'onClick={() => void attachPacket(false)}' in source


def test_mid_completion_actions_link_to_review_and_bound_report_workflow():
    source = HELPER.read_text(encoding="utf-8")

    assert "Attach NICO evidence packet" in source
    assert 'href="/mid-review"' in source
    assert 'href="/mid-report"' in source
    assert "Start a fresh Mid run" in source


def test_layout_installs_report_presentation_without_legacy_mid_evidence_overlay():
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'import ReportPresentationGuard from "./ReportPresentationGuard"' in source
    assert "<ReportPresentationGuard />" in source
    assert "MidEvidencePacketHelper" not in source
    assert 'href="/assessment?tier=express#assessment"' in source
    assert "Start Express or Comprehensive" in source
