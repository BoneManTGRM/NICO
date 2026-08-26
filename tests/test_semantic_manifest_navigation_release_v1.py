from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _semantic_fixture(*, spanish: bool) -> bytes:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS

    sections = list(CANONICAL_TOC_SECTIONS)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)

    pdf.drawString(
        48,
        744,
        (
            "NICO Comprehensive | BORRADOR AUTOMATIZADO"
            if spanish
            else "NICO Comprehensive | AUTOMATED DRAFT"
        ),
    )
    pdf.showPage()

    # Keep the scorecard heading on its own page so later control names are actual
    # semantic headings rather than scorecard table cells.
    scorecard_id = "canonical_technical_scorecard"
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for section in sections:
        if section["section_id"] == scorecard_id:
            if current:
                chunks.append(current)
                current = []
            chunks.append([section])
            continue
        current.append(section)
        if len(current) == 6:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)

    for chunk in chunks:
        y = 744
        pdf.drawString(
            48,
            y,
            (
                "NICO Comprehensive | BORRADOR AUTOMATIZADO"
                if spanish
                else "NICO Comprehensive | AUTOMATED DRAFT"
            ),
        )
        y -= 28
        for section in chunk:
            title = section["title_es"] if spanish else section["title_en"]
            pdf.drawString(48, y, title)
            y -= 18
            pdf.drawString(
                60,
                y,
                f"semantic proof {section['section_id']}",
            )
            y -= 24
        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _body_without_generated_toc(pdf_bytes: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    # This fixture stays below one TOC page; remove exactly that generated page.
    for page in reader.pages[2:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return PdfReader(io.BytesIO(output.getvalue()))


def _outline_titles(value) -> list[str]:
    output: list[str] = []
    if isinstance(value, list):
        for item in value:
            output.extend(_outline_titles(item))
        return output
    title = getattr(value, "title", None)
    if title:
        output.append(str(title))
    return output


def test_semantic_navigation_uses_canonical_manifest_and_preserves_every_body_section() -> None:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    from nico.comprehensive_semantic_navigation_v1 import (
        semantic_entry_records,
        semantic_renumber_and_outline,
    )

    source = _semantic_fixture(spanish=False)
    source_reader = PdfReader(io.BytesIO(source))
    before, spanish = semantic_entry_records(source_reader)
    assert spanish is False

    expected_ids = {section["section_id"] for section in CANONICAL_TOC_SECTIONS}
    before_ids = {record["section_id"] for record in before}
    assert before_ids == expected_ids

    by_id = {record["section_id"]: record for record in before}
    assert by_id["code_audit"]["source_page_index"] == by_id[
        "dependency_library_ecosystem"
    ]["source_page_index"]
    assert by_id["code_audit"]["source_page_index"] == by_id[
        "secrets_exposure_review"
    ]["source_page_index"]

    output = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(output))
    toc_text = reader.pages[1].extract_text() or ""
    outline_titles = _outline_titles(reader.outline)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    for section in CANONICAL_TOC_SECTIONS:
        title = section["title_en"]
        assert title in toc_text
        assert title in outline_titles
        assert f"semantic proof {section['section_id']}" in full_text

    after_reader = _body_without_generated_toc(output)
    after, after_spanish = semantic_entry_records(after_reader)
    assert after_spanish is False
    assert {record["section_id"] for record in after} == before_ids


def test_semantic_navigation_localizes_all_generated_navigation_for_es_mx() -> None:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    from nico.comprehensive_semantic_navigation_v1 import (
        semantic_entry_records,
        semantic_renumber_and_outline,
    )

    source = _semantic_fixture(spanish=True)
    before, spanish = semantic_entry_records(PdfReader(io.BytesIO(source)))
    assert spanish is True
    assert {record["section_id"] for record in before} == {
        section["section_id"] for section in CANONICAL_TOC_SECTIONS
    }

    output = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(output))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    toc_text = reader.pages[1].extract_text() or ""

    assert "Tabla de contenido" in toc_text
    assert "Table of Contents" not in full_text
    assert "Document page " not in full_text
    for index in range(1, len(reader.pages) + 1):
        assert f"Página del documento {index} de {len(reader.pages)}" in full_text

    for section in CANONICAL_TOC_SECTIONS:
        assert section["title_es"] in toc_text


def test_scorecard_control_cells_do_not_steal_semantic_navigation_targets() -> None:
    from nico.comprehensive_semantic_navigation_v1 import semantic_entry_records

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(48, 744, "NICO Comprehensive | AUTOMATED DRAFT")
    pdf.showPage()

    pdf.drawString(48, 744, "Canonical Technical Scorecard")
    pdf.drawString(48, 710, "Code Audit")
    pdf.drawString(200, 710, "Strong")
    pdf.drawString(48, 690, "Dependency / Library Ecosystem")
    pdf.showPage()

    pdf.drawString(48, 744, "Code Audit")
    pdf.drawString(48, 720, "STRONG · 96/100")
    pdf.drawString(48, 680, "Dependency / Library Ecosystem")
    pdf.drawString(48, 656, "PROVISIONAL STRONG · HUMAN REVIEW REQUIRED")
    pdf.showPage()
    pdf.save()

    records, _spanish = semantic_entry_records(PdfReader(io.BytesIO(buffer.getvalue())))
    by_id = {record["section_id"]: record for record in records}
    assert by_id["code_audit"]["source_page_index"] == 2
    assert by_id["dependency_library_ecosystem"]["source_page_index"] == 2
