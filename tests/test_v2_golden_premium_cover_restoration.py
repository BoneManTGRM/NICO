from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts


def _package() -> dict:
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "run_id": "comprun_golden_visual",
                "evidence_ledger_id": "ledger-golden",
                "customer_id": "customer-golden",
                "project_id": "project-golden",
                "generated_at": "2026-08-04T16:15:00Z",
                "report_language": "en",
            },
            "generated_at": "2026-08-04T16:15:00Z",
            "report_language": "en",
            "assessment": {
                "technical_score": 81,
                "canonical_evidence_adjusted_score": 79,
                "maturity_signal": {"level": "Strong", "score": 81, "presented_score": 81},
                "sections": [],
                "unavailable_data_notes": [],
            },
            "canonical_findings": [
                {
                    "finding_id": "RISK-P1-GOLDEN",
                    "priority": "P1",
                    "category": "architecture",
                    "title": "High-complexity code hotspot",
                    "location": "apps/web/app/operations/page.tsx:177",
                    "business_impact": "Concentrated branch logic increases regression risk.",
                    "recommendation": "Decompose the hotspot into bounded modules.",
                    "status": "open",
                }
            ],
            "scanner_execution_records": [],
            "stage_summaries": [],
            "roadmap": [],
        }
    }


def test_golden_dark_cover_replaces_plain_canonical_score_sheet() -> None:
    result = rebuild_client_artifacts(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    first_page = reader.pages[0].extract_text() or ""

    assert "NICO / EVIDENCE-BOUND ENGINEERING INTELLIGENCE" in first_page
    assert "NICO COMPREHENSIVE" in first_page
    assert "Evidence-Bound Technical Review Package" in first_page
    assert "Decision-Grade Technical Assessment" not in first_page
    assert "TECHNICAL MATURITY" in first_page
    assert "EVIDENCE-ADJUSTED" in first_page
    assert "HUMAN APPROVAL" in first_page
    assert "Pending" in first_page
    assert "REVIEW PACKAGE" in first_page
    assert "Ready" in first_page
    assert "CLIENT-READY" not in first_page
    assert "ASSESSED REPOSITORY" in first_page
    assert "Executive posture" in first_page
    assert "PRIORITY DECISIONS" in first_page
    assert "POWERED BY REPARODYNAMICS" in first_page
    assert "Client delivery remains blocked until explicit approval" in first_page
    assert "Canonical Score Summary" not in first_page
    assert result["premium_report_renderer"]["golden_cover_layout_restored"] is True
    assert result["premium_report_renderer"]["canonical_score_sheet_removed"] is True
