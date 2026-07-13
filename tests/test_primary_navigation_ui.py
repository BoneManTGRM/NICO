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


def test_navigation_has_three_primary_service_destinations() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)

    assert primary.count('key: "') == 3
    assert set(re.findall(r'label: "([^"]+)"', primary)) == {
        "Run a Job",
        "Operations",
        "Retainer",
    }
    assert 'href: "/assessment?tier=express#assessment"' in primary
    assert 'href: "/operations"' in primary
    assert 'href: "/retainer-ops"' in primary
    assert 'data-primary-service-count="3"' in source
    for legacy_label in ("Express Assessment", "Mid Assessment", "Full Assessment"):
        assert legacy_label not in primary


def test_internal_workflow_steps_remain_out_of_global_more_menu() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)
    advanced = _advanced_block(source)

    assert '<details className="nav-more">' in source
    assert "Advanced tools" in source
    for label, href in {
        "Recovery": "/operations/recovery",
        "Backup & Restore": "/operations/backup-restore",
        "Scanner to Express": "/scanner-workflow",
        "Refresh Evidence": "/refresh-full-evidence",
        "Easy Mode": "/easy",
        "Start Job": "/start-job",
        "Guide": "/guided-workflow",
    }.items():
        assert f'{{label: "{label}", href: "{href}"}}' in advanced
        assert label not in primary
        assert href not in primary

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
    assert '<a className="global-brand" href="/assessment?tier=express#assessment" aria-label="NICO home">NICO</a>' in source


def test_run_a_job_uses_one_query_selected_intake() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    for required in [
        'type AssessmentMode = "express" | "mid" | "full"',
        'new URLSearchParams(window.location.search).get("tier")',
        'value === "mid" || value === "full"',
        'window.addEventListener(ASSESSMENT_TIER_EVENT',
        'window.addEventListener("popstate"',
        'pathname.startsWith("/assessment")',
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


def test_layout_uses_unified_assessment_and_preserves_safety_disclosures() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

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
        "unified assessment page",
        "One Run action completes every automated stage",
        "stop at required human review",
        "never approves findings",
        "does not create a client delivery link",
        "Client downloads require acknowledgement",
        "review interrupted scanner work",
        "Retainer workflow:",
    ]:
        assert disclosure in layout


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
