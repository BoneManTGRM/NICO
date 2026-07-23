from __future__ import annotations

# Regression contract for NICO's canonical customer and operator navigation.

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
NAV_STYLES = ROOT / "apps" / "web" / "styles" / "navigation.css"
POLISH_STYLES = ROOT / "apps" / "web" / "styles" / "professional-polish.css"


def _primary_block(source: str) -> str:
    return source.split("export const PRIMARY_SERVICES = [", 1)[1].split("] as const;", 1)[0]


def _secondary_block(source: str) -> str:
    return source.split("const SECONDARY_GROUPS = [", 1)[1].split("] as const;", 1)[0]


def test_navigation_keeps_one_canonical_primary_assessment_destination() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)

    assert primary.count('key: "') == 1
    assert set(re.findall(r'label: "([^"]+)"', primary)) == {"Run Assessment"}
    assert 'href: "/assessment?tier=express#assessment"' in primary
    assert 'href: "/operations"' not in primary
    assert 'href: "/retainer-ops"' not in primary
    assert 'data-primary-service-count="1"' in source
    for legacy_label in ("Express Assessment", "Mid Assessment", "Full Assessment", "Start Job"):
        assert legacy_label not in primary


def test_more_menu_exposes_only_help_and_authorized_operator_destinations() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    secondary = _secondary_block(source)

    for label, href in {
        "Guide": "/guided-workflow",
        "Operations (Admin)": "/operations",
        "Retainer Ops": "/retainer-ops",
    }.items():
        assert f'{{label: "{label}", href: "{href}"}}' in secondary

    for removed in (
        "Recovery",
        "Backup & Restore",
        "Scanner to Express",
        "Refresh Evidence",
        "Easy Mode",
        "/operations/recovery",
        "/operations/backup-restore",
        "/scanner-workflow",
        "/refresh-full-evidence",
        'href: "/easy"',
    ):
        assert removed not in secondary

    assert "Secondary navigation" in source
    assert "The primary assessment workflow remains under Run Assessment" in source
    assert 'className="global-brand" href="/assessment?tier=express#assessment"' in source


def test_spanish_route_localizes_the_simplified_navigation_shell() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    assert 'const spanishActive = pathname.startsWith("/es")' in source
    assert 'const languageHref = spanishActive ? "/assessment?tier=express#assessment" : "/es/assessment?tier=express#assessment"' in source
    assert '"run-job": "Ejecutar evaluación"' in source
    for translated in (
        "Navegación secundaria",
        "Ayuda",
        "Espacios de trabajo del operador",
        "Operaciones (administrador)",
        "Servicio continuo",
        "Guía",
    ):
        assert translated in source
    for removed in ("Recuperación", "Respaldo y restauración", "Escáner a Express", "Actualizar evidencia", "Modo fácil"):
        assert removed not in source
    assert 'spanishActive ? "Más" : "More"' in source
    assert 'spanishActive ? "Navegación principal de NICO" : "NICO primary navigation"' in source
    assert 'lang={spanishActive ? "es-MX" : undefined}' in source


def test_run_assessment_uses_one_query_selected_native_intake() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    for required in [
        'type AssessmentMode = "express" | "comprehensive"',
        'new URLSearchParams(window.location.search).get("tier")',
        '["comprehensive", "mid", "full", "deep"].includes',
        "window.addEventListener(ASSESSMENT_TIER_EVENT",
        'window.addEventListener("popstate"',
        'pathname.startsWith("/assessment")',
        'pathname.startsWith("/es/assessment")',
        'pathname.startsWith("/operations")',
        'pathname.startsWith("/retainer-ops")',
        'aria-current={active ? "page" : undefined}',
    ]:
        assert required in source
    assert "MutationObserver" not in source
    assert "requestedButton.click()" not in source


def test_layout_preserves_safety_disclosures_and_loads_final_polish() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    for required in (
        'import "../styles/navigation.css";',
        'import "../styles/professional-polish.css";',
        'import {MidWorkspaceProvider} from "./MidWorkspaceContext";',
        'import OperationsPreloadGuard from "./OperationsPreloadGuard";',
        'import PrimaryNavigation from "./PrimaryNavigation";',
        "<MidWorkspaceProvider>",
        "<OperationsPreloadGuard />",
        "<PrimaryNavigation />",
        "Assessment workflow:",
        "Start Express or Comprehensive",
        "captures one immutable commit",
        "required human review",
        "never approves findings or creates client delivery automatically",
        "More → Guide",
        "More → Operations (Admin)",
        "More → Retainer Ops",
    ):
        assert required in layout
    assert '<div className="global-links">' not in layout


def test_navigation_and_assessment_cards_remain_mobile_contained() -> None:
    navigation = NAV_STYLES.read_text(encoding="utf-8")
    polish = POLISH_STYLES.read_text(encoding="utf-8")

    assert ".primary-service-link.active" in navigation
    assert ".nav-more-panel" in navigation
    assert "@media (max-width: 820px)" in navigation
    for required in (
        'main.shell[data-assessment-service-count="2"] .target-grid article',
        "overflow-wrap: anywhere;",
        "word-break: break-word;",
        "font-size: clamp(15px, 3.8vw, 21px);",
        "@media (max-width: 760px)",
        "@media (max-width: 430px)",
        "max-width: min(680px, calc(100vw - 32px));",
    ):
        assert required in polish
