from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_comprehensive_transport_errors_are_not_synthetic_terminal_failures() -> None:
    source = _source("apps/web/app/AssessmentFailureResponseBridge.tsx")

    guard = "if (COMPREHENSIVE_ROUTE.test(route) && !response.ok) return null;"
    assert guard in source
    assert source.index(guard) < source.index("await response.clone().json()")
    assert "assessment_run" not in guard


def test_markdown_bridge_cannot_swallow_click_before_exact_run_binding() -> None:
    source = _source("apps/web/app/AssessmentMarkdownCopyBridge.tsx")
    handler = source[source.index("async function handleCopyMarkdownClick") :]

    ready = 'actions.getAttribute("data-assessment-report-ready") !== "true"'
    exact = "const entry = entryForVisibleRun(actions);"
    cancel = "event.preventDefault();"
    assert ready in handler
    assert exact in handler
    assert cancel in handler
    assert handler.index(ready) < handler.index(exact) < handler.index(cancel)
    assert "if (!entry) return;" in handler[: handler.index(cancel)]


def test_pdf_bridge_cannot_swallow_click_before_exact_run_binding() -> None:
    source = _source("apps/web/app/AssessmentReviewPdfDownload.tsx")
    handler = source[source.index("function handleReviewPdfClick") :]

    ready = 'actions.getAttribute("data-assessment-report-ready") !== "true"'
    exact = "const runId = visibleRunId(actions);"
    bound = 'if (!runId.startsWith("comprun_")) return;'
    cancel = "event.preventDefault();"
    assert ready in handler
    assert exact in handler
    assert bound in handler
    assert cancel in handler
    assert handler.index(ready) < handler.index(exact) < handler.index(bound) < handler.index(cancel)


def test_report_action_bridges_bind_and_prefer_machine_readable_run_identity() -> None:
    for path in (
        "apps/web/app/AssessmentMarkdownCopyBridge.tsx",
        "apps/web/app/AssessmentReviewPdfDownload.tsx",
    ):
        source = _source(path)
        visible = source[source.index("function visibleRunId") : source.index("function ", source.index("function visibleRunId") + 1)]

        marker = 'container?.getAttribute(RUN_ID_ATTR)'
        query = 'searchParams.get('
        fallback = '.nico-identifier-value code[title]'
        bind = 'container.setAttribute(RUN_ID_ATTR, runId)'
        assert 'const RUN_ID_ATTR = "data-run-id";' in source
        assert marker in visible
        assert query in visible
        assert fallback in visible
        assert bind in source
        assert visible.index(marker) < visible.index(query) < visible.index(fallback)


def test_report_action_run_identity_rejects_non_comprehensive_ids() -> None:
    for path in (
        "apps/web/app/AssessmentMarkdownCopyBridge.tsx",
        "apps/web/app/AssessmentReviewPdfDownload.tsx",
    ):
        source = _source(path)
        validator = source[source.index("function exactRunId") : source.index("function bindRunId")]
        assert 'runId.startsWith("comprun_") ? runId : ""' in validator
