from __future__ import annotations

from nico.triage_aware_scanner_finding_truth import (
    TRIAGE_AWARE_SCANNER_TRUTH_VERSION,
    apply_triage_aware_scanner_finding_truth,
)


def _section(section_id: str, score: int = 90) -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "green",
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def test_only_material_findings_receive_score_caps() -> None:
    assessment = {
        "sections": [
            _section("code_audit"),
            _section("dependency_health"),
            _section("secrets_review"),
            _section("static_analysis"),
            _section("ci_cd"),
            _section("architecture_debt"),
            _section("velocity_complexity"),
        ],
        "maturity_signal": {"score": 90, "level": "Senior"},
        "scorecard": {},
        "findings": [],
    }
    scanner = {
        "finding_summary": {
            "raw_total": 120,
            "material_total": 1,
            "review_required_total": 19,
            "excluded_test_only_total": 100,
            "by_category": {
                "dependency": {
                    "raw": 4,
                    "material": 1,
                    "review_required": 3,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                },
                "static": {
                    "raw": 115,
                    "material": 0,
                    "review_required": 15,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 100,
                },
                "secret": {
                    "raw": 1,
                    "material": 0,
                    "review_required": 1,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                },
            },
        }
    }

    result = apply_triage_aware_scanner_finding_truth(assessment, scanner)
    sections = {item["id"]: item for item in result["sections"]}

    assert sections["dependency_health"]["score"] == 54
    assert sections["dependency_health"]["status"] == "red"
    assert sections["static_analysis"]["score"] == 90
    assert sections["secrets_review"]["score"] == 90
    assert sections["static_analysis"]["score_evidence_breakdown"]["scanner_excluded_test_only_count"] == 100
    assert sections["static_analysis"]["score_evidence_breakdown"]["raw_finding_count_not_used_as_material"] is True
    assert result["scorecard"]["scanner_finding_truth_version"] == TRIAGE_AWARE_SCANNER_TRUTH_VERSION
    assert result["scorecard"]["scanner_material_finding_count"] == 1
    assert result["scorecard"]["scanner_review_required_count"] == 19
    assert result["scorecard"]["scanner_excluded_test_only_count"] == 100
    assert result["scorecard"]["raw_scanner_counts_used_as_material"] is False
    assert result["maturity_signal"]["score"] < 90


def test_review_only_and_test_only_counts_do_not_force_a_red_section() -> None:
    assessment = {
        "sections": [_section("static_analysis", 88)],
        "maturity_signal": {"score": 88, "level": "Senior"},
        "scorecard": {},
        "findings": [],
    }
    scanner = {
        "finding_summary": {
            "by_category": {
                "static": {
                    "raw": 8000,
                    "material": 0,
                    "review_required": 20,
                    "approved_or_nonblocking": 80,
                    "excluded_test_only": 7900,
                }
            }
        }
    }

    result = apply_triage_aware_scanner_finding_truth(assessment, scanner)
    section = result["sections"][0]

    assert section["score"] == 88
    assert section["status"] == "green"
    assert section["confidence"] == "scanner-review-items-disclosed"
    assert any("not scored as confirmed production defects" in item for item in section["findings"])
