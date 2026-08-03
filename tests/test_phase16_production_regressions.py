from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
RUNTIME_REPAIR = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentRuntimeTruthRepair.tsx"
VERIFIER = ROOT / "nico" / "phase16_client_delivery_verification_v1.py"
INTEGRATION = ROOT / "nico" / "phase9_comprehensive_report_integration_v1.py"


def test_markdown_copy_has_mobile_safari_fallback_and_current_run_fetch() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    repair = RUNTIME_REPAIR.read_text(encoding="utf-8")

    assert "/report/markdown" in workspace
    assert "encodeURIComponent(runId)" in workspace
    assert "if (!markdown.trim())" in workspace
    assert "navigator.clipboard?.writeText" in repair
    assert 'document.execCommand("copy")' in repair
    assert "copyCurrentMarkdown" in repair
    assert "installMarkdownCopyRepair" in repair


def test_review_required_is_not_presented_as_assessment_failure() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    repair = RUNTIME_REPAIR.read_text(encoding="utf-8")

    assert 'phase === "review_required"' in workspace
    assert '"READY FOR INTERNAL REVIEW"' in repair
    assert '"The automated assessment is complete. Internal review is the next required step before delivery."' in repair
    assert "repairReviewWaitingPresentation" in repair


def test_scores_are_read_from_current_assessment_payload_not_ui_literals() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "assessmentRecord?.technical_score" in source
    assert "maturityRecord?.technical_score" in source
    assert "canonical_evidence_adjusted_score" in source
    assert "technicalValue == null" in source
    assert '"83/100"' not in source
    assert '"82/100"' not in source


def test_phase16_blocks_semantic_duplicates_repeated_criteria_and_filename_states() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")
    integration = INTEGRATION.read_text(encoding="utf-8")

    assert "canonical findings contain semantic duplicates" in verifier
    assert "contains repeated acceptance criteria" in verifier
    assert "must contain exactly one automated-draft approval state" in verifier
    assert "repair_client_delivery_package" in integration
    assert 'package["canonical_truth_sha256"]' in integration
    assert 'package["findings_csv_base64"]' in integration
