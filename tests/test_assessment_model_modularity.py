from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
MODEL = ASSESSMENT / "assessmentModel.ts"
EVIDENCE = ASSESSMENT / "assessmentEvidence.ts"
PROGRESS = ASSESSMENT / "assessmentProgress.ts"
STATUS = ASSESSMENT / "assessmentStatus.ts"
TRANSPORT = ASSESSMENT / "assessmentTransport.ts"
TERMINAL_AUTHORITY = ASSESSMENT / "assessmentTerminalAuthority.ts"


def test_assessment_model_is_a_thin_compatibility_barrel() -> None:
    source = MODEL.read_text(encoding="utf-8")

    assert source.splitlines() == [
        'export * from "./assessmentEvidence";',
        'export {progressPercent} from "./assessmentProgress";',
        'export * from "./assessmentStatus";',
        'export * from "./assessmentTransport";',
        'export {terminal} from "./assessmentTerminalAuthority";',
    ]
    assert "function " not in source
    assert "class " not in source


def test_assessment_evidence_module_preserves_canonical_selection_contracts() -> None:
    source = EVIDENCE.read_text(encoding="utf-8")

    for contract in [
        "browserEvidencePreview",
        "assessmentFor",
        "reportFor",
        "evidenceCompletionFor",
        "internalReviewStateFor",
        "internalReviewHrefFor",
        "progressFor",
        "immutableCommitFor",
        "scannerStatusFor",
    ]:
        assert f"export function {contract}" in source
    assert "final_comprehensive_report_generation" in source
    assert "evidence_reconciliation_and_scoring" in source
    assert "client_delivery_allowed" in source
    assert "default_customer" in source
    assert "default_project" in source


def test_assessment_progress_module_keeps_display_fallback_isolated() -> None:
    source = PROGRESS.read_text(encoding="utf-8")

    assert "export function progressPercent" in source
    assert "COMPREHENSIVE_STAGE_IDS" in source
    assert "canonical_progress_percent" in source
    assert "active_stage_progress_percent" in source
    assert "completed_stages" in source
    assert "fetch(" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_assessment_status_module_preserves_score_and_lifecycle_presentation() -> None:
    source = STATUS.read_text(encoding="utf-8")

    for contract in [
        "scopeId",
        "toneKey",
        "statusClass",
        "scoreTone",
        "scoreClass",
        "compactIdentifier",
        "formatStatus",
        "persistenceStatus",
        "sectionPresentation",
    ]:
        assert f"export function {contract}" in source
    assert "review_limited" in source
    assert "review_required" in source
    assert "durability_verified" in source


def test_assessment_transport_module_preserves_error_and_download_boundaries() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert "export class AssessmentApiError" in source
    assert "TRANSIENT_HTTP_STATUS" in source
    assert "assessment_invalid_json" in source
    assert "assessment_request_failed" in source
    assert "x-request-id" in source
    assert "window.atob" in source
    assert "URL.revokeObjectURL" in source
    assert "application/pdf" in source


def test_assessment_terminal_authority_is_isolated_and_fail_closed() -> None:
    source = TERMINAL_AUTHORITY.read_text(encoding="utf-8")

    assert "export function terminal" in source
    assert "result.terminal !== true" in source
    assert 'return "failed";' in source
    assert 'return "review_required";' in source
    assert 'return "complete";' in source
    assert "client_delivery_allowed" in source
