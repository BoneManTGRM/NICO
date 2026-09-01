from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_canonical_projection_truth_v55 import (
    final_projection_checks,
    normalize_final_projection,
    validate_final_report_package,
)


def _scanner(name: str, *, completed: bool = True) -> dict[str, object]:
    return {
        "scanner_name": name,
        "status": "completed" if completed else "partial",
        "completed": completed,
        "verified": completed,
        "exact_commit_match": True,
        "artifact_hash": f"sha256-{name}" if completed else "",
        "required": True,
    }


def _finding(identifier: str, location: str) -> dict[str, object]:
    return {
        "finding_id": identifier,
        "title": "Reduce complexity in build_report",
        "location": location,
        "symbol": "build_report",
        "rule_id": "complexity_hotspot",
        "category": "architecture",
        "priority": "P1",
        "recommendation": "Split orchestration from rendering.",
    }


def _production_regression_fixture() -> dict[str, object]:
    records = [_scanner("bandit"), _scanner("eslint")]
    findings = [
        _finding("NICO-FINDING-SUMMARY", "nico/report.py:40"),
        _finding("NICO-FINDING-DETAIL", "nico/report.py:40-180:40"),
        {
            "finding_id": "NICO-FINDING-DEPENDENCY",
            "title": "Upgrade affected dependency",
            "category": "dependency",
            "finding_family": "dependency_vulnerability:ghsa-example",
            "priority": "P1",
        },
    ]
    return {
        "identity": {"commit_sha": "a" * 40},
        "scanner_execution_records": deepcopy(records),
        "assessment": {
            "scanner_execution_records": deepcopy(records),
            "sections": [
                {
                    "score_contract": {
                        "incomplete_analyzers": ["bandit"],
                        "analyzer_execution_coverage": 88,
                    }
                }
            ],
            "score_contract": {
                "incomplete_analyzers": ["bandit"],
                "analyzer_execution_coverage": 89,
            },
            "evidence_coverage": {"incomplete_analyzers": ["bandit"]},
            "finding_population": {
                "decision_finding_count": 3,
                "finding_register_count": 3,
                "canonical_finding_count": 3,
                "exact_source_code_finding_count": 2,
                "operational_or_context_finding_count": 1,
            },
        },
        "evidence_health_summary": {
            "incomplete_analyzers": [
                {"scanner": "bandit", "status": "capture_truncated"}
            ]
        },
        "canonical_findings": deepcopy(findings),
        "findings_register": deepcopy(findings),
        "findings": deepcopy(findings),
        "decision_grade_findings_register": deepcopy(findings),
        "executive_risk_register": deepcopy(findings),
        "priority_findings": deepcopy(findings),
        "unique_finding_count": 0,
        "finding_register_count": 3,
        "canonical_finding_count": 3,
        "exact_source_finding_count": 0,
        "operational_finding_count": 0,
        "client_finding_remediation_register": {
            "code_findings": deepcopy(findings[:2]),
            "operational_findings": deepcopy(findings[2:]),
            "summary": {
                "decision_finding_count": 3,
                "finding_register_count": 3,
                "canonical_finding_count": 3,
                "exact_source_code_finding_count": 2,
                "operational_or_context_finding_count": 1,
            },
        },
    }


def test_production_regression_projection_reconciles_four_failed_checks() -> None:
    normalized = normalize_final_projection(_production_regression_fixture())
    checks = final_projection_checks(normalized)

    assert checks["completed_scanners_not_incomplete"] is True
    assert checks["analyzer_coverage_values_consistent"] is True
    assert checks["finding_register_has_no_equivalent_duplicates"] is True
    assert checks["stated_unique_finding_count_matches_register"] is True
    assert checks["expected_analyzer_execution_coverage"] == 100
    assert checks["canonical_finding_count"] == 2
    assert normalized["unique_finding_count"] == 2
    assert normalized["exact_source_finding_count"] == 1
    assert normalized["operational_finding_count"] == 1
    assert normalized["assessment"]["score_contract"]["incomplete_analyzers"] == []
    assert (
        normalized["assessment"]["score_contract"][
            "analyzer_execution_coverage"
        ]
        == 100
    )
    assert len(normalized["findings_register"]) == 2
    aliases = normalized["findings_register"][0]["finding_aliases"]
    assert set(aliases) == {"NICO-FINDING-SUMMARY", "NICO-FINDING-DETAIL"}


