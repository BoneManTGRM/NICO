from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "web" / "app" / "ReportPresentationGuard.tsx"


def test_comprehensive_run_identity_is_presented_without_raw_identifier() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "comprun_" in source
    assert 'return "Comprehensive Run"' in source
    assert "element.dataset.technicalRunId = technicalRunId" in source
    assert "Technical run ID:" in source
    assert "const displayLabel = friendlyTierLabel(technicalRunId)" in source
    assert "element.textContent = displayLabel" in source
    assert "Active authorized repository" in source


def test_mobile_report_cards_wrap_long_paths_and_use_compact_actions() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert 'const POLISH_STYLE_ID = "nico-comprehensive-ui-polish"' in source
    assert "overflow-wrap: anywhere" in source
    assert "word-break: break-word" in source
    assert "grid-template-columns: minmax(0, 1fr) auto" in source
    assert "max-width: 46vw" in source
    assert "grid-template-columns: 1fr" in source
    assert "main.shell[data-assessment-service-count] .report-actions button" in source


def test_polish_styles_apply_to_the_unified_single_assessment_shell() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "main.shell[data-assessment-service-count]" in source
    assert "data-assessment-service-count=\"2\"" not in source
    assert "ensurePolishStyles();" in source
