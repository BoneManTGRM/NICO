from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "apps" / "web" / "app" / "operations" / "ScannerRecoveryPanel.tsx"
PAGE = ROOT / "apps" / "web" / "app" / "operations" / "recovery" / "page.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"


def test_scanner_recovery_ui_wires_inventory_and_same_id_resume() -> None:
    panel = PANEL.read_text(encoding="utf-8")

    assert "/operations/recovery?refresh=" in panel
    assert "/operations/recovery/scanner/" in panel
    assert "/resume" in panel
    assert '"X-NICO-Admin-Token": adminToken' in panel
    assert 'method: "POST"' in panel
    assert "Resume same scan ID" in panel
    assert "No automatic rerun is permitted" in panel
    assert "same durable scan ID" in PAGE.read_text(encoding="utf-8")


def test_recovery_token_remains_in_react_memory_only() -> None:
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
        "tokenparams",
    ]:
        assert forbidden not in lowered
    assert '{"x-nico-admin-token": admintoken}' in lowered


def test_recovery_is_linked_from_operator_navigation() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    navigation = NAVIGATION.read_text(encoding="utf-8")

    assert '{label: "Recovery", href: "/operations/recovery"}' in navigation
    assert 'label: "Operator workspaces"' in navigation
    assert "Operator-only deployment controls are available under" in layout
