from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY
from nico.v2_automated_draft_quality_compat_v2 import repair_rendered_report
from nico.v2_report_quality_repairs import repair_canonical_truth


SHA = "a" * 40
RUN_ID = "comprun_quality"


def _package(*, include_sections: bool = True) -> dict:
    sections = (
        [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "review_limited_not_scored",
                "presented_status": "REVIEW_LIMITED_NOT_SCORED",
                "score": 83,
                "presented_score": 83,
                "summary": "Completed analyzer evidence was retained.",
                "evidence": [
                    "bandit: status=failed; exact_commit_match=True",
                    "eslint: status=missing; exact_commit_match=True",
                ],
                "unavailable": [],
            }
        ]
        if include_sections
        else []
    )
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": SHA,
                "run_id": RUN_ID,
            },
            "assessment": {
                "comprehensive_score_truth": {
                    "technical_score": 83,
                    "canonical_evidence_adjusted_score": 88,
                },
                "sections": sections,
                "unavailable_data_notes": [
                    "Full Git history and object store were materialized and verified for Gitleaks and TruffleHog."
                ],
            },
            "scanner_execution_records": [
                {
                    "scanner_name": "bandit",
                    "state": "completed",
                    "completed": True,
                    "exact_commit_match": True,
                    "artifact_hash": "b" * 64,
                    "verified": False,
                },
                {
                    "scanner_name": "eslint",
                    "state": "completed_with_findings",
                    "completed": True,
                    "exact_commit_match": True,
                    "artifact_hash": "c" * 64,
                    "verified": True,
                    "findings": [{"rule_id": "complexity"}],
                },
            ],
            "canonical_findings": [
                {
                    "finding_id": "TEST-ONLY",
                    "title": "Dynamic execution in test fixture",
                    "location": "tests/test_fixture.py:12",
                    "production_scope": False,
                    "technical_score_impact": "none",
                },
                {
                    "finding_id": "PROD-1",
                    "title": "Production hotspot",
                    "location": "nico/app.py:20",
                    "production_scope": True,
                    "technical_score_impact": "material",
                },
            ],
            "stage_summaries": [
                {
                    "stage_id": "deep_scanner_triage",
                    "title": "Deep Scanner Triage",
                    "status": "complete",
                    "summary": "Complete",
                    "unavailable": [
                        "Exact snapshot checkout retained the requested commit and verified full git history for history-aware scanners."
                    ],
                },
                {
                    "stage_id": "decision_report_generation",
                    "title": "Core Decision Report",
                    "status": "complete",
                    "summary": "A stale report contract remained.",
                    "report_contract_status": "blocked",
                    "report_contract_reason": "canonical_score_truth_mismatch",
                },
            ],
        },
        "markdown": "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED\n",
        "html": "<html><body><article><p>DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED</p></article></body></html>",
    }


def _synthetic_pdf(*, scorecard_text: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(72, 740, "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED")
    pdf.drawString(72, 720, RUN_ID)
    pdf.drawString(72, 700, SHA)
    pdf.showPage()
    pdf.drawString(72, 740, "Canonical Technical Scorecard")
    pdf.drawString(72, 720, scorecard_text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_repair_removes_truth_contradictions_without_inventing_scores() -> None:
    repaired = repair_canonical_truth(_package())
    canonical = repaired["json"]
    section = canonical["assessment"]["sections"][0]
    records = {item["scanner_name"]: item for item in canonical["scanner_execution_records"]}
    stages = {item["stage_id"]: item for item in canonical["stage_summaries"]}

    assert section["presented_status"] == "MODERATE"
    assert section["presented_score"] == 83
    assert section["evidence"] == []
    assert canonical["assessment"]["unavailable_data_notes"] == []
    assert stages["deep_scanner_triage"]["unavailable"] == []
    assert stages["decision_report_generation"]["report_contract_status"] == "passed"
    assert stages["decision_report_generation"]["report_contract_reason"] is None
    assert records["bandit"]["verified"] is True
    assert [item["finding_id"] for item in canonical["canonical_findings"]] == ["PROD-1"]
    assert [item["finding_id"] for item in canonical["non_production_observations"]] == ["TEST-ONLY"]


def test_rendered_scorecard_wraps_rows_and_preserves_automated_draft_semantics() -> None:
    package = repair_canonical_truth(_package())
    package["pdf_base64"] = base64.b64encode(
        _synthetic_pdf(scorecard_text="REVIEW_LIMITED_NOT_SCOREDStatic Analysis")
    ).decode("ascii")

    repaired = repair_rendered_report(package)
    output = base64.b64decode(repaired["pdf_base64"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)

    assert "Canonical Technical Scorecard" in text
    assert "REVIEW_LIMITED_NOT_SCOREDStatic Analysis" not in text
    assert "Static Analysis" in text
    assert "Moderate" in text
    assert "83/100" in text
    assert EN_BOUNDARY in text
    assert "FINAL REPORT" not in text.upper()
    assert "AUTOMATED DRAFT" in repaired["markdown"].upper()
    assert "PENDING HUMAN APPROVAL" in repaired["html"].upper()
    assert repaired["report_finality"] == "automated_draft"
    assert repaired["approval_status"] == "pending_human_approval"
    assert repaired["client_delivery_allowed"] is False
    assert repaired["premium_report_renderer"]["scorecard_word_jumble_removed"] is True
    assert repaired["premium_report_renderer"]["scorecard_rows_verified"] is True
    assert repaired["premium_report_renderer"]["automated_draft_is_valid_unapproved_state"] is True


def test_report_with_no_canonical_sections_preserves_original_page() -> None:
    package = repair_canonical_truth(_package(include_sections=False))
    package["pdf_base64"] = base64.b64encode(
        _synthetic_pdf(scorecard_text="Original scorecard evidence retained")
    ).decode("ascii")

    repaired = repair_rendered_report(package)
    output = base64.b64decode(repaired["pdf_base64"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)

    assert "Original scorecard evidence retained" in text
    assert repaired["premium_report_renderer"]["scorecard_word_jumble_removed"] is False
    assert repaired["premium_report_renderer"]["scorecard_replacement_skipped_no_sections"] is True
    assert repaired["premium_report_renderer"]["scorecard_rows_verified"] is False
    assert EN_BOUNDARY in text
    assert "FINAL REPORT" not in text.upper()
    assert repaired["report_finality"] == "automated_draft"
    assert repaired["client_delivery_allowed"] is False
