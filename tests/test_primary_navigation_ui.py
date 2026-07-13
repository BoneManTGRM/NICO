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


def test_navigation_has_exactly_five_primary_service_destinations() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)

    assert primary.count('key: "') == 5
    assert set(re.findall(r'label: "([^"]+)"', primary)) == {
        "Express Assessment",
        "Mid Assessment",
        "Full Assessment",
        "Operations",
        "Retainer",
    }
    assert 'href: "/?assessment=express#assessment"' in primary
    assert 'href: "/?assessment=mid#assessment"' in primary
    assert 'href: "/full-run"' in primary
    assert 'href: "/operations"' in primary
    assert 'href: "/retainer-ops"' in primary
    assert 'data-primary-service-count="5"' in source


def test_internal_workflow_steps_are_grouped_under_one_advanced_menu() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    primary = _primary_block(source)
    advanced = _advanced_block(source)

    assert '<details className="nav-more">' in source
    assert "Advanced tools" in source
    for label, href in {
        "Mid Review": "/mid-review",
        "Mid Report": "/mid-report",
        "Mid Approval": "/mid-approval",
        "Mid Delivery": "/mid-delivery-admin",
        "Recovery": "/operations/recovery",
        "Scanner to Express": "/scanner-workflow",
        "Refresh Evidence": "/refresh-full-evidence",
        "Easy Mode": "/easy",
        "Start Job": "/start-job",
        "Guide": "/guided-workflow",
    }.items():
        assert f'{{label: "{label}", href: "{href}"}}' in advanced
        assert label not in primary
        assert href not in primary

    assert 'label: "Command Center"' not in source
    assert '<a className="global-brand" href="/" aria-label="NICO home">NICO</a>' in source


def test_express_and_mid_links_synchronize_the_existing_unified_intake() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    for required in [
        'new URLSearchParams(window.location.search).get("assessment")',
        'requested === "mid" ? "mid" : "express"',
        'document.querySelector<HTMLElement>("[aria-label=\'Assessment type\']")',
        'requestedButton.click()',
        'attributeFilter: ["aria-pressed"]',
        'url.searchParams.set("assessment", mode)',
        'window.history.replaceState(',
        'url.hash || "#assessment"',
    ]:
        assert required in source

    assert 'pathname.startsWith("/mid-review")' in source
    assert 'pathname.startsWith("/operations")' in source
    assert 'pathname.startsWith("/retainer-ops")' in source
    assert 'aria-current={active ? "page" : undefined}' in source


def test_layout_uses_navigation_component_and_preserves_safety_disclosures() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import "../styles/navigation.css";' in layout
    assert 'import PrimaryNavigation from "./PrimaryNavigation";' in layout
    assert "<PrimaryNavigation />" in layout
    assert '<div className="global-links">' not in layout
    for disclosure in [
        "Mid workflow:",
        "review-by-exception packet",
        "Approval creates a separate approved artifact",
        "does not create a client delivery link",
        "Client downloads require acknowledgement",
        "review interrupted scanner work",
        "Retainer workflow:",
    ]:
        assert disclosure in layout


def test_navigation_stays_compact_on_desktop_and_scrollable_on_mobile() -> None:
    css = STYLES.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in css
    assert ".primary-service-link.active" in css
    assert ".nav-more-panel" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert "@media (max-width: 820px)" in css
    assert "overflow-x: auto;" in css
    assert "flex: 0 0 auto;" in css
    assert "@media (max-width: 620px)" in css
    assert "position: fixed;" in css
