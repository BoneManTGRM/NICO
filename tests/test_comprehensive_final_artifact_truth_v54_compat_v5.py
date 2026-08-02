from __future__ import annotations

from nico.comprehensive_final_artifact_truth_v54_compat import (
    apply_legacy_projection_validation_compat,
)


def _blocked_result() -> dict[str, object]:
    return {
        "status": "blocked",
        "checks": {
            "canonical_json_present": True,
            "pdf_full_text_available": True,
            "score_aliases_consistent": True,
            "weighted_scores_recompute": False,
            "completed_scanners_not_incomplete": True,
            "analyzer_coverage_values_consistent": True,
            "all_completed_analyzers_report_full_coverage": True,
            "finding_register_has_no_equivalent_duplicates": True,
            "stated_unique_finding_count_matches_register": False,
            "pdf_identifier_integrity": True,
        },
        "failed_checks": [
            "stated_unique_finding_count_matches_register",
            "weighted_scores_recompute",
        ],
    }


def test_minimal_legacy_finality_fixture_does_not_require_new_projection_contract() -> None:
    canonical = {
        "service_id": "comprehensive",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment": {
            "technical_score": 85,
            "canonical_evidence_adjusted_score": 74,
            "evidence_adjusted_score": 74,
        },
    }

    repaired = apply_legacy_projection_validation_compat(_blocked_result(), canonical)

    assert repaired["status"] == "verified"
    assert repaired["failed_checks"] == []
    assert repaired["legacy_projection_contract_absent"] is True
    assert repaired["human_review_required"] is True
    assert repaired["client_delivery_allowed"] is False


def test_strict_projection_package_remains_fail_closed() -> None:
    canonical = {
        "pre_render_truth_reconciliation": True,
        "scanner_execution_records": [],
        "canonical_findings": [],
        "unique_finding_count": 0,
        "assessment": {
            "score_reconciliation": {"rows": []},
        },
    }

    unchanged = apply_legacy_projection_validation_compat(_blocked_result(), canonical)

    assert unchanged["status"] == "blocked"
    assert "weighted_scores_recompute" in unchanged["failed_checks"]
    assert "stated_unique_finding_count_matches_register" in unchanged["failed_checks"]


def test_non_projection_failure_is_never_overridden() -> None:
    result = _blocked_result()
    result["checks"]["pdf_full_text_available"] = False
    result["failed_checks"].append("pdf_full_text_available")
    canonical = {"assessment": {"technical_score": 85}}

    repaired = apply_legacy_projection_validation_compat(result, canonical)

    assert repaired["status"] == "blocked"
    assert repaired["failed_checks"] == ["pdf_full_text_available"]
