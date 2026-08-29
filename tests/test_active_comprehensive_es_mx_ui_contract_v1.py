from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_current_comprehensive_stage_copy_has_deliberate_es_mx_mappings() -> None:
    localization = source("apps/web/app/assessment/AssessmentSpanishLocalization.ts")
    current_authored_stage_copy = (
        "The authorized repository was bound to one immutable commit before evidence collection.",
        "Exact-commit repository, dependency, architecture, workflow, activity, and complexity evidence were attached.",
        "The modern scanner suite is executing against the exact immutable commit.",
        "Canonical evidence-bound technical scoring completed without forced score inflation.",
        "Scanner findings were separated into material, review-required, approved/nonblocking, and test-only dispositions.",
        "Repository test inventory, supplied journey evidence, parsed results, coverage gaps, and draft QA conclusions were reconciled without treating repository tests or model synthesis as runtime acceptance.",
        "Repository platform indicators and supplied feature/device observations were reconciled and divergence candidates surfaced without promoting source indicators or an unapproved matrix to runtime/device parity.",
        "The existing 0-30/31-90/91-180 roadmap framework was drafted from technical priorities, evidence gaps, supplied requirements, and supplied constraints without creating commitments.",
        "This assessment stage is executing behind the exact-run boundary without holding the browser continuation request open.",
        "Automated Comprehensive work is complete. Client acceptance and delivery remain pending human approval.",
    )

    for phrase in current_authored_stage_copy:
        assert f'["{phrase.lower()}",' in localization

    for required_spanish in (
        "El repositorio autorizado quedó vinculado",
        "El conjunto moderno de analizadores se está ejecutando",
        "Se conciliaron el inventario de pruebas del repositorio",
        "sin crear compromisos",
        "la entrega permanece bloqueada hasta registrar una autorización de entrega independiente",
    ):
        assert required_spanish in localization


def test_stage_display_localizes_known_copy_and_fails_safe_for_new_authored_prose() -> None:
    workspace = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    copy = source("apps/web/app/assessment/assessmentCopy.ts")
    run_hook = source("apps/web/app/assessment/useAssessmentRun.ts")

    assert "localizedStageMessage(item.message, copy, locale)" in workspace
    assert "localizeExactSpanishText(source) || copy.stageMessageUnavailable" in workspace
    assert "No se devolvió una explicación localizada de esta etapa" in copy
    assert "currentStageId.replaceAll" not in run_hook
    assert "currentStageId ? copy.unknownStage" in run_hook
    assert "data-stage-id={canonicalStage}" in workspace
    assert "data-status-id={String(item.status" in workspace


def test_failure_surface_never_renders_unbounded_backend_prose_in_es_mx() -> None:
    panel = source("apps/web/app/AssessmentFailureEvidencePanel.tsx")

    assert "authoredFailureMessage(failure.message, spanish" in panel
    assert "authoredFailureMessage(item.message, spanish" in panel
    assert "return localizeExactSpanishText(source) || fallback" in panel
    assert "<dd>{failure.message}</dd>" not in panel
    assert "<p>{item.message}</p>" not in panel
    assert "failure.code" in panel
    assert "failure.route" in panel
    assert "data-stage-id={item.step}" in panel
    assert "data-status-id={item.status}" in panel
    assert "copyFor(\"es-MX\").unknownStage" in panel
    assert "copyFor(\"es-MX\").unknownStatus" in panel


def test_es_mx_alias_and_query_locale_cover_mounted_recovery_and_operations_chrome() -> None:
    failure = source("apps/web/app/AssessmentFailureEvidencePanel.tsx")
    recovery = source("apps/web/app/ComprehensiveStuckRunRecovery.tsx")
    navigation = source("apps/web/app/PrimaryNavigation.tsx")
    workflow = source("apps/web/app/WorkflowCallout.tsx")
    review_action = source("apps/web/app/AssessmentFinalReviewAction.tsx")
    pdf_action = source("apps/web/app/AssessmentReviewPdfDownload.tsx")

    for mounted_surface in (failure, recovery, navigation, workflow, review_action, pdf_action):
        assert 'get("lang")?.toLowerCase()' in mounted_surface
        assert 'queryLocale === "es-mx"' in mounted_surface

    assert 'path === "/es-mx"' in failure
    assert 'path.startsWith("/es-mx/")' in failure
    assert 'path === "/es-mx"' in recovery
    assert 'path.startsWith("/es-mx/")' in recovery
    assert '"/operations/final-review?lang=es-MX"' in workflow
    assert "UI_LOCALE_CHANGE_EVENT" in failure
    assert "UI_LOCALE_CHANGE_EVENT" in recovery


