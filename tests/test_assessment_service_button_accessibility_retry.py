from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/assessment/AssessmentMetricDisplayV44.tsx"


def test_service_button_accessibility_survives_late_hydration_replacement() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "requestAnimationFrame(reconcileDuringHydration)" in source
    assert "attempts >= 120" in source
    assert "reconcileServiceAccessibility();" in source
    assert 'button.setAttribute("aria-label", label)' in source
    assert "Hydration may replace already-present server nodes" in source
    assert "MutationObserver" not in source


def test_hydration_reconciliation_is_bounded_to_service_buttons() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "#assessment button[aria-pressed]" in source
    assert "dynamic assessment result tree" in source
    assert "document.body" not in source
