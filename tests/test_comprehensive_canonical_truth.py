from __future__ import annotations

from nico.comprehensive_canonical_truth import (
    canonicalize_comprehensive_payload,
    normalize_truncated_tool_record,
    weighted_technical_score,
)


def payload_fixture() -> dict:
    return {
        "sections": [
            {"id": "code_audit", "score": 82},
            {"id": "dependency_health", "score": 92},
            {"id": "secrets_review", "score": 85},
            {"id": "static_analysis", "score": None},
            {"id": "ci_cd", "score": 80},
            {"id": "architecture_debt", "score": 78},
            {"id": "velocity_complexity", "score": 84},
        ],
        "evidence_coverage": {"percent": 89, "numerator": 89, "denominator": 100},
        "mid_score_transparency": {
            "records": [
                {"presented_score": 82},
                {"presented_score": 90},
                {"presented_score": 81},
                {"presented_score": 70},
                {"presented_score": 76},
                {"presented_score": 74},
                {"presented_score": 80},
            ]
        },
        "technical_score": 75,
        "technical_band": "MODERATE",
        "maturity_signal": {"score": 83, "level": "Strong"},
        "decision_summary": {"technical_score": 75},
        "executive_summary": {"technical_score": "75/100"},
        "stage_results": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "capability": "canonical_scoring",
                "technical_score": 75,
                "technical_band": "MODERATE",
                "maturity_level": "Mid",
                "summary": "Technical score: 75; technical band: MODERATE; maturity level: Mid",
            }
        ],
    }


def test_weighted_score_excludes_unscored_control_instead_of_zeroing_it() -> None:
    assert weighted_technical_score(payload_fixture()) == 83


def test_canonical_truth_reconciles_every_final_score_surface() -> None:
    result = canonicalize_comprehensive_payload(payload_fixture())
    assert result["technical_score"] == 83
    assert result["technical_band"] == "STRONG"
    assert result["maturity_signal"]["score"] == 83
    assert result["maturity_signal"]["level"] == "Strong"
    assert result["decision_summary"]["technical_score"] == 83
    assert result["executive_summary"]["technical_score"] == "83/100"
    assert result["canonical_report_truth"]["score_source"] == "immutable maturity signal"
    assert result["canonical_report_truth"]["evidence_adjusted_score"] == 79
    assert result["canonical_report_truth"]["evidence_coverage_percent"] == 89

    stage = result["stage_results"][0]
    assert stage["technical_score"] == 83
    assert stage["technical_band"] == "STRONG"
    assert stage["maturity_level"] == "Strong"
    assert stage["pre_reconciliation_technical_score"] == 75
    assert "Technical score: 83" in stage["summary"]
    assert "technical band: STRONG" in stage["summary"]


def test_existing_reported_immutable_score_wins_over_weighted_fallback() -> None:
    payload = payload_fixture()
    payload["maturity_signal"] = {"score": 81, "level": "Mid"}
    payload["score_integrity"] = {
        "weights": {
            "code_audit": 20,
            "dependency_health": 15,
            "secrets_review": 10,
            "static_analysis": 15,
            "ci_cd": 15,
            "architecture_debt": 15,
            "velocity_complexity": 10,
        },
        "calculated_score": 82,
        "reported_score": 81,
        "score_match": False,
        "calculated_from_seven_technical_sections": True,
    }
    result = canonicalize_comprehensive_payload(payload)
    assert result["technical_score"] == 81
    assert result["score_integrity"]["calculated_score"] == 82
    assert result["score_integrity"]["reported_score"] == 81
    assert result["score_integrity"]["final_report_score"] == 81
    assert result["canonical_report_truth"]["score_source"] == "reported immutable maturity signal"


def test_canonicalization_is_idempotent() -> None:
    first = canonicalize_comprehensive_payload(payload_fixture())
    second = canonicalize_comprehensive_payload(first)
    assert second["canonical_report_truth"]["technical_score"] == 83
    assert second["stage_results"][0]["pre_reconciliation_technical_score"] == 75


def test_truncated_scanner_output_fails_closed() -> None:
    record = normalize_truncated_tool_record(
        {
            "tool": "bandit",
            "status": "completed",
            "output_truncated": True,
            "verified_for_this_report": True,
            "findings": [{"rule_id": "B101"}],
            "findings_count": 1,
        }
    )
    assert record["status"] == "failed"
    assert record["verified_for_this_report"] is False
    assert record["findings"] == []
    assert record["findings_count"] == 0
    assert record["unverified_truncated_findings_count"] == 1


def test_complete_scanner_output_is_unchanged() -> None:
    source = {
        "tool": "bandit",
        "status": "completed",
        "output_truncated": False,
        "verified_for_this_report": True,
        "findings": [],
        "findings_count": 0,
    }
    assert normalize_truncated_tool_record(source) == source