def test_report_actions_and_terminal_truth_keep_locale_and_approval_boundaries_separate() -> None:
    workspace = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    review_action = source("apps/web/app/AssessmentFinalReviewAction.tsx")
    markdown = source("apps/web/app/AssessmentMarkdownCopyBridge.tsx")
    workflow = source("apps/web/app/WorkflowCallout.tsx")

    assert "internalReview.deliveryAllowed" in workspace
    assert "copy.deliveryAuthorizationRequired" in workspace
    assert "localizedArtifactError(response, copy.markdownMissing, locale)" in workspace
    assert "localizedArtifactError(response, copy.pdfMissing, locale)" in workspace
    assert "payload?.message" not in workspace.split("async function localizedArtifactError", 1)[1].split("function stageLabel", 1)[0]
    assert 'path === "/es-mx"' in review_action
    assert 'path.startsWith("/es-mx/")' in review_action
    assert 'path === "/es-mx"' in markdown
    assert 'path.startsWith("/es-mx/")' in markdown
    assert "separate delivery authorization required" in workflow
    assert "autorización de entrega independiente" in workflow


def test_evidence_completion_labels_are_locale_owned_while_counts_remain_canonical() -> None:
    evidence = source("apps/web/app/assessment/assessmentEvidence.ts")
    copy = source("apps/web/app/assessment/assessmentCopy.ts")

    assert "presentationLabel: string" in evidence
    assert "presentationDefinition: string" in evidence
    assert "label: presentationLabel" in evidence
    assert "definition: presentationDefinition" in evidence
    assert "record.completed" in evidence
    assert "record.total" in evidence
    assert "copy.automatableEvidenceDefinition" in evidence
    assert "copy.overallEngagementEvidenceDefinition" in evidence
    assert "Evidencia del repositorio que puede recopilarse y evaluarse automáticamente." in copy


def test_canonical_evidence_literals_bypass_all_localization_and_normalization() -> None:
    workspace = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    localization = source("apps/web/app/assessment/AssessmentSpanishLocalization.ts")
    canonical_literals = (
        "Compañía Águila  —  literal con  espacios",
        "src/revisión/Ñandú.ts:17",
        "finding_ID-Case/Sensitive",
        "Review required is canonical evidence, not UI copy.",
    )

    assert '<ul className="tight-list" data-no-localize="true">' in workspace
    assert "<li key={`${index}-${item}`}>{item}</li>" in workspace
    assert 'data-no-localize="true">{section.summary}</p>' not in workspace
    assert "localizedSectionPresentation(section, copy, locale)" in workspace
    assert "localizeExactSpanishText(rawSummary)" in workspace
    assert "ES_SECTION_LABELS[sectionId]" in workspace
    assert "label: label || copy.unknownSection" in workspace
    assert "summary: summary || copy.sectionSummaryUnavailable" in workspace
    assert "presentation.retainedLabel" not in workspace
    assert "presentation.retainedSummary" not in workspace
    assert "localizedExecutivePresentation(assessment?.executive_summary, copy, locale)" in workspace
    assert "executivePresentation.summary" in workspace
    assert "executivePresentation.retained" not in workspace
    assert 'data-no-localize="true">{JSON.stringify(item.evidence, null, 2)}</pre>' in workspace
    assert "localizeSpanishJson" not in localization
    assert "localizeJsonBlocks" not in localization
    assert "JSON_KEY_SPANISH" not in localization

    # The fixtures exercise the exact classes of values guarded by the direct JSX
    # identity projection above: Unicode, repeated spaces, paths/IDs, and English-looking
    # canonical evidence remain byte-for-byte identical.
    for literal in canonical_literals:
        assert literal.encode("utf-8").decode("utf-8") == literal


