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


def test_failure_panel_supports_english_and_spanish_and_hides_unavailable_report_actions() -> None:
    source = _read("apps/web/app/AssessmentFailureEvidencePanel.tsx")

    assert 'window.location.pathname.startsWith("/assessment")' in source
    assert 'window.location.pathname.startsWith("/es/assessment")' in source
    assert "Actual failed stage" in source
    assert "Etapa que falló" in source
    assert "ASSESSMENT FAILURE EVIDENCE" in source
    assert "EVIDENCIA DE FALLO DE LA EVALUACIÓN" in source
    assert 'body[data-nico-terminal-failure="true"] .report-actions' in source
    assert 'href="/operations/recovery"' in source
    assert "/operations/recovery?run_id=" in source
