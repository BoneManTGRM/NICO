from __future__ import annotations

from pathlib import Path

from nico.comprehensive_score_truth_v1 import enforce_report_score_truth, reconcile_scoring_result

ROOT = Path(__file__).resolve().parents[1]
PDF_SOURCE = ROOT / "nico" / "comprehensive_premium_pdf_v6.py"


def _package(*, canonical_score: int, stage_score: int, adjusted_score: int | None = None) -> dict:
    adjusted = canonical_score if adjusted_score is None else adjusted_score
    return {
        "status": "complete",
        "assessment": {
            "technical_score": canonical_score,
            "evidence_adjusted_score": adjusted,
            "maturity_signal": {
                "score": canonical_score,
                "technical_score": canonical_score,
                "presented_score": adjusted,
                "evidence_adjusted_score": adjusted,
            },
        },
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "evidence": [f"technical_score: {stage_score}"],
            },
            {
                "stage_id": "risk_reduction_and_executive_briefing",
                "evidence": [f"technical_score: {stage_score}"],
            },
        ],
        "report_quality_contract": {},
        "report_package": {
            "report_quality_contract": {},
            "client_delivery_allowed": False,
        },
        "client_delivery_allowed": False,
    }


def test_report_blocks_when_appendix_score_disagrees_with_canonical_score() -> None:
    result = enforce_report_score_truth(_package(canonical_score=85, stage_score=75, adjusted_score=81))

    assert result["status"] == "blocked"
    assert result["reason"] == "canonical_technical_score_mismatch"
    assert result["report_quality_contract"]["canonical_score_consistent_across_stages"] is False
    assert result["report_quality_contract"]["canonical_score"] == 85
    assert result["report_quality_contract"]["evidence_adjusted_score"] == 81
    assert result["report_quality_contract"]["stage_reported_scores"] == [75]
    assert result["client_delivery_allowed"] is False


def test_report_uses_technical_score_not_evidence_adjusted_presented_score() -> None:
    result = enforce_report_score_truth(_package(canonical_score=85, stage_score=85, adjusted_score=81))

    assert result["status"] == "complete"
    assert result.get("reason") is None
    assert result["report_quality_contract"]["canonical_score"] == 85
    assert result["report_quality_contract"]["evidence_adjusted_score"] == 81
    assert result["report_quality_contract"]["technical_and_assurance_scores_not_conflated"] is True


def test_complete_reconciled_assessment_is_not_penalized_twice() -> None:
    result = {
        "status": "complete",
        "assessment": {
            "technical_score": 85,
            "evidence_adjusted_score": 81,
            "maturity_signal": {
                "score": 85,
                "technical_score": 85,
                "presented_score": 81,
                "evidence_adjusted_score": 81,
                "score_band_label": "STRONG",
            },
            "scoring_weights": [
                {"section_id": "code_audit", "included": True},
                {"section_id": "static_analysis", "included": False},
            ],
            "comprehensive_express_quality": {"status": "complete"},
        },
    }

    reconciled = reconcile_scoring_result(result)

    assert reconciled["assessment"]["technical_score"] == 85
    assert reconciled["assessment"]["evidence_adjusted_score"] == 81
    assert reconciled["canonical_score_truth"]["technical_score"] == 85
    assert reconciled["canonical_score_truth"]["evidence_adjusted_score"] == 81
    assert reconciled["canonical_score_truth"]["technical_and_assurance_scores_not_conflated"] is True


def test_pdf_tables_use_explicit_white_header_paragraphs() -> None:
    source = PDF_SOURCE.read_text(encoding="utf-8")

    assert '"P6-TableHeader"' in source
    assert "textColor=colors.white" in source
    assert "header_style = ParagraphStyle" in source
    assert "parent=table_header" in source
    assert "header_style if header and row_index == 0 else cell_style" in source
    assert '("TOPPADDING", (0, 0), (-1, 0), 6)' in source
    assert '("BOTTOMPADDING", (0, 0), (-1, 0), 6)' in source