def test_projection_is_idempotent() -> None:
    once = normalize_final_projection(_production_regression_fixture())
    twice = normalize_final_projection(once)

    assert twice == once


def test_genuine_incomplete_scanner_remains_visible_and_reduces_coverage() -> None:
    fixture = _production_regression_fixture()
    fixture["scanner_execution_records"][0] = _scanner("bandit", completed=False)
    fixture["assessment"]["scanner_execution_records"][0] = _scanner(
        "bandit", completed=False
    )

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 50
    assert checks["incomplete_scanner_names"] == ["bandit"]
    assert normalized["assessment"]["score_contract"]["incomplete_analyzers"] == [
        "bandit"
    ]
    assert (
        normalized["assessment"]["score_contract"][
            "analyzer_execution_coverage"
        ]
        == 50
    )


def test_explicitly_inapplicable_scanners_do_not_reduce_execution_coverage() -> None:
    fixture = _production_regression_fixture()
    not_applicable = [
        {
            "scanner_name": name,
            "status": "not_applicable",
            "completed": False,
            "applicable": False,
            "reason": "Repository technology does not require this analyzer.",
        }
        for name in ("npm-audit", "eslint", "typescript")
    ]
    applicable = [
        _scanner(name)
        for name in (
            "bandit",
            "pip-audit",
            "osv-scanner",
            "semgrep",
            "trufflehog",
            "gitleaks",
        )
    ]
    expanded_records = deepcopy(applicable + not_applicable)
    fixture["scanner_execution_records"] = deepcopy(expanded_records)
    fixture["not_applicable_scanner_records"] = deepcopy(not_applicable)
    fixture["assessment"]["scanner_execution_records"] = deepcopy(
        expanded_records
    )
    fixture["assessment"]["not_applicable_scanner_records"] = deepcopy(
        not_applicable
    )

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 100
    assert checks["completed_scanner_names"] == sorted(
        item["scanner_name"] for item in applicable
    )
    assert checks["incomplete_scanner_names"] == []
    assert checks["analyzer_coverage_values_consistent"] is True
    assert (
        normalized["assessment"]["score_contract"][
            "analyzer_execution_coverage"
        ]
        == 100
    )


def test_not_applicable_register_is_authoritative_when_retained_record_is_expanded() -> None:
    fixture = _production_regression_fixture()
    expanded = _scanner("npm-audit", completed=False)
    expanded["status"] = "unavailable"
    expanded["applicable"] = True
    fixture["scanner_execution_records"].append(deepcopy(expanded))
    fixture["assessment"]["scanner_execution_records"].append(deepcopy(expanded))
    fixture["not_applicable_scanner_records"] = [
        {"scanner_name": "npm-audit", "status": "not_applicable", "applicable": False}
    ]

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 100
    assert checks["incomplete_scanner_names"] == []


def test_failed_applicable_scanner_still_fails_closed_with_not_applicable_peers() -> None:
    fixture = _production_regression_fixture()
    failed = _scanner("bandit", completed=False)
    fixture["scanner_execution_records"] = [
        failed,
        _scanner("pip-audit"),
        {
            "scanner_name": "npm-audit",
            "status": "not_applicable",
            "completed": False,
            "applicable": False,
        },
    ]
    fixture["assessment"]["scanner_execution_records"] = deepcopy(
        fixture["scanner_execution_records"]
    )

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 50
    assert checks["incomplete_scanner_names"] == ["bandit"]


