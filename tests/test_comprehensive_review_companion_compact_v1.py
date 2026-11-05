from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v2 import (
    merge_review_companion_markdown,
    review_sections,
)
from nico.comprehensive_client_review_companion_v7 import (
    COMPANION_PAGE_COUNT,
    render_paired_substantive_review_pdf,
)


SECTION_IDS = (
    "functional_qa",
    "platform_parity",
    "historical_trends_and_change_failure",
    "requirements_traceability",
    "stakeholder_and_business_alignment",
    "risk_reduction_and_executive_briefing",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
)


def _canonical() -> dict:
    return {
        "stage_summaries": [
            {
                "stage_id": section_id,
                "status": "review_required",
                "summary": f"Bounded automated summary for {section_id}.",
                "evidence": [f"Retained evidence for {section_id}."],
                "findings": [f"Review observation for {section_id}."],
                "limitations": [f"Human evidence is required for {section_id}."],
            }
            for section_id in SECTION_IDS
        ]
    }


def test_review_companion_pairs_two_complete_sections_per_sheet() -> None:
    canonical = _canonical()
    expected = review_sections(canonical, spanish=False)
    pdf = render_paired_substantive_review_pdf(canonical, spanish=False)
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]

    assert len(expected) == 8
    assert len(reader.pages) == COMPANION_PAGE_COUNT == 4
    for page_number, page in enumerate(pages, start=1):
        pair = expected[(page_number - 1) * 2 : page_number * 2]
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        assert len(pair) == 2
        for section in pair:
            assert section["title"] in page
        assert lines.count("Retained evidence") == 2
        assert lines.count("What cannot be concluded") == 2
        assert lines.count("Reviewer disposition") == 2
        assert lines.count("Decision record") == 2
        assert page.count("CLIENT DELIVERY BLOCKED") == 2
        assert f"Review page {page_number} of 4" in page


def test_companion_markdown_removes_orphan_heading_tokens() -> None:
    result = merge_review_companion_markdown(
        "# NICO\n\n## Roadmap\n\n#\n\n## Delivery Status\nBlocked\n",
        _canonical(),
        spanish=False,
    )

    assert "\n#\n" not in result
    assert "## Comprehensive Client Review" in result
    assert "## Delivery Status" in result


def _review_geometry(page):
    """Measure ink bounds in page coordinates, including fit/scale transforms."""
    from reportlab.pdfbase import pdfmetrics
    drawn = []
    pending_rectangles = []

    def point(x, y, matrix):
        return (x * matrix[0] + y * matrix[2] + matrix[4],
                x * matrix[1] + y * matrix[3] + matrix[5])

    def bounds(corners):
        return (min(x for x, _ in corners), min(y for _, y in corners),
                max(x for x, _ in corners), max(y for _, y in corners))

    def operand(operator, operands, cm, _tm):
        if operator == b're':
            x, y, width, height = map(float, operands)
            pending_rectangles.append(bounds([point(a, b, cm) for a, b in
                ((x,y),(x+width,y),(x,y+height),(x+width,y+height))]))
        elif operator in (b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*'):
            drawn.extend(('fill', box, '') for box in pending_rectangles)
            pending_rectangles.clear()
        elif operator in (b'n', b'S', b's'):
            pending_rectangles.clear()

    def text(value, cm, tm, font, size):
        font_name = str((font or {}).get('/BaseFont', '/Helvetica')).split('+')[-1].lstrip('/')
        if font_name == 'BitstreamVeraSans-Roman': font_name = 'NICOReviewText'
        if font_name == 'BitstreamVeraSans-Bold': font_name = 'NICOReviewBold'
        ascent, descent = pdfmetrics.getAscentDescent(font_name, size)
        for index, line in enumerate(value.splitlines()):
            if not line.strip(): continue
            width = pdfmetrics.stringWidth(line, font_name, size)
            offset = -index * size * 1.2
            corners = [point(*point(x,y,tm),cm) for x,y in
                       ((0,descent+offset),(width,descent+offset),
                        (0,ascent+offset),(width,ascent+offset))]
            label = ('Reviewer / date / acceptance evidence:' in line or
                     'Revisor / fecha / evidencia:' in line)
            drawn.append(('label' if label else 'text', bounds(corners), line))

    page.extract_text(visitor_operand_before=operand, visitor_text=text)
    return drawn


def _assert_review_labels_clear(reader):
    count = 0
    for page in reader.pages:
        drawn = _review_geometry(page)
        for index, (kind, box, label) in enumerate(drawn):
            if kind != 'label': continue
            count += 1
            for other_index, (other_kind, other, content) in enumerate(drawn):
                if other_index == index: continue
                # A panel painted before its text is a background. Subsequent
                # fills must not cover the label; text must never intersect it.
                if other_kind == 'fill' and other_index < index: continue
                overlap_x = min(box[2],other[2])-max(box[0],other[0])
                overlap_y = min(box[3],other[3])-max(box[1],other[1])
                assert overlap_x <= .1 or overlap_y <= .1, ('review label overlap',label,content,box,other)
    assert count == 8


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('production_layout', [False, True])
def test_review_record_text_is_clear_of_the_following_boundary_background(spanish, production_layout) -> None:
    from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_review_pdf
    render = _render_polished_review_pdf if production_layout else render_paired_substantive_review_pdf
    _assert_review_labels_clear(PdfReader(io.BytesIO(render(_canonical(), spanish=spanish))))


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('production_layout', [False, True])
@pytest.mark.parametrize('occluder', ['text','fill'])
def test_review_geometry_rejects_real_drawn_overlap(spanish,production_layout,occluder):
    from reportlab.pdfgen.canvas import Canvas
    from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_review_pdf
    render = _render_polished_review_pdf if production_layout else render_paired_substantive_review_pdf
    reader=PdfReader(io.BytesIO(render(_canonical(),spanish=spanish)))
    page=next(p for p in reader.pages if any(item[0]=='label' for item in _review_geometry(p)))
    box=next(item[1] for item in _review_geometry(page) if item[0]=='label')
    stream=io.BytesIO();canvas=Canvas(stream,pagesize=(float(page.mediabox.width),float(page.mediabox.height)))
    canvas.translate(box[0],box[1]);canvas.scale(.8,.8)
    if occluder=='fill': canvas.rect(0,0,100,(box[3]-box[1])/.8,fill=1,stroke=0)
    else:
        canvas.setFont('Helvetica',8);canvas.drawString(0,1,'Boundary overlaps reviewer record')
    canvas.save();page.merge_page(PdfReader(io.BytesIO(stream.getvalue())).pages[0])
    with pytest.raises(AssertionError,match='review label overlap'):
        _assert_review_labels_clear(reader)
