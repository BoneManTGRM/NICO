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


def test_report_actions_publish_exact_run_binding() -> None:
    source = _source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    actions = source[source.index("function renderReportActions") : source.index("function renderHero")]

    assert 'data-assessment-report-actions="true"' in actions
    assert 'data-run-id={String(result?.run_id || "")}' in actions
    assert actions.index('data-run-id={String(result?.run_id || "")}') < actions.index("<button")


def test_markdown_bridge_prefers_canonical_run_binding_and_cannot_swallow_early_click() -> None:
    source = _source("apps/web/app/AssessmentMarkdownCopyBridge.tsx")
    resolver = source[source.index("function visibleRunId") : source.index("function markdownHref")]
    handler = source[source.index("async function handleCopyMarkdownClick") :]

    bound = 'actions?.getAttribute("data-run-id")'
    fallback = 'searchParams.get("run_id")'
    assert bound in resolver
    assert fallback in resolver
    assert resolver.index(bound) < resolver.index(fallback)

    ready = 'actions.getAttribute("data-assessment-report-ready") !== "true"'
    exact = "const entry = entryForVisibleRun(actions);"
    cancel = "event.preventDefault();"
    assert ready in handler
    assert exact in handler
    assert cancel in handler
    assert handler.index(ready) < handler.index(exact) < handler.index(cancel)
    assert "if (!entry) return;" in handler[: handler.index(cancel)]


def test_pdf_bridge_prefers_canonical_run_binding_and_cannot_swallow_early_click() -> None:
    source = _source("apps/web/app/AssessmentReviewPdfDownload.tsx")
    resolver = source[source.index("function visibleRunId") : source.index("function exactRunPdfHref")]
    handler = source[source.index("function handleReviewPdfClick") :]

    canonical = 'actions?.getAttribute("data-run-id")'
    fallback = "searchParams.get(RUN_ID_QUERY)"
    assert canonical in resolver
    assert fallback in resolver
    assert resolver.index(canonical) < resolver.index(fallback)

    ready = 'actions.getAttribute("data-assessment-report-ready") !== "true"'
    exact = "const runId = visibleRunId(actions);"
    bound = 'if (!runId.startsWith("comprun_")) return;'
    cancel = "event.preventDefault();"
    assert ready in handler
    assert exact in handler
    assert bound in handler
    assert cancel in handler
    assert handler.index(ready) < handler.index(exact) < handler.index(bound) < handler.index(cancel)


def test_approved_pdf_bypasses_localization_and_verifies_exact_accepted_bytes() -> None:
    workspace = _source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    bridge = _source("apps/web/app/AssessmentReviewPdfDownload.tsx")
    handler = bridge[bridge.index("function handleReviewPdfClick") :]

    assert 'data-assessment-pdf-kind="accepted-edition"' in workspace
    assert 'data-assessment-pdf-kind="localized-draft-pending-approval"' in workspace
    assert "onClick={downloadApprovedPdf}" in workspace
    assert "onClick={downloadPdf}" in workspace
    assert "!exactApprovedPdfAvailable || approvedLocaleMismatch" in workspace
    assert "acceptedPdfIdentity?.reportLanguage !== requestedReportLanguage" in workspace
    assert "copy.newApprovalRequired" in workspace
    assert "observedSha256 !== acceptedPdfSha256" in workspace
    assert 'response.headers.get("x-nico-artifact-sha256")' in workspace
    assert 'response.headers.get("x-nico-accepted-pdf-sha256")' in workspace
    assert "APPROVED-ACCEPTED-EDITION.pdf" in workspace

    kind_guard = (
        'if (button.getAttribute("data-assessment-pdf-kind") !== '
        "REVIEW_PDF_KIND) return;"
    )
    cancel = "event.preventDefault();"
    assert kind_guard in handler
    assert handler.index(kind_guard) < handler.index(cancel)
    assert "approved" not in bridge.split("const REVIEW_PDF_LABEL =", 1)[1].split(
        ";", 1
    )[0]


def test_final_review_bridge_prefers_canonical_run_binding_without_approval_side_effect() -> None:
    source = _source("apps/web/app/AssessmentFinalReviewAction.tsx")
    resolver = source[source.index("function visibleRunId") : source.index("function reportExists")]
    install = source[source.index("function installAction") : source.index("export default function AssessmentFinalReviewAction")]

    assert "actions?.dataset.runId" in resolver
    assert 'get("run_id")' in resolver
    assert resolver.index("actions?.dataset.runId") < resolver.index('get("run_id")')
    assert "const runId = visibleRunId(actions);" in install
    assert "/operations/final-review?" in install
    assert "client_delivery_allowed" not in install
    assert "approved =" not in install


def test_final_review_bridge_cannot_self_trigger_terminal_mutation_loop() -> None:
    source = _source("apps/web/app/AssessmentFinalReviewAction.tsx")
    install = source[source.index("function installAction") : source.index("export default function AssessmentFinalReviewAction")]
    effect = source[source.index("export default function AssessmentFinalReviewAction") :]
    existing = install[install.index("if (existing)") : install.index("const link =")]

    assert 'if (existing.getAttribute("href") !== href)' in existing
    assert "if (existing.textContent !== label)" in existing
    assert 'if (existing.getAttribute("aria-label") !== ariaLabel)' in existing
    assert "let installFrame = 0;" in effect
    assert "if (installFrame) return;" in effect
    assert "new MutationObserver(scheduleInstall)" in effect
    assert '"data-assessment-report-ready"' in effect
    assert "characterData: true" not in effect
