from __future__ import annotations

import io
import math

import pytest
from pypdf import PdfReader
from pypdf.generic import ContentStream
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_manifest_navigation_v1 as navigation
from nico.comprehensive_four_phase_pdf_v1 import (
    PHASE_BOX_TOP_Y, _overlay, apply_four_phase_pdf, four_phase_target_page_index,
)


def _fixture(titles: list[str], spanish: bool = False) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1)
    pdf.drawString(48, 744, "NICO Comprehensive | BORRADOR AUTOMATIZADO" if spanish else "NICO Comprehensive")
    pdf.showPage()
    for title in titles:
        pdf.drawString(48, 744, title)
        pdf.drawString(48, 700, "Synthetic retained evidence")
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _assert_composed_geometry(navigated: bytes, titles: list[str], spanish: bool) -> bytes:
    canonical = {"identity": {"report_language": "es-MX" if spanish else "en"},
                 "human_review_required": True, "client_delivery_allowed": False}
    rendered = apply_four_phase_pdf(navigated, canonical, spanish=spanish)
    reader = PdfReader(io.BytesIO(rendered))
    target = four_phase_target_page_index(reader, spanish=spanish)
    title_set = set(titles)
    runs = []
    def visitor(text, cm, tm, font, size):
        if text.strip() in title_set:
            runs.append((text.strip(), float(tm[5]), float(size)))
    reader.pages[target].extract_text(visitor_text=visitor)
    assert runs
    overlay = PdfReader(io.BytesIO(_overlay(canonical, spanish, letter)))
    path_tops = []
    for args, op in ContentStream(overlay.pages[0].get_contents(), overlay).operations:
        if op in (b"m", b"l", b"c"):
            path_tops.extend(float(args[i]) for i in range(1, len(args), 2))
        elif op == b"re":
            path_tops.append(float(args[1]) + float(args[3]))
    actual_panel_top = max(path_tops)
    assert actual_panel_top == PHASE_BOX_TOP_Y
    # Conservative full-font extent, not mere extraction order: the opaque panel
    # must not cover the last entry's descenders or its clickable destination row.
    assert all(y - size >= actual_panel_top + 6 for _, y, size in runs)
    toc_count = len(reader.pages) - len(titles) - 1
    texts = [p.extract_text() or "" for p in reader.pages]
    toc_text = "\n".join(texts[1:1 + toc_count])
    for i, title in enumerate(titles, start=1):
        assert title in toc_text
        lines = toc_text.splitlines()
        assert lines[lines.index(title) + 1] == str(i + toc_count + 1)
        assert title in texts[i + toc_count]
    destinations = {x.title: reader.get_destination_page_number(x)
                    for x in reader.outline if not isinstance(x, list)}
    for i, title in enumerate(titles, start=1):
        assert destinations[title] == i + toc_count
    assert reader.page_labels == [str(i + 1) for i in range(len(reader.pages))]
    assert apply_four_phase_pdf(rendered, canonical, spanish=spanish) == rendered
    return rendered


@pytest.mark.parametrize("count", [5, 22, 23, 27, 35])
def test_legacy_contents_reserves_actual_panel_bounds(count) -> None:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    titles = [x["title_en"] for x in list(CANONICAL_TOC_SECTIONS)[:count]]
    source = _fixture(titles)
    navigated = navigation._renumber_and_outline(source)
    assert navigation._renumber_and_outline(source) == navigated
    rendered = _assert_composed_geometry(navigated, titles, False)
    reader = PdfReader(io.BytesIO(rendered))
    # Capacity follows the unchanged 8.2pt text / 18pt pitch and panel geometry.
    capacity = math.floor((690 - 8.2 - PHASE_BOX_TOP_Y - 6) / 18) + 1
    assert len(reader.pages) == count + 1 + math.ceil(count / capacity)


@pytest.mark.parametrize("spanish", [False, True], ids=["en", "es-MX"])
@pytest.mark.parametrize("count", [5, 27, 35])
def test_semantic_contents_keeps_bilingual_geometry_and_offsets(monkeypatch, spanish, count) -> None:
    from nico import comprehensive_semantic_navigation_v1 as semantic
    from nico import comprehensive_pdf_layout_polish_v1 as polish
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    monkeypatch.setattr(semantic, "_toc_pdf", polish._render_polished_toc_pdf)
    monkeypatch.setattr(semantic, "_TOC_ROWS_PER_PAGE", polish._TOC_ROWS_PER_PAGE)
    sections = list(CANONICAL_TOC_SECTIONS)[:count]
    titles = [x["title_es" if spanish else "title_en"] for x in sections]
    source = _fixture(titles, spanish=spanish)
    navigated = semantic.semantic_renumber_and_outline(source)
    assert semantic.semantic_renumber_and_outline(source) == navigated
    _assert_composed_geometry(navigated, titles, spanish)
