from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
VERIFIER = ROOT / "nico" / "phase16_client_delivery_verification_v1.py"
INTEGRATION = ROOT / "nico" / "phase9_comprehensive_report_integration_v1.py"


def test_markdown_copy_has_mobile_safari_fallback_and_current_run_fetch() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "navigator.clipboard.writeText(markdown)" in source
    assert "document.execCommand(\"copy\")" in source
    assert "/report/markdown" in source
    assert "encodeURIComponent(runId)" in source
    assert "if (!markdown.trim())" in source


def test_review_required_is_not_presented_as_assessment_failure() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert 'phase === "review_required"' in source
    assert '"Ready for internal review"' in source
    assert '"The automated assessment package is complete and is waiting for internal approval."' in source
    assert 'displayIssue = phase === "review_required" && reportReady ? null : runIssue' in source


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

    assert "semantic duplicate findings remain" in verifier
    assert "repeated acceptance criteria" in verifier
    assert "duplicated approval state" in verifier
    assert "_merge_duplicate_findings" in integration
    assert "_collapse_filename_state" in integration
    assert 'package["canonical_truth_sha256"]' in integration
    assert 'package["findings_csv_base64"]' in integration
