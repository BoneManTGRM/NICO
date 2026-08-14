from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = (
    ROOT / "apps" / "web" / "app" / "AssessmentActiveRunReset.tsx"
).read_text(encoding="utf-8")
MOBILE_CSS = (
    ROOT / "apps" / "web" / "styles" / "assessment-mobile-stability.css"
).read_text(encoding="utf-8")


def test_mobile_active_run_controls_are_collapsible_and_accessible() -> None:
    assert 'const MOBILE_ACTIVE_RUN_QUERY = "(max-width: 760px), (pointer: coarse)"' in COMPONENT
    assert "const [collapsed, setCollapsed] = useState(false)" in COMPONENT
    assert "window.matchMedia?.(MOBILE_ACTIVE_RUN_QUERY).matches" in COMPONENT
    assert "setCollapsed(true)" in COMPONENT
    assert 'data-assessment-active-run-toggle="true"' in COMPONENT
    assert 'aria-controls="nico-current-assessment-controls"' in COMPONENT
    assert "aria-expanded={!collapsed}" in COMPONENT
    assert "setCollapsed((value) => !value)" in COMPONENT
    assert '{collapsed ? "Show" : "Hide"}' in COMPONENT


def test_clear_current_run_action_remains_available_when_expanded() -> None:
    assert 'id="nico-current-assessment-controls"' in COMPONENT
    assert 'data-assessment-clear-current-run="true"' in COMPONENT
    assert "Clear current run and start new assessment" in COMPONENT
    assert "{!collapsed ? (" in COMPONENT


def test_fixed_panel_exports_its_measured_height_for_document_clearance() -> None:
    assert "const panelRef = useRef<HTMLElement | null>(null)" in COMPONENT
    assert "panel.getBoundingClientRect().height" in COMPONENT
    assert '"data-assessment-active-run-reset-visible"' in COMPONENT
    assert '"--nico-active-run-reset-clearance"' in COMPONENT
    assert "new ResizeObserver(reserveViewportSpace)" in COMPONENT
    assert 'window.addEventListener("resize", reserveViewportSpace)' in COMPONENT
    assert "clearReservedViewportSpace()" in COMPONENT


def test_mobile_document_reserves_space_below_the_fixed_panel() -> None:
    assert 'html[data-assessment-active-run-reset-visible="true"] body.nico-app' in MOBILE_CSS
    assert "var(--nico-active-run-reset-clearance, 68px)" in MOBILE_CSS
    assert "padding-bottom: calc(" in MOBILE_CSS
    assert "scroll-padding-bottom: calc(" in MOBILE_CSS
    assert 'details[class*="compactIdentity"]' in MOBILE_CSS
    assert "scroll-margin-bottom: calc(" in MOBILE_CSS


def test_repair_does_not_change_run_reset_or_approval_boundaries() -> None:
    assert 'window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY)' in COMPONENT
    assert 'url.searchParams.delete(ACTIVE_RUN_QUERY_KEY)' in COMPONENT
    assert 'url.searchParams.set("new_assessment", String(Date.now()))' in COMPONENT
    assert "human_review" not in COMPONENT
    assert "client_delivery" not in COMPONENT
    assert "approved_delivery" not in COMPONENT
