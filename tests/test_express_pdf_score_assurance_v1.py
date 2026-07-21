from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.express_pdf_score_assurance_v1 import replace_score_assurance_pages


def _source_pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for title in (
        "Transparent Technical Score",
        "Score Contribution and Constraints",
        "CI/CD and Release Decision Record",
    ):
        document.drawString(72, 720, title)
        document.showPage()
    document.save()
    return buffer.getvalue()


def _result() -> dict:
    return {
        "human_review_required": True,
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 92,
                "presented_score": 92,
                "status": "yellow",
                "confidence": "review-limited",
                "summary": "Current release checks are strong while historical exceptions remain open.",
                "evidence": ["Current release checks passed."],
                "findings": ["Historical workflow reliability includes non-success runs."],
                "unavailable": [],
                "score_rationale": "One retained historical exception remains unresolved.",
            },
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "presented_score": 86,
                "status": "green",
                "confidence": "high",
                "summary": "Code audit evidence is complete.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
        ],
    }


def test_pdf_separates_score_band_from_assurance() -> None:
    result = _result()
    output = replace_score_assurance_pages(_source_pdf(), result)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)

    assert "Technical Score and Evidence Assurance" in text
    assert "EXCEPTIONAL" in text
    assert "92/100" in text
    assert "REVIEW LIMITED" in text
    assert "Technical band" in text
    assert "Assurance" in text
    assert "STRONG" in text
    assert result["express_pdf_score_assurance"]["score_band_coloring"] is True
    assert result["express_pdf_score_assurance"]["assurance_separate"] is True
    assert result["express_pdf_score_assurance_geometry"]["records"][0]["score_tone"] == "green"
    assert result["express_pdf_score_assurance_geometry"]["records"][0]["assurance"] == "REVIEW LIMITED"
