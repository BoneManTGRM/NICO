from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_canonical_report_truth_v1 import (
    apply_canonical_score_truth,
    finalize_canonical_report_truth,
)


def _assessment() -> dict:
    scores = [
        ("code_audit", 0.20, 92, "VERIFIED"),
        ("dependency_health", 0.15, 92, "LIMITED · CANDIDATE DISPOSITION"),
        ("secrets_review", 0.15, 93, "LIMITED · CANDIDATE DISPOSITION"),
        ("static_analysis", 0.15, 79, "LIMITED · ANALYZER COVERAGE"),
        ("ci_cd", 0.15, 86, "VERIFIED"),
        ("architecture_debt", 0.15, 78, "VERIFIED"),
        ("velocity_complexity", 0.05, 84, "VERIFIED"),
    ]
    return {
        "repository": "BoneManTGRM/NICO",
        "sections": [
            {"id": section_id, "score_value": score, "assurance_label": assurance}
            for section_id, _weight, score, assurance in scores
        ],
        "scoring_weights": [
            {
                "section_id": section_id,
                "control": section_id,
                "weight": weight,
                "technical_score": score,
                "assurance": assurance,
                "included": True,
            }
            for section_id, weight, score, assurance in scores
        ],
        "findings_register": [
            {
                "priority": "P1",
                "category": "architecture",
                "title": "Complexity hotspot: build_report",
                "evidence": "cyclomatic_complexity=94; verified=True",
                "impact": "Concentrated branch logic increases regression risk.",
            },
            {
                "priority": "P1",
                "category": "evidence",
                "title": "bandit evidence unavailable",
                "evidence": "Analyzer status=failed",
                "impact": "Evidence was unavailable.",
            },
        ],
        "executive_risk_register": [],
    }


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.drawString(40, 700, text)
    page.drawString(40, 680, "87/100")
    page.drawString(40, 660, "85/100")
    page.save()
    return buffer.getvalue()


def test_scores_are_derived_as_87_and_85_from_the_control_evidence() -> None:
    result = apply_canonical_score_truth(_assessment())
    contract = result["canonical_score_contract"]

    assert result["technical_score"] == 87
    assert result["evidence_adjusted_score"] == 85
    assert contract["review_limited_scored_controls"] == 3
    assert contract["evidence_penalty_points"] == 2
    assert "87/100" in result["executive_summary"]
    assert "85/100" in result["executive_summary"]
    assert "Express" not in result["executive_summary"]


def test_complexity_and_evidence_limitations_are_not_misrepresented_as_p1_defects() -> None:
    result = apply_canonical_score_truth(_assessment())
    findings = result["findings_register"]

    assert findings[0]["priority"] == "P2"
    assert findings[1]["priority"] == "P2"
    assert findings[1]["release_blocker"] is True
    assert "not proof of a severe client-system defect" in findings[1]["impact"]


def test_final_report_normalizes_filename_and_blocks_cross_format_score_drift() -> None:
    assessment = apply_canonical_score_truth(_assessment())
    summary = assessment["executive_summary"]
    pdf = _pdf(summary)
    source = {
        "status": "complete",
        "report_package": {
            "markdown": f"# NICO Comprehensive Technical Assessment\n\n{summary}\n\n87/100\n85/100",
            "html": f"<h1>NICO Comprehensive Technical Assessment</h1><p>{summary}</p><p>87/100</p><p>85/100</p>",
            "json": {"assessment": assessment},
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_filename": "report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "report_quality_contract": {},
        },
    }

    result = finalize_canonical_report_truth(source)

    assert result["status"] == "complete"
    assert result["report_package"]["pdf_filename"] == "report-FINAL-PENDING-APPROVAL.pdf"
    invariant = result["report_package"]["report_quality_contract"]["canonical_score_invariant"]
    assert invariant["status"] == "passed"


def test_report_fails_closed_when_one_surface_disagrees() -> None:
    assessment = apply_canonical_score_truth(_assessment())
    source = {
        "status": "complete",
        "report_package": {
            "markdown": "# NICO Comprehensive Technical Assessment\n87/100\n85/100",
            "html": "<p>88/100</p><p>76/100</p>",
            "json": {"assessment": assessment},
            "pdf_base64": base64.b64encode(_pdf("NICO Comprehensive Technical Assessment")).decode("ascii"),
            "pdf_filename": "report-DRAFT.pdf",
            "report_quality_contract": {},
        },
    }

    result = finalize_canonical_report_truth(source)

    assert result["status"] == "blocked"
    assert result["reason"] == "canonical_report_score_invariant_failed"
