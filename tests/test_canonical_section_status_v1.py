from __future__ import annotations

from copy import deepcopy

from nico.canonical_section_status_v1 import (
    assessment_semantic_sha256,
    normalize_report_package,
    normalize_scored_sections,
)


def _assessment() -> dict:
    return {
        "technical_score": 79,
        "canonical_evidence_adjusted_score": 79,
        "maturity_signal": {
            "technical_score": 79,
            "presented_score": 79,
            "evidence_adjusted_score": 79,
        },
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "presented_score": 83,
                "presented_status": "REVIEW_LIMITED_NOT_SCORED",
                "status": "review_limited_not_scored",
                "unavailable": ["One supplemental analyzer was review-limited."],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "presented_score": 76,
                "presented_status": "MODERATE",
                "status": "moderate",
                "unavailable": [],
            },
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "status": "completed",
                "completed": True,
                "verified_complete": True,
                "findings": [],
            },
            {
                "scanner_name": "eslint",
                "status": "completed_with_findings",
                "completed": True,
                "verified_complete": True,
                "findings": [{"rule_id": "no-unused-vars"}],
            },
        ],
    }


def test_numeric_review_limited_section_uses_score_band_without_hiding_assurance_limit() -> None:
    result = normalize_scored_sections(_assessment())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert static["presented_score"] == 83
    assert static["score"] == 83
    assert static["presented_status"] == "MODERATE"
    assert static["status"] == "moderate"
    assert static["assurance_status"] == "review_limited"
    assert static["source_assurance_status"] == "review_limited_not_scored"
    assert static["score_status_consistent"] is True


def test_report_package_normalization_updates_canonical_json_contract() -> None:
    result = normalize_report_package({"json": {"assessment": _assessment()}})
    canonical = result["json"]
    static = next(
        item for item in canonical["assessment"]["sections"]
        if item["id"] == "static_analysis"
    )

    assert static["presented_status"] == "MODERATE"
    assert canonical["v2_pipeline_contract"]["scored_sections_never_labeled_not_scored"] is True
    assert canonical["assessment"]["section_status_contract"]["assurance_status_is_separate"] is True


def test_semantic_fingerprint_is_repeatable_and_ignores_run_identity() -> None:
    first = _assessment()
    second = deepcopy(first)
    first["run_id"] = "comprun_first"
    second["run_id"] = "comprun_second"

    first_normalized = normalize_scored_sections(first)
    second_normalized = normalize_scored_sections(second)

    assert assessment_semantic_sha256(first_normalized) == assessment_semantic_sha256(
        second_normalized
    )


def test_semantic_fingerprint_changes_when_score_or_scanner_truth_changes() -> None:
    baseline = normalize_scored_sections(_assessment())
    changed_score = deepcopy(baseline)
    changed_score["sections"][0]["presented_score"] = 82
    changed_score["sections"][0]["score"] = 82
    changed_scanner = deepcopy(baseline)
    changed_scanner["scanner_execution_records"][0]["status"] = "partial"
    changed_scanner["scanner_execution_records"][0]["verified_complete"] = False

    baseline_hash = assessment_semantic_sha256(baseline)
    assert assessment_semantic_sha256(changed_score) != baseline_hash
    assert assessment_semantic_sha256(changed_scanner) != baseline_hash