def _late_projection_applicability_contract() -> dict[str, object]:
    requested = [
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    ]
    not_applicable = ["npm-audit", "eslint", "typescript"]
    applicable = [name for name in requested if name not in not_applicable]
    return {
        "requested_exact_run_scanners": requested,
        "applicable_exact_run_scanners": applicable,
        "not_applicable_exact_run_scanners": not_applicable,
        "authoritative_scanner_record_count": 9,
        "applicable_scanner_record_count": 6,
        "not_applicable_scanner_record_count": 3,
        "coverage_numerator": 6,
        "coverage_denominator": 6,
        "technology_inapplicable_scanners_excluded_from_coverage_denominator": True,
        "not_applicable_scanners_receive_completion_credit": False,
    }


def test_late_expanded_projection_uses_self_consistent_authoritative_applicability() -> None:
    fixture = _production_regression_fixture()
    contract = _late_projection_applicability_contract()
    applicable = set(contract["applicable_exact_run_scanners"])
    fixture["scanner_execution_records"] = [
        _scanner(name, completed=name in applicable)
        for name in contract["requested_exact_run_scanners"]
    ]
    for record in fixture["scanner_execution_records"]:
        if record["scanner_name"] not in applicable:
            record["status"] = "unavailable"
            record.pop("applicable", None)
    fixture["assessment"]["scanner_execution_records"] = deepcopy(
        fixture["scanner_execution_records"]
    )
    fixture.pop("not_applicable_scanner_records", None)
    fixture["assessment"].pop("not_applicable_scanner_records", None)
    fixture["client_readiness_contract"] = contract

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 100
    assert checks["incomplete_scanner_names"] == []
    assert checks["analyzer_coverage_values_consistent"] is True


def test_inconsistent_applicability_contract_is_ignored_fail_closed() -> None:
    fixture = _production_regression_fixture()
    contract = _late_projection_applicability_contract()
    contract["applicable_scanner_record_count"] = 7
    applicable = set(contract["applicable_exact_run_scanners"])
    fixture["scanner_execution_records"] = [
        _scanner(name, completed=name in applicable)
        for name in contract["requested_exact_run_scanners"]
    ]
    fixture["assessment"]["scanner_execution_records"] = deepcopy(
        fixture["scanner_execution_records"]
    )
    fixture["client_readiness_contract"] = contract

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 67
    assert set(checks["incomplete_scanner_names"]) == {
        "eslint",
        "npm-audit",
        "typescript",
    }


def test_valid_applicability_contract_does_not_hide_failed_applicable_scanner() -> None:
    fixture = _production_regression_fixture()
    contract = _late_projection_applicability_contract()
    applicable = set(contract["applicable_exact_run_scanners"])
    fixture["scanner_execution_records"] = [
        _scanner(
            name,
            completed=name in applicable and name != "bandit",
        )
        for name in contract["requested_exact_run_scanners"]
    ]
    fixture["assessment"]["scanner_execution_records"] = deepcopy(
        fixture["scanner_execution_records"]
    )
    fixture["client_readiness_contract"] = contract

    normalized = normalize_final_projection(fixture)
    checks = final_projection_checks(normalized)

    assert checks["expected_analyzer_execution_coverage"] == 83
    assert checks["incomplete_scanner_names"] == ["bandit"]


def test_final_validator_uses_one_canonical_register_not_mirrored_tree_counts() -> None:
    canonical = normalize_final_projection(_production_regression_fixture())

    def delegate(_package: dict[str, object]) -> dict[str, object]:
        return {
            "status": "blocked",
            "checks": {
                "canonical_json_present": True,
                "weighted_scores_recompute": True,
                "completed_scanners_not_incomplete": False,
                "analyzer_coverage_values_consistent": False,
                "finding_register_has_no_equivalent_duplicates": False,
                "stated_unique_finding_count_matches_register": False,
            },
            "failed_checks": [
                "completed_scanners_not_incomplete",
                "analyzer_coverage_values_consistent",
                "finding_register_has_no_equivalent_duplicates",
                "stated_unique_finding_count_matches_register",
            ],
        }

    validation = validate_final_report_package({"json": canonical}, delegate)

    assert validation["status"] == "verified"
    assert validation["failed_checks"] == []
    assert validation["calculated_unique_finding_count"] == 2
    assert validation["client_delivery_allowed"] is False
    assert validation["human_review_required"] is True
