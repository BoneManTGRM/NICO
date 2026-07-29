from __future__ import annotations

import pytest

from nico.v2_assessment_pipeline import (
    AssessmentState,
    ScannerState,
    assert_cross_format_identity,
    build_canonical_assessment,
    canonical_truth_sha256,
    derive_assessment_state,
    normalize_scanner_result,
)


SHA = "a" * 40


def _finding(identifier: str, criterion: str) -> dict:
    return {
        "finding_id": identifier,
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "fact": "cyclomatic_complexity=52; loc=173; method=typescript_compiler_ast",
        "priority": "P1",
        "status": "open",
        "recommendation": "Decompose the hotspot.",
        "acceptance_criteria": [criterion],
    }


def test_legacy_and_p1_duplicates_become_one_canonical_finding():
    report = {
        "identity": {"commit_sha": SHA},
        "findings_register": [
            _finding("RISK-LEGACY", "Complexity is at most 30. [method: metric_comparison]"),
            _finding("RISK-P1", f"Complexity is at most 30. [target commit: {SHA}]"),
        ],
    }
    canonical = build_canonical_assessment(report)
    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert set(finding["finding_aliases"]) == {"RISK-LEGACY", "RISK-P1"}
    assert len(finding["acceptance_criteria"]) == 1
    assert canonical["findings"] == canonical["findings_register"] == canonical["canonical_findings"]


def test_bandit_exit_one_with_exact_sha_artifact_is_completed_with_findings():
    result = normalize_scanner_result(
        {
            "scanner": "bandit",
            "commit_sha": SHA,
            "status": "failed",
            "exit_code": 1,
            "artifact_hash": "b" * 64,
            "findings": [{"test_id": "B101"}],
            "verified_complete": True,
        },
        SHA,
    )
    assert result.state is ScannerState.COMPLETED_WITH_FINDINGS
    assert result.completed is True
    assert result.verified is True
    assert result.failure_reason == ""


def test_scanner_without_exact_sha_artifact_remains_failed_with_reason():
    result = normalize_scanner_result(
        {"scanner": "bandit", "commit_sha": SHA, "status": "failed", "exit_code": 1},
        SHA,
    )
    assert result.state is ScannerState.FAILED
    assert result.completed is False
    assert result.failure_reason


def test_complete_package_never_maps_to_failed_when_review_is_pending():
    state = derive_assessment_state(
        package_complete=True,
        review_required=True,
        review_approved=False,
        client_delivery_allowed=False,
        fatal_error=False,
    )
    assert state is AssessmentState.REVIEW_REQUIRED


def test_cross_format_truth_mismatch_fails_closed():
    with pytest.raises(ValueError, match="do not share one canonical truth"):
        assert_cross_format_identity(
            canonical_sha256="1",
            markdown_canonical_sha256="1",
            pdf_canonical_sha256="2",
            ui_canonical_sha256="1",
        )


def test_cross_format_truth_accepts_one_hash():
    report = {"identity": {"commit_sha": SHA}, "findings": []}
    digest = canonical_truth_sha256(build_canonical_assessment(report))
    assert_cross_format_identity(
        canonical_sha256=digest,
        markdown_canonical_sha256=digest,
        pdf_canonical_sha256=digest,
        ui_canonical_sha256=digest,
    )
