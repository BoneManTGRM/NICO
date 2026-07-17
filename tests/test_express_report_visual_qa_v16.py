from __future__ import annotations

import base64
import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import express_report_dossier_export_v15 as export
from nico.express_report_visual_qa_v16 import assert_bilingual_structure, validate_express_pdf


def _pdf(pages: int, first_page_text: str, repeated_text: str = "Evidence-bound technical assessment page with substantive content.") -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for index in range(pages):
        document.setFont("Helvetica", 10)
        text = first_page_text if index == 0 else f"{repeated_text} Page {index + 1}."
        document.drawString(48, 720, text)
        document.showPage()
    document.save()
    return buffer.getvalue()


def _result(locale: str = "en") -> dict:
    return {
        "locale": locale,
        "human_review_required": True,
        "reports": {"markdown": "# Existing report", "html": "<h1>Existing report</h1>"},
        "sections": [],
        "repair_intelligence": {"candidates": []},
        "express_score_transparency": {
            "records": [
                {
                    "section_id": "code_audit",
                    "status": "yellow",
                    "deductions": [{"reason": "Open evidence", "points": 4}],
                }
            ]
        },
    }


def test_visual_qa_accepts_structurally_valid_english_express_pdf() -> None:
    pdf = _pdf(
        15,
        "Executive Decision Brief Transparent Technical Score Finding Dossier Human review required substantive report content.",
    )
    qa = validate_express_pdf(pdf, _result("en-US"))
    assert qa["status"] == "pass"
    assert qa["page_count"] == 15
    assert qa["client_delivery_allowed"] is False
    assert qa["issues"] == []


def test_visual_qa_accepts_required_spanish_report_labels() -> None:
    pdf = _pdf(
        15,
        "Evaluación Express de Salud Técnica NICO Expediente del Hallazgo Se requiere revisión humana contenido sustantivo.",
    )
    qa = validate_express_pdf(pdf, _result("es-MX"))
    assert qa["status"] == "pass"
    assert qa["locale"] == "es"


def test_visual_qa_rejects_page_count_blank_pages_and_score_contradictions() -> None:
    result = _result("en")
    result["express_score_transparency"]["records"][0]["status"] = "green"
    pdf = _pdf(21, "Executive Decision Brief Transparent Technical Score Finding Dossier Human review required.", repeated_text="x")
    qa = validate_express_pdf(pdf, result)
    assert qa["status"] == "fail"
    assert any("outside 15-20" in issue for issue in qa["issues"])
    assert any("Score/status contradiction" in issue for issue in qa["issues"])


def test_bilingual_structure_requires_equal_score_and_dossier_counts() -> None:
    english = {
        "express_score_transparency": {"records": [{}, {}]},
        "express_finding_dossier_export": {"dossier_count": 3},
    }
    spanish = {
        "express_score_transparency": {"records": [{}, {}]},
        "express_finding_dossier_export": {"dossier_count": 3},
    }
    assert assert_bilingual_structure(english, spanish)["status"] == "pass"
    spanish["express_finding_dossier_export"]["dossier_count"] = 2
    assert assert_bilingual_structure(english, spanish)["status"] == "fail"


def test_final_dossier_export_records_visual_qa_and_keeps_review_gate_closed(monkeypatch) -> None:
    base_pdf = _pdf(
        15,
        "Executive Decision Brief Transparent Technical Score Finding Dossier Human review required substantive report content.",
    )
    empty_pdf = _pdf(0, "")
    monkeypatch.setattr(export, "_premium_pdf", lambda result: base_pdf)
    monkeypatch.setattr(export, "_dossier_pdf", lambda result: empty_pdf)

    result = _result("en")
    encoded, error = export.build_express_dossier_export(result)

    assert error is None
    assert encoded
    assert base64.b64decode(encoded)
    assert result["express_visual_qa"]["status"] == "pass"
    assert result["reports"]["pdf_quality_status"] == "pass"
    assert result["client_delivery_allowed"] is False
    assert "human review" in result["client_delivery_block_reason"].lower()
