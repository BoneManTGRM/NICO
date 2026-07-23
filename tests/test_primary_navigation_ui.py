from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
STYLES = ROOT / "apps" / "web" / "styles" / "navigation.css"


def _primary_block(source: str) -> str:
    return source.split("export const PRIMARY_SERVICES = [", 1)[1].split("] as const;", 1)[0]


def _advanced_block(source: str) -> str:
    return source.split("const ADVANCED_GROUPS = [", 1)[1].split("] as const;", 1)[0]


def test_navigation_keeps_one_primary_assessment_destination() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)
    advanced = _advanced_block(source)

    assert primary.count('key: "') == 1
    assert set(re.findall(r'label: "([^"]+)"', primary)) == {"Run Assessment"}
    assert 'href: "/assessment?tier=express#assessment"' in primary
    assert 'href: "/operations"' not in primary
    assert 'href: "/retainer-ops"' not in primary
    assert 'data-primary-service-count="1"' in source
    assert '{label: "Operations (Admin)", href: "/operations"}' in advanced
    assert '{label: "Retainer Ops", href: "/retainer-ops"}' in advanced
    for legacy_label in ("Express Assessment", "Mid Assessment", "Full Assessment"):
        assert legacy_label not in primary


def test_internal_workflow_steps_remain_out_of_global_more_menu() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)
    advanced = _advanced_block(source)

    assert 'className={`nav-more${advancedActive ? " active" : ""}`}' in source
    assert "Operator and advanced tools" in source
    for label, href in {
        "Operations (Admin)": "/operations",
        "Retainer Ops": "/retainer-ops",
        "Recovery": "/operations/recovery",
        "Backup & Restore": "/operations/backup-restore",
        "Scanner to Express": "/scanner-workflow",
        "Refresh Evidence": "/refresh-full-evidence",
        "Easy Mode": "/easy",
        "Guide": "/guided-workflow",
    }.items():
        assert f'{{label: "{label}", href: "{href}"}}' in advanced
        assert label not in primary
        assert href not in primary

    assert 'label: "Start Job"' not in source
    assert 'href: "/start-job"' not in source

    for label, href in {
        "Mid Review": "/mid-review",
        "Mid Report": "/mid-report",
        "Mid Approval": "/mid-approval",
        "Mid Delivery": "/mid-delivery-admin",
        "Full Run": "/full-run",
    }.items():
        assert label not in advanced
        assert href not in advanced

    assert 'label: "Command Center"' not in source
    assert 'className="global-brand" href="/assessment?tier=express#assessment"' in source


def test_spanish_route_localizes_the_complete_shared_navigation_shell() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    assert 'const spanishActive = pathname.startsWith("/es")' in source
    assert 'const languageHref = spanishActive ? "/assessment?tier=express#assessment" : "/es/assessment?tier=express#assessment"' in source
    assert "SPANISH_PRIMARY_LABELS" in source
    assert '"run-job": "Ejecutar evaluación"' in source
    assert 'operations: "Operaciones (administrador)"' in source
    assert "const SPANISH_ADVANCED_GROUPS" in source
    for translated in (
        "Espacios para operadores",
        "Administración del despliegue y actualización continua de evidencia",
        "Operaciones (administrador)",
        "Servicio continuo",
        "Recuperación",
        "Respaldo y restauración",
        "Herramientas avanzadas de evidencia",
        "Escáner a Express",
        "Actualizar evidencia",
        "Modo fácil",
        "Guía",
    ):
        assert translated in source

    assert "Iniciar trabajo" not in source
    assert 'spanishActive ? "Más" : "More"' in source
    assert 'spanishActive ? "Navegación principal de NICO" : "NICO primary navigation"' in source
    assert 'spanishActive ? "Abrir herramientas para operadores y herramientas avanzadas" : "Open operator and advanced tools"' in source
    assert "const advancedGroups = spanishActive ? SPANISH_ADVANCED_GROUPS : ADVANCED_GROUPS" in source
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
    ]:
        assert required in source

    assert "MutationObserver" not in source
    assert "requestedButton.click()" not in source
    assert 'pathname.startsWith("/full-run")' in source
    assert 'pathname.startsWith("/mid-assessment")' in source
    assert 'pathname.startsWith("/mid-review")' in source
    assert 'pathname.startsWith("/mid-report")' in source
    assert 'pathname.startsWith("/mid-approval")' in source
    assert 'pathname.startsWith("/mid-delivery-admin")' in source
    assert 'pathname.startsWith("/operations")' in source
    assert 'pathname.startsWith("/retainer-ops")' in source
    assert 'aria-current={active ? "page" : undefined}' in source


def test_layout_uses_native_assessment_and_preserves_safety_disclosures() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    navigation = NAVIGATION.read_text(encoding="utf-8")

    assert 'import "../styles/navigation.css";' in layout
    assert 'import {MidWorkspaceProvider} from "./MidWorkspaceContext";' in layout
    assert 'import OperationsPreloadGuard from "./OperationsPreloadGuard";' in layout
    assert 'import PrimaryNavigation from "./PrimaryNavigation";' in layout
    assert "<MidWorkspaceProvider>" in layout
    assert "</MidWorkspaceProvider>" in layout
    assert "<OperationsPreloadGuard />" in layout
    assert "<PrimaryNavigation />" in layout
    assert '<div className="global-links">' not in layout
    for disclosure in [
        "Assessment workflow:",
        "Start Express or Comprehensive",
        "captures one immutable commit",
        "required human review",
        "never approves findings or creates client delivery automatically",
        "Operator-only deployment controls",
        "More → Operations (Admin)",
        "Ongoing weekly and monthly evidence refresh",
        "More → Retainer Ops",
    ]:
        assert disclosure in layout
    assert '{label: "Recovery", href: "/operations/recovery"}' in navigation
    for legacy_global in (
        "AssessmentMidLiveStatusTransport",
        "AssessmentSavedMidRunGuard",
        "MidScoreIntelligencePortal",
        "MidSectionReviewPortal",
        "UnifiedMidTokenCapture",
        "MidAssessmentCompanion",
        "MidEvidencePacketHelper",
    ):
        assert legacy_global not in layout


def test_navigation_and_advanced_stages_stay_compact_and_mobile_scrollable() -> None:
    css = STYLES.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".primary-service-link.active" in css
    assert ".nav-more-panel" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".mid-stage-links" in css
    assert ".mid-workspace-grid" in css
    assert ".mid-stage-link.active" in css
    assert "@media (max-width: 820px)" in css
    assert "overflow-x: auto;" in css
    assert "flex: 0 0 auto;" in css
    assert "@media (max-width: 620px)" in css
    assert "position: fixed;" in css
