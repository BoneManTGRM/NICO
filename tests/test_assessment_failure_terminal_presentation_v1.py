from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PANEL = ROOT / "apps" / "web" / "app" / "AssessmentFailureEvidencePanel.tsx"
FAILURE_CSS = ROOT / "apps" / "web" / "styles" / "assessment-failure-terminal.css"
MOBILE_STABILITY = ROOT / "apps" / "web" / "styles" / "assessment-mobile-stability.css"


def test_failure_styles_load_after_mobile_stability_boundary() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    stability = source.index('import "../styles/assessment-mobile-stability.css"')
    terminal_failure = source.index('import "../styles/assessment-failure-terminal.css"')
    assert stability < terminal_failure


def test_failure_panel_reconciles_duplicate_and_contradictory_state() -> None:
    source = PANEL.read_text(encoding="utf-8")

    assert 'data-assessment-failure-evidence="true"' in source
    assert 'main[data-workspace="assessment"]' in source
    assert 'section[data-assessment-run-state="true"]' in source
    assert 'main.dataset.assessmentTerminalFailure = "true"' in source
    assert 'state.dataset.assessmentFailureReconciled = "true"' in source
    assert 'packageValue: "Blocked during final report generation"' in source
    assert 'reviewValue: "Not reached"' in source
    assert 'packageValue: "Bloqueado durante la generación del informe final"' in source
    assert 'reviewValue: "No alcanzada"' in source
    assert "new MutationObserver(apply)" in source


def test_failure_panel_keeps_raw_diagnostics_collapsed() -> None:
    source = PANEL.read_text(encoding="utf-8")

    assert 'title: "The assessment stopped"' in source
    assert 'summary: "Completed analysis and the exact run identity remain preserved' in source
    assert '<details className="help-details nico-failure-evidence__details">' in source
    assert '<summary>{copy.details}</summary>' in source
    assert '<div><dt>{copy.code}</dt><dd><code>{failure.code}</code></dd></div>' in source
    assert '<div><dt>{copy.message}</dt><dd>{failure.message}</dd></div>' in source
    assert 'recovery: "Open this run in Recovery"' in source


def test_mobile_failure_surface_hides_duplicate_intake_and_wraps_identity() -> None:
    source = FAILURE_CSS.read_text(encoding="utf-8")
    stability = MOBILE_STABILITY.read_text(encoding="utf-8")

    assert 'body[data-nico-terminal-failure="true"] main[data-workspace="assessment"] > .hero' in source
    assert 'section#assessment' in source
    assert 'section[data-assessment-run-state="true"] > .section-head' in source
    assert '[data-assessment-report-actions="true"]' in source
    assert '.nico-failure-evidence__primary code' in source
    assert "overflow-wrap: anywhere" in source
    assert "env(safe-area-inset-top, 0px)" in source
    assert "grid-template-columns: minmax(0, 1fr)" in source
    assert "assessment-mobile-stability.css" in str(MOBILE_STABILITY)
    assert 'main[data-workspace="assessment"]' in stability
    assert '[data-assessment-run-state="true"]' in stability
    assert "overflow-anchor: none !important" in stability
