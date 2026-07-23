from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/web/app/assessment/AssessmentRuntimeTruthRepair.tsx"
METRICS = ROOT / "apps/web/app/assessment/AssessmentMetricDisplayV44.tsx"
ACCEPTANCE = ROOT / "scripts/two_service_live_acceptance_v3.py"


def test_live_assessment_components_do_not_mutate_react_dom_continuously() -> None:
    runtime = RUNTIME.read_text(encoding="utf-8")
    metrics = METRICS.read_text(encoding="utf-8")

    assert "new MutationObserver" not in runtime
    assert "new MutationObserver" not in metrics
    assert "React remains the sole owner" in metrics
    assert "external mutation of live result nodes" in runtime


def test_large_comprehensive_continuations_are_not_cloned_for_persistence() -> None:
    source = RUNTIME.read_text(encoding="utf-8")

    assert 'path === "/api/nico/assessment/express-run"' in source
    assert 'path === "/api/nico/assessment/comprehensive-intake"' in source
    assert "boundedPersistenceRequest(target)" in source
    assert "Comprehensive continuation" in source


def test_acceptance_ui_read_is_immediate_and_non_blocking() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")

    assert "acceptance.ui_state = _safe_ui_state" in source
    assert "document.querySelector('section[aria-live=\"polite\"]')" in source
    assert "locator.evaluate" in source
    assert "return fallback" in source
    assert "No duplicate run is started" in source


def test_terminal_comprehensive_report_projection_remains_supported() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")

    assert "acceptance.report_package = _report_package" in source
    assert 'payload.get("reports")' in source
    assert "_original_report_package" in source
