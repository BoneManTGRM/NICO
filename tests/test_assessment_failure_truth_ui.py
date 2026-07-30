from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_layout_installs_terminal_failure_response_bridge_after_existing_transports() -> None:
    layout = _read("apps/web/app/layout.tsx")

    assert 'import AssessmentFailureResponseBridge from "./AssessmentFailureResponseBridge";' in layout
    assert "<AssessmentFailureResponseBridge />" in layout
    assert layout.index("<AssessmentExactCommitTransport />") < layout.index("<AssessmentFailureResponseBridge />")


def test_bridge_preserves_backend_failure_payload_without_relabeling_it_successful() -> None:
    source = _read("apps/web/app/AssessmentFailureResponseBridge.tsx")

    assert 'const TERMINAL_FAILURES = new Set(["blocked", "failed", "error", "interrupted", "rejected"]);' in source
    assert "status: 200" in source
    assert '"X-NICO-Original-Status"' in source
    assert '"X-NICO-Terminal-Failure": "true"' in source
    assert "human_review_required: true" in source
    assert "client_ready: false" in source
    assert "client_delivery_allowed: false" in source
    assert "failure_stage" in source
    assert "failure_code" in source


def test_failure_panel_supports_bilingual_semantic_state_and_hides_unavailable_report_actions() -> None:
    source = _read("apps/web/app/AssessmentFailureEvidencePanel.tsx")

    assert 'window.location.pathname.startsWith("/assessment")' in source
    assert 'window.location.pathname.startsWith("/es/assessment")' in source
    assert 'failedStage: "Failed stage"' in source
    assert 'failedStage: "Etapa que falló"' in source
    assert 'title: "The assessment stopped"' in source
    assert 'title: "La evaluación se detuvo"' in source
    assert 'data-assessment-failure-evidence="true"' in source
    assert 'data-assessment-failure-stage={failedStage?.step || "unknown_stage"}' in source
    assert 'data-assessment-failure-code={failure.code}' in source
    assert 'const reportActions = state.querySelector<HTMLElement>(\'[data-assessment-report-actions="true"]\')' in source
    assert "if (reportActions) reportActions.hidden = true" in source
    assert '<details className="help-details nico-failure-evidence__details">' in source
    assert 'href={recoveryHref}' in source
    assert '`/operations/recovery?run_id=${encodeURIComponent(failure.run_id)}' in source
