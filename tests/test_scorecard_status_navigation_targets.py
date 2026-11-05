"""Scorecard status cells must not claim dedicated semantic section targets."""
import io

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
from nico.comprehensive_semantic_navigation_v1 import (
    semantic_entry_records, semantic_renumber_and_outline,
)
from nico.v2_report_quality_repairs import _scorecard_page
from nico.v2_localized_report_quality_repairs import _spanish_scorecard_page

IDS = ("architecture_technical_debt", "velocity_complexity")


def _page(lines):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    for index, text in enumerate(lines):
        pdf.drawString(48, 744 - 22 * index, text)
    pdf.showPage()
    pdf.save()
    return PdfReader(io.BytesIO(buffer.getvalue())).pages[0]


@pytest.mark.parametrize("spanish", [False, True])
@pytest.mark.parametrize("status", ["green", "yellow", "red", "gray", "provisional strong", "provisional moderate", "unknown"])
def test_actual_scorecard_cells_do_not_steal_dedicated_section_targets(spanish, status):
    sections = [next(s for s in CANONICAL_TOC_SECTIONS if s["section_id"] == id_) for id_ in IDS]
    titles = [s["title_es" if spanish else "title_en"] for s in sections]
    canonical = {"assessment": {"sections": [
        {"id": id_, "label": section["title_en"], "presented_status": status,
         "score": None if spanish else 96, "summary": "Synthetic retained evidence."}
        for id_, section in zip(IDS, sections)
    ]}}
    scorecard = (_spanish_scorecard_page if spanish else _scorecard_page)(canonical)
    writer = PdfWriter()
    writer.add_page(_page(["NICO Comprehensive | " + ("BORRADOR AUTOMATIZADO" if spanish else "AUTOMATED DRAFT")]))
    for page in PdfReader(io.BytesIO(scorecard)).pages:
        writer.add_page(page)
    assert len(writer.pages) == 2
    for title in titles:
        writer.add_page(_page([title, "SÓLIDO · 96/100" if spanish else "STRONG · 96/100", "Synthetic unique body evidence."]))
    buffer = io.BytesIO()
    writer.write(buffer)
    original = buffer.getvalue()
    reader = PdfReader(io.BytesIO(original))
    entries, language = semantic_entry_records(reader)
    by_id = {item["section_id"]: item for item in entries}
    assert language is spanish
    assert [by_id[id_]["source_page_index"] for id_ in IDS] == [2, 3]

    rendered = semantic_renumber_and_outline(original)
    assert semantic_renumber_and_outline(original) == rendered
    final = PdfReader(io.BytesIO(rendered))
    assert len(final.pages) == 5
    outline = {item.title: final.get_destination_page_number(item) for item in final.outline}
    toc_lines = final.pages[1].extract_text().splitlines()
    for title, index in zip(titles, (3, 4)):
        assert outline[title] == index
        assert toc_lines[toc_lines.index(title) + 1] == str(index + 1)
    for index, page in enumerate(reader.pages):
        final_index = index if index == 0 else index + 1
        text = final.pages[final_index].extract_text()
        assert page.extract_text() in text
        label = f"Página del documento {final_index + 1} de 5" if spanish else f"Document page {final_index + 1} of 5"
        assert text.count(label) == 1


@pytest.mark.parametrize("spanish", [False, True])
def test_compacted_real_section_on_scorecard_page_remains_a_target(spanish):
    title = "Arquitectura y deuda técnica" if spanish else "Architecture & Technical Debt"
    writer = PdfWriter()
    writer.add_page(_page(["BORRADOR AUTOMATIZADO" if spanish else "AUTOMATED DRAFT"]))
    writer.add_page(_page([
        "Cuadro de puntuación técnica" if spanish else "Canonical Technical Scorecard",
        title, "SIN PUNTUACIÓN" if spanish else "Green", "96/100",
        title, "SÓLIDO · 96/100" if spanish else "STRONG · 96/100", "Dedicated evidence.",
    ]))
    entries, _ = semantic_entry_records(writer)
    match = next(item for item in entries if item["section_id"] == IDS[0])
    assert match["source_page_index"] == 1
    assert match["source_line_index"] == 4


@pytest.mark.parametrize("status", ["Green", "Yellow", "Red", "Gray", "Verde", "Amarillo", "Rojo", "Gris", "SIN PUNTUACIÓN", "FUERTE PROVISIONAL", "MODERADO PROVISIONAL", "DESCONOCIDO", "UNKNOWN"])
def test_scorecard_color_and_unscored_cells_are_not_rich_section_statuses(status):
    from nico.comprehensive_semantic_navigation_v1 import _scorecard_table_followup
    assert _scorecard_table_followup(status)
    assert not _scorecard_table_followup(status + " · 96/100")