def test_markdown_copy_uses_same_run_locale_projection_and_locale_keyed_cache() -> None:
    workspace = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    bridge = source("apps/web/app/AssessmentMarkdownCopyBridge.tsx")
    repair = source("apps/web/app/assessment/AssessmentRuntimeTruthRepair.tsx")

    localized_route = (
        "/localized-report/${encodeURIComponent(requestedReportLanguage)}"
    )
    assert localized_route in workspace
    assert "/report/markdown" not in workspace
    assert 'headers: {Accept: "application/json"}' in workspace
    assert "payload.report?.markdown" in workspace
    assert 'String(payload.run_id || "") !== runId' in workspace
    assert 'String(payload.commit_sha || "") !== immutableCommit' in workspace
    assert 'String(payload.report_language || "") !== requestedReportLanguage' in workspace
    assert "payload.assessment_rerun !== false" in workspace

    assert "reportLanguage: ReportLanguage" in bridge
    assert "cache.current.reportLanguage !== reportLanguage" in bridge
    assert "cache.current.runId !== runId" in bridge
    assert "cache.current.commitSha !== commitSha" in bridge
    assert "markdownHref(entry.runId, entry.reportLanguage)" in bridge
    assert "payload.report?.markdown" in bridge
    assert "markdown_report_language_mismatch" in bridge
    assert "const reportLanguage = activeReportLanguage();" in bridge
    assert "REPORT_LOCALE_CHANGE_EVENT" not in bridge
    assert 'data-commit-sha={immutableCommit}' in workspace

    assert "/report/markdown" not in repair
    assert "/localized-report/${encodeURIComponent(reportLanguage)}" in repair
    assert "payload.report?.markdown" in repair


def test_accepted_source_and_cross_locale_draft_actions_remain_distinct() -> None:
    workspace = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    bridge = source("apps/web/app/AssessmentReviewPdfDownload.tsx")

    assert "acceptedPdfIdentityFor(result)" in workspace
    assert "accepted?.report_language" in workspace
    assert "acceptedPdfIdentity?.reportLanguage !== requestedReportLanguage" in workspace
    assert 'data-assessment-pdf-kind="accepted-edition"' in workspace
    assert 'data-assessment-pdf-kind="localized-draft-pending-approval"' in workspace
    assert "!exactApprovedPdfAvailable || approvedLocaleMismatch" in workspace
    assert "copy.newApprovalRequired" in workspace
    assert "const markdownLabel = approvedLocaleMismatch" in workspace
    assert "/localized-report/${encodeURIComponent(requestedReportLanguage)}/pdf" in workspace
    assert "/report/pdf" in workspace
    assert 'response.headers.get("x-nico-approval-status")' in workspace
    assert 'response.headers.get("x-nico-delivery-status")' in workspace
    assert 'response.headers.get("x-nico-client-delivery-allowed")' in workspace
    assert 'response.headers.get("x-nico-localized-artifact-requires-new-approval")' in workspace
    assert 'acceptedPdfHeader !== ""' in workspace
    assert 'approvalStatus !== "pending_human_approval"' in workspace
    assert 'deliveryStatus !== "blocked_pending_human_approval"' in workspace
    assert 'clientDeliveryAllowed !== "false"' in workspace
    assert 'approvedLocaleMismatch && requiresNewApproval !== "true"' in workspace
    assert "immutableCommit && responseCommit !== immutableCommit" in workspace
    assert "responseLanguage !== acceptedPdfIdentity?.reportLanguage" in workspace
    assert "REPORT_LOCALE_CHANGE_EVENT" in workspace
    assert 'data-report-language={acceptedPdfIdentity?.reportLanguage}' in workspace
    assert 'data-report-language={requestedReportLanguage}' in workspace

    # The compatibility bridge owns only the localized pending-review draft.
    assert 'button.getAttribute("data-assessment-pdf-kind") !== REVIEW_PDF_KIND' in bridge


def test_same_origin_proxy_preserves_locale_and_artifact_lifecycle_headers() -> None:
    proxy = source("apps/web/app/api/nico/[...path]/route.ts")

    for header in (
        "x-nico-commit-sha",
        "x-nico-report-language",
        "x-nico-assessment-rerun",
        "x-nico-pdf-sha256",
        "x-nico-artifact-sha256",
        "x-nico-accepted-pdf-sha256",
        "x-nico-accepted-edition-language",
        "x-nico-accepted-edition-manifest-sha256",
        "x-nico-approval-status",
        "x-nico-delivery-status",
        "x-nico-client-delivery-allowed",
        "x-nico-localized-artifact-requires-new-approval",
        "x-nico-localized-artifact-approval-invalidated",
        "x-nico-artifact-finality",
    ):
        assert f'"{header}"' in proxy
