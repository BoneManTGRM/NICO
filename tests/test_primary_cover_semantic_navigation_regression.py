from __future__ import annotations

import base64
import io
import re

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_semantic_navigation_v1 as semantic
from nico.comprehensive_commercial_ship_projection_v3 import (
    _source_pdf_requires_integrity_reprojection,
)
from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_toc_pdf
from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS

_BASE_TOC = semantic._toc_pdf
_COMMIT = "a" * 40
_COVER_ID = "comprehensive_technical_assessment"


def _identified_cover_document(spanish: bool, fault: str | None = None) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(48, 744, "NICO COMPREHENSIVE")
    pdf.drawString(48, 720, "REPOSITORIO EVALUADO" if spanish else "ASSESSED REPOSITORY")
    pdf.drawString(48, 700, "github.com/owner/repository")
    if fault != "missing_commit":
        pdf.drawString(48, 680, _COMMIT)
    pdf.drawString(48, 660, "BORRADOR AUTOMATIZADO" if spanish else "AUTOMATED DRAFT")
    pdf.showPage()
    sections = [
        section for section in CANONICAL_TOC_SECTIONS
        if section["section_id"] != _COVER_ID
        and not (fault == "missing_body_section" and section["section_id"] == "functional_qa")
    ]
    for start in range(0, len(sections), 6):
        y = 744
        for section in sections[start:start + 6]:
            pdf.drawString(48, y, section["title_es"] if spanish else section["title_en"])
            y -= 18
            pdf.drawString(60, y, "Retained evidence: " + section["section_id"])
            y -= 24
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _status(pdf: bytes) -> dict:
    return {
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
        "reports": {
            "json": {"stage_summaries": []},
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        },
    }


@pytest.mark.parametrize("spanish", (False, True))
@pytest.mark.parametrize("polished", (False, True))
def test_identified_primary_cover_keeps_complete_navigation_and_exact_source_guard(
    monkeypatch, spanish: bool, polished: bool,
) -> None:
    # REP-005: this primary cover owns identity after the redundant legacy cover
    # is removed. Both supported TOC renderers and bookmarks must target page 1.
    monkeypatch.setattr(semantic, "_toc_pdf", _render_polished_toc_pdf if polished else _BASE_TOC)
    source = _identified_cover_document(spanish)
    before = PdfReader(io.BytesIO(source))
    records, language = semantic.semantic_entry_records(before)
    assert language is spanish
    assert {record["section_id"] for record in records} == {
        section["section_id"] for section in CANONICAL_TOC_SECTIONS
    }
    cover = next(record for record in records if record["section_id"] == _COVER_ID)
    assert cover["source_page_index"] == 0

    output = semantic.semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(output))
    toc = "\n".join(
        page.extract_text() or "" for page in reader.pages[1:]
        if ("Tabla de contenido" if spanish else "Table of Contents") in (page.extract_text() or "")
    )
    title = CANONICAL_TOC_SECTIONS[0]["title_es" if spanish else "title_en"]
    assert re.search(re.escape(title) + r"\s+1(?:\s|$)", toc)
    destinations = [
        item for item in reader.outline
        if not isinstance(item, list) and getattr(item, "title", None) == title
    ]
    assert len(destinations) == 1
    assert reader.get_destination_page_number(destinations[0]) == 0
    assert _source_pdf_requires_integrity_reprojection(
        _status(output), "es-MX" if spanish else "en",
    ) is False
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert _COMMIT in reader.pages[0].extract_text()
    for section in CANONICAL_TOC_SECTIONS[1:]:
        assert "Retained evidence: " + section["section_id"] in text


@pytest.mark.parametrize("spanish", (False, True))
@pytest.mark.parametrize("fault", ("missing_commit", "missing_body_section"))
def test_primary_cover_navigation_does_not_hide_controlled_incompleteness(
    monkeypatch, spanish: bool, fault: str,
) -> None:
    monkeypatch.setattr(semantic, "_toc_pdf", _BASE_TOC)
    output = semantic.semantic_renumber_and_outline(_identified_cover_document(spanish, fault))
    assert _source_pdf_requires_integrity_reprojection(
        _status(output), "es-MX" if spanish else "en",
    ) is True
