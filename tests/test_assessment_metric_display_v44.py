from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/assessment/AssessmentMetricDisplayV44.tsx"
CSS = ROOT / "apps/web/app/assessment/assessment-metric-display-v44.css"
ROUTE = ROOT / "apps/web/app/assessment/page.tsx"
SPANISH_ROUTE = ROOT / "apps/web/app/es/assessment/page.tsx"
PAGE = ROOT / "apps/web/app/assessment/AssessmentPage.tsx"


def test_metric_display_is_bound_through_the_canonical_page_for_both_locales() -> None:
    route = ROUTE.read_text(encoding="utf-8")
    spanish_route = SPANISH_ROUTE.read_text(encoding="utf-8")
    source = PAGE.read_text(encoding="utf-8")
    assert 'import AssessmentPage from "./AssessmentPage"' in route
    assert '<AssessmentPage locale="en-US" />' in route
    assert 'import AssessmentPage from "../../assessment/AssessmentPage"' in spanish_route
    assert '<AssessmentPage locale="es-MX" />' in spanish_route
    assert 'import AssessmentMetricDisplayV44 from "./AssessmentMetricDisplayV44"' in source
    assert "<AssessmentMetricDisplayV44 />" in source


def test_service_descriptors_do_not_change_exact_button_inner_text() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    styles = CSS.read_text(encoding="utf-8")
    assert 'button.setAttribute("aria-label", label)' in source
    assert "button.dataset.serviceDetail = descriptor" in source
    assert 'detail.textContent = ""' in source
    assert 'content: attr(data-service-detail)' in styles
    assert '.nico-service-detail {' in styles
    assert "display: none !important" in styles


def test_scanner_worker_is_presented_as_execution_coverage_not_technical_score() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    styles = CSS.read_text(encoding="utf-8")
    assert 'card.dataset.nicoMetricKind = "execution-coverage"' in source
    assert '"Execution coverage"' in source
    assert '"Excluded from maturity"' in source
    assert 'data-nico-metric-kind="execution-coverage"' in styles
