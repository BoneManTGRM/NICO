from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_zero_finding_finality_truth_v1 import (
    install_comprehensive_zero_finding_finality_truth_v1,
)

INSTALLATION = install_comprehensive_zero_finding_finality_truth_v1()

from nico.comprehensive_canonical_projection_truth_v55 import (
    final_projection_checks,
    normalize_final_projection,
    validate_final_report_package,
)


def _explicit_zero_finding_canonical() -> dict:
    return normalize_final_projection(
        {
            "service_id": "comprehensive",
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "c" * 40,
                "run_id": "comprun_explicit_zero_findings",
            },
            "scanner_execution_records": [],
            "canonical_findings": [],
            "findings_register": [],
            "findings": [],
            "decision_grade_findings_register": [],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )


def test_zero_finding_finality_installer_is_bound() -> None:
    assert INSTALLATION["bound"] is True
    assert INSTALLATION["explicit_zero_finding_register_supported"] is True
    assert INSTALLATION["missing_register_remains_blocked"] is True
    assert INSTALLATION["stale_nonzero_count_remains_blocked"] is True


def test_explicit_zero_finding_register_passes_count_truth() -> None:
    canonical = _explicit_zero_finding_canonical()
    source = deepcopy(canonical)

    checks = final_projection_checks(canonical)

    assert canonical == source
    assert checks["canonical_finding_count"] == 0
    assert checks["finding_register_has_no_equivalent_duplicates"] is True
    assert checks["stated_unique_finding_count_matches_register"] is True
    assert checks["zero_finding_register_explicit"] is True
    assert checks["zero_finding_count_contract_consistent"] is True
    assert canonical["unique_finding_count"] == 0
    assert canonical["finding_register_count"] == 0
    assert canonical["canonical_finding_count"] == 0


def test_explicit_zero_finding_package_can_reach_verified_truth() -> None:
    canonical = _explicit_zero_finding_canonical()

    def delegate(_package: dict) -> dict:
        return {
            "status": "blocked",
            "checks": {
                "canonical_json_present": True,
                "weighted_scores_recompute": True,
                "completed_scanners_not_incomplete": True,
                "analyzer_coverage_values_consistent": True,
                "finding_register_has_no_equivalent_duplicates": True,
                "stated_unique_finding_count_matches_register": False,
            },
            "failed_checks": ["stated_unique_finding_count_matches_register"],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    validation = validate_final_report_package({"json": canonical}, delegate)

    assert validation["status"] == "verified"
    assert validation["failed_checks"] == []
    assert validation["calculated_unique_finding_count"] == 0
    assert (
        validation["canonical_projection_truth"]
        ["zero_finding_count_contract_consistent"]
        is True
    )
    assert validation["human_review_required"] is True
    assert validation["client_delivery_allowed"] is False


def test_missing_finding_contract_remains_fail_closed() -> None:
    canonical = {
        "unique_finding_count": 0,
        "finding_register_count": 0,
        "canonical_finding_count": 0,
    }

    checks = final_projection_checks(canonical)

    assert checks["canonical_finding_count"] == 0
    assert checks["stated_unique_finding_count_matches_register"] is False
    assert "zero_finding_register_explicit" not in checks


def test_stale_nonzero_alias_on_empty_register_remains_blocked() -> None:
    canonical = _explicit_zero_finding_canonical()
    canonical["assessment"]["finding_population"] = {
        "decision_finding_count": 1,
        "finding_register_count": 0,
        "canonical_finding_count": 0,
    }

    checks = final_projection_checks(canonical)

    assert checks["canonical_finding_count"] == 0
    assert checks["zero_finding_register_explicit"] is True
    assert checks["zero_finding_count_contract_consistent"] is False
    assert checks["stated_unique_finding_count_matches_register"] is False


def test_nonempty_register_semantics_are_unchanged() -> None:
    canonical = normalize_final_projection(
        {
            "canonical_findings": [
                {
                    "finding_id": "NICO-FINDING-ONE",
                    "title": "Review one material condition",
                    "category": "architecture",
                }
            ]
        }
    )

    checks = final_projection_checks(canonical)

    assert checks["canonical_finding_count"] == 1
    assert checks["stated_unique_finding_count_matches_register"] is True
    assert "zero_finding_register_explicit" not in checks
