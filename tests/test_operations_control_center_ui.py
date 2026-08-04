from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "apps" / "web" / "app" / "operations"
PAGE = OPERATIONS / "page.tsx"
CONTROL_CENTER = OPERATIONS / "operations-control-center.tsx"
CONTROLLER = OPERATIONS / "use-operations-control-center.ts"
TYPES = OPERATIONS / "operations-types.ts"
STYLES = OPERATIONS / "operations.module.css"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"


def _runtime_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAGE, CONTROL_CENTER, CONTROLLER, TYPES)
    )


def test_operator_route_is_a_thin_composition_boundary() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'import {OperationsControlCenter}' in source
    assert "return <OperationsControlCenter />" in source
    assert len(source.splitlines()) <= 8
    assert "useState" not in source
    assert "fetch(" not in source
    assert "/operations/" not in source


def test_operator_control_center_wires_every_required_evidence_endpoint() -> None:
    source = _runtime_source()

    assert '"use client"' in source
    assert "NEXT_PUBLIC_NICO_API_URL" in source
    assert "/operations/readiness" in source
    assert "/operations/observability" in source
    assert "/operations/events" in source
    assert "/operations/alerts" in source
    assert '"/api/deployment"' in source
    assert "X-NICO-Admin-Token" in source
    assert "X-NICO-Correlation-ID" in source
    assert "frontend_commit" in source
    assert "event_window" in source
    assert "URLSearchParams" in source


def test_operator_token_remains_in_component_memory_only() -> None:
    source = _runtime_source()
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
    source = _runtime_source()
    normalized = " ".join(source.split())

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

    assert "Automatic remediation" in normalized
    assert "not allowed" in source
    assert "Unavailable" in source


def test_operator_page_is_responsive_and_available_from_operator_menu() -> None:
    css = STYLES.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    navigation = NAVIGATION.read_text(encoding="utf-8")

    assert "@media(max-width:1050px)" in css
    assert "@media(max-width:800px)" in css
    assert ".eventTable" in css
    assert ".alertList" in css
    assert '{label: "Operations (Admin)", href: "/operations"}' in navigation
    assert 'label: "Operator workspaces"' in navigation
    assert "Operator-only deployment controls are available under" in layout
    assert "More → Operations (Admin)" in layout
