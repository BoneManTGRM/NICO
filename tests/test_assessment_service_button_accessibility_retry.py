from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/assessment/AssessmentMetricDisplayV44.tsx"


def test_service_button_accessibility_retries_only_until_hydration_is_ready() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert "requestAnimationFrame(reconcileUntilReady)" in source
    assert "serviceButtonCount < 2" in source
    assert "attempts < 120" in source
    assert 'button.setAttribute("aria-label", label)' in source
    assert "MutationObserver" not in source
