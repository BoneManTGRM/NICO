from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "apps" / "web" / "app" / "operations" / "AssessmentRecoveryPanel.tsx"
PAGE = ROOT / "apps" / "web" / "app" / "operations" / "recovery" / "page.tsx"


def test_assessment_recovery_ui_wires_inventory_and_same_run_resume() -> None:
    panel = PANEL.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert "/operations/recovery/assessments?refresh=" in panel
    assert "/operations/recovery/assessment/" in panel
    assert "/resume" in panel
    assert '"X-NICO-Admin-Token": adminToken' in panel
    assert 'method: "POST"' in panel
    assert "Resume same run ID" in panel
    assert "No automatic continuation is permitted" in panel
    assert "AssessmentRecoveryPanel" in page
    assert "ScannerRecoveryPanel" in page
    assert "Recovery Control" in page


def test_recovery_page_keeps_operator_token_in_memory_only() -> None:
    source = PAGE.read_text(encoding="utf-8") + PANEL.read_text(encoding="utf-8")
    lowered = source.lower()

    assert 'const [admintoken, setadmintoken] = usestate("")' in lowered
    assert 'type="password"' in lowered
    assert 'autocomplete="off"' in lowered
    for forbidden in [
        "window.localstorage",
        "window.sessionstorage",
        "localstorage.getitem",
        "localstorage.setitem",
        "sessionstorage.getitem",
        "sessionstorage.setitem",
        "document.cookie",
        "window.name",
        "?admin_token=",
        "&admin_token=",
        "?admintoken=",
        "&admintoken=",
    ]:
        assert forbidden not in lowered


def test_recovery_ui_discloses_identity_reuse_and_human_control() -> None:
    panel = PANEL.read_text(encoding="utf-8")

    assert "Same run, snapshot, report, and approval identities are retained" in panel
    assert "Existing deterministic artifacts are reused rather than duplicated" in panel
    assert "All resumes require an authenticated operator claim" in panel
    assert "No automatic continuation is permitted" in panel
