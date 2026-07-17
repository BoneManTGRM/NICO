from __future__ import annotations

from pathlib import Path

from nico.mid_report_v5_hardening import harden_mid_report_payload


ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "mid_report_v5_compat.py"
HARDENING = ROOT / "nico" / "mid_report_v5_hardening.py"

WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}
SCORES = {
    "code_audit": 0,
    "dependency_health": 70,
    "secrets_review": 80,
    "static_analysis": 50,
    "ci_cd": 90,
    "architecture_debt": 85,
    "velocity_complexity": 75,
}


def _section(section_id: str) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": SCORES[section_id],
        "truth_status": "Verified with limitations" if SCORES[section_id] < 80 else "Verified",
        "evidence": ["same retained statement", "same retained statement"],
        "findings": ["same retained statement", f"repair {section_id}", f"repair {section_id}"],
        "unavailable": [f"gap {section_id}", f"gap {section_id}"],
        "missing_evidence_sources": [],
        "failed_evidence_tools": [],
        "scope_disclosures": [],
    }


def _payload() -> dict:
    rows = [
        {
            "section_id": section_id,
            "label": section_id.replace("_", " ").title(),
            "score": score,
            "weight": 99,
            "weighted_contribution": 99,
            "truth_status": "Verified",
        }
        for section_id, score in SCORES.items()
    ]
    rows.extend([
        {"section_id": "code_audit", "score": 100, "weight": 0},
        {"section_id": "unknown_control", "score": 100, "weight": 100},
    ])
    return {
        "technical_score": 70,
        "sections": [_section(section_id) for section_id in WEIGHTS],
        "decision_summary": {"technical_score": 70},
        "score_integrity": {
            "calculated_score": 70,
            "reported_score": 70,
            "final_report_score": 70,
            "score_match": False,
            "weighted_rows": rows,
        },
    }


def test_hardening_enforces_exact_fixed_weight_rows_and_preserves_zero() -> None:
    result = harden_mid_report_payload(_payload())
    rows = result["score_integrity"]["weighted_rows"]

    assert len(rows) == 7
    assert [row["section_id"] for row in rows] == list(WEIGHTS)
    assert [row["weight"] for row in rows] == list(WEIGHTS.values())
    assert next(row for row in rows if row["section_id"] == "code_audit")["score"] == 0
    assert result["technical_score"] == 60
    assert result["decision_summary"]["technical_score"] == 60
    assert result["score_integrity"]["final_report_score"] == 60
    assert result["score_integrity"]["canonical_scorecard_complete"] is True
    assert result["score_integrity"]["canonical_weight_total"] == 100
    assert result["score_integrity"]["score_match"] is True
    assert result["score_integrity"]["score_reconciled"] is True


def test_hardening_deduplicates_within_fields_without_erasing_semantic_categories() -> None:
    result = harden_mid_report_payload(_payload())
    code = next(section for section in result["sections"] if section["id"] == "code_audit")

    assert code["evidence"] == ["same retained statement"]
    assert code["findings"] == ["same retained statement", "repair code_audit"]
    assert code["unavailable"] == ["gap code_audit"]
    assert [item["section_id"] for item in result["decision_summary"]["primary_score_constraints"]] == [
        "code_audit",
        "static_analysis",
        "dependency_health",
    ]


def test_incomplete_scorecard_keeps_real_zero_without_claiming_integrity_match() -> None:
    result = harden_mid_report_payload({
        "technical_score": 0,
        "sections": [_section("code_audit")],
        "decision_summary": {"technical_score": 0},
        "score_integrity": {"reported_score": 0, "score_match": False},
    })

    assert result["technical_score"] == 0
    assert result["decision_summary"]["technical_score"] == 0
    assert result["score_integrity"]["final_report_score"] == 0
    assert result["score_integrity"]["canonical_scorecard_complete"] is False
    assert result["score_integrity"]["score_match"] is False


def test_pdf_heading_compatibility_is_stable_not_swapped_per_request() -> None:
    compat = COMPAT.read_text(encoding="utf-8")
    hardening = HARDENING.read_text(encoding="utf-8")

    assert "def pdf_compat" not in compat
    assert "original_paragraph = flowable_module._paragraph" not in compat
    assert "flowable_module._paragraph = paragraph_with_stable_alias" in hardening
    assert "request_time_global_patch_used" in hardening
