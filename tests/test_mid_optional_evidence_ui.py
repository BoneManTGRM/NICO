from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPANION = ROOT / "apps" / "web" / "app" / "MidAssessmentCompanion.tsx"
HELPER = ROOT / "apps" / "web" / "app" / "MidEvidencePacketHelper.tsx"
TOKEN_CAPTURE = ROOT / "apps" / "web" / "app" / "UnifiedMidTokenCapture.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def _companion() -> str:
    return COMPANION.read_text(encoding="utf-8")


def test_legacy_mid_evidence_components_are_retained_but_not_globally_mounted() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert COMPANION.exists()
    assert HELPER.exists()
    assert TOKEN_CAPTURE.exists()
    assert "MidAssessmentCompanion" not in layout
    assert "MidEvidencePacketHelper" not in layout
    assert "UnifiedMidTokenCapture" not in layout
    assert 'href="/assessment?tier=express#assessment"' in layout
    assert "Start Express or Comprehensive" in layout


def test_companion_remains_a_legacy_command_center_console() -> None:
    source = _companion()

    assert 'window.location.pathname === "/"' in source
    assert "if (!active || !runId) return null" in source
    assert 'id="mid-evidence-console"' in source
    assert 'runId.startsWith("midrun_")' not in source
    assert 'resolvedRunId.startsWith("midrun_")' in source


def test_legacy_token_capture_still_recognizes_mid_capability_without_rendering_it() -> None:
    source = TOKEN_CAPTURE.read_text(encoding="utf-8")

    assert 'pathname !== "/assessment"' in source
    assert 'path === "/assessment/mid-run"' in source
    assert "isMidStatusPath(path)" in source
    assert "response.clone().json()" in source
    assert "sessionStorage.setItem(RUN_KEY, runId)" in source
    assert "sessionStorage.setItem(TOKEN_PREFIX + runId, token)" in source
    assert "return null" in source
    assert "{token}" not in source


def test_legacy_evidence_packet_helper_is_not_part_of_native_public_intake() -> None:
    source = HELPER.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'const supported = pathname === "/" || pathname === "/assessment"' in source
    assert 'setVisible(pathname === "/")' in source
    assert "if (!active || !visible || !runId) return null" in source
    assert "void attachPacket(true)" in source
    assert "MidEvidencePacketHelper" not in layout
