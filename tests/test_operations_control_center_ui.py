from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "operations" / "page.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "operations" / "operations.module.css"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_operator_control_center_wires_every_required_evidence_endpoint() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '"use client"' in source
    assert 'NEXT_PUBLIC_NICO_API_URL' in source
    assert '/operations/readiness' in source
    assert '/operations/observability' in source
    assert '/operations/events' in source
    assert '/operations/alerts' in source
    assert '"/api/deployment"' in source
    assert 'X-NICO-Admin-Token' in source
    assert 'X-NICO-Correlation-ID' in source
    assert 'frontend_commit' in source
    assert 'event_window' in source
    assert 'URLSearchParams' in source


def test_operator_token_remains_in_component_memory_only() -> None:
    source = PAGE.read_text(encoding="utf-8")
    lowered = source.lower()

    assert 'const [admintoken, setadmintoken] = usestate("")' in lowered
    assert 'type="password"' in lowered
    assert 'autocomplete="off"' in lowered
    for forbidden_access in [
        "window.localstorage",
        "window.sessionstorage",
        "localstorage.getitem",
        "localstorage.setitem",
        "sessionstorage.getitem",
        "sessionstorage.setitem",
        "document.cookie",
        "window.name",
    ]:
        assert forbidden_access not in lowered
    assert "admintoken=" not in lowered
    assert "tokenparams" not in lowered
    assert '{"x-nico-admin-token": admintoken}' in lowered


def test_operator_page_surfaces_required_status_and_incident_fields() -> None:
    source = PAGE.read_text(encoding="utf-8")

    required_labels = [
        "Semantic readiness",
        "Release alignment",
        "Durable storage",
        "Failure rate",
        "Timeout rate",
        "P95 latency",
        "Assessment runs",
        "Scanner runs",
        "Oldest queue age",
        "Scanner duration",
        "Report generation",
        "Deterministic alerts",
        "Correlation ID",
        "Readiness checks",
    ]
    for label in required_labels:
        assert label in source

    for severity in ["p0", "p1", "p2", "p3"]:
        assert f'"{severity}"' in source

    assert "Automatic remediation" in source
    assert "not allowed" in source
    assert "Unavailable" in source


def test_operator_page_is_responsive_and_added_to_primary_navigation() -> None:
    css = STYLES.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert "@media(max-width:1050px)" in css
    assert "@media(max-width:800px)" in css
    assert ".eventTable" in css
    assert ".alertList" in css
    assert '<a href="/operations">Operations</a>' in layout
    assert "Operators can verify deployment" in layout
