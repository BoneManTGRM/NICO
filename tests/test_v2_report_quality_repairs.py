from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.v2_report_quality_repairs import repair_canonical_truth, repair_rendered_report


def _package() -> dict:
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "run_id": "comprun_quality",
            },
            "assessment": {
                "comprehensive_score_truth": {
                    "technical_score": 83,
                    "canonical_evidence_adjusted_score": 88,
                },
                "sections": [
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
                ],
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
                }
            ],
        }
    }


def test_repair_removes_truth_contradictions_without_inventing_scores() -> None:
    repaired = repair_canonical_truth(_package())
    canonical = repaired["json"]
    section = canonical["assessment"]["sections"][0]
    records = {item["scanner_name"]: item for item in canonical["scanner_execution_records"]}

    assert section["presented_status"] == "MODERATE"
    assert section["presented_score"] == 83
    assert section["evidence"] == []
    assert canonical["assessment"]["unavailable_data_notes"] == []
    assert canonical["stage_summaries"][0]["unavailable"] == []
    assert records["bandit"]["verified"] is True
    assert [item["finding_id"] for item in canonical["canonical_findings"]] == ["PROD-1"]
    assert [item["finding_id"] for item in canonical["non_production_observations"]] == ["TEST-ONLY"]


def test_rendered_scorecard_wraps_cells_without_overlapping_words() -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(72, 720, "Canonical Technical Scorecard")
    pdf.drawString(72, 700, "REVIEW_LIMITED_NOT_SCOREDStatic Analysis")
    pdf.showPage()
    pdf.save()

    package = repair_canonical_truth(_package())
    package["pdf_base64"] = base64.b64encode(buffer.getvalue()).decode("ascii")
    repaired = repair_rendered_report(package)
    output = base64.b64decode(repaired["pdf_base64"])
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)

    assert "Canonical Technical Scorecard" in text
    assert "REVIEW_LIMITED_NOT_SCOREDStatic Analysis" not in text
    assert "Moderate" in text
    assert repaired["premium_report_renderer"]["scorecard_word_jumble_removed"] is True
