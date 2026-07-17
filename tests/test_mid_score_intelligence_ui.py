from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps" / "web" / "app" / "MidScoreIntelligencePortal.tsx"
UNIFIED = ROOT / "apps" / "web" / "app" / "assessment" / "MidSectionReview.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_mid_score_transport_captures_exact_status_responses_once() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert "assessment\\/mid-run" in source
    assert "response.clone().json()" in source
    assert "nico:mid-status-payload" in source
    assert "publishMidPayload(parsed)" in source
    assert "window.fetch = captureFetch" in source
    assert "createPortal" not in source
    assert "querySelectorAll" not in source
    assert "return null" in source


def test_unified_mid_surface_contains_score_contract_without_second_panel() -> None:
    source = UNIFIED.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert "Express is a faster baseline" in source
    assert "seven fixed technical weights" in source
    assert "verified-fix scenario" in source
    assert "Evidence-unit coverage" in source
    assert "new immutable snapshot assessment" in source
    assert "weightTable" in source
    assert 'import MidScoreIntelligencePortal from "./MidScoreIntelligencePortal"' in layout
    assert "<MidScoreIntelligencePortal />" in layout
    assert "<MidSectionReviewPortal />" in layout
