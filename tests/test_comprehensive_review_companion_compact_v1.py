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


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('production_layout', [False, True])
def test_review_record_text_is_clear_of_the_following_boundary_background(spanish, production_layout) -> None:
    """Check drawn PDF geometry, including the shrink-to-fit transform."""
    from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_review_pdf
    render = _render_polished_review_pdf if production_layout else render_paired_substantive_review_pdf
    pdf = render(_canonical(), spanish=spanish)
    label_count = 0
    for page in PdfReader(io.BytesIO(pdf)).pages:
        drawn = []

        def point(x, y, matrix):
            return (x * matrix[0] + y * matrix[2] + matrix[4],
                    x * matrix[1] + y * matrix[3] + matrix[5])

        def rectangle(operator, operands, cm, _tm):
            if operator == b're':
                x, y, width, height = map(float, operands)
                drawn.append(('rectangle', point(x, y, cm), point(x + width, y + height, cm)))

        def text(value, cm, tm, _font, size):
            if 'Reviewer / date / acceptance evidence:' in value or 'Revisor / fecha / evidencia:' in value:
                drawn.append(('label', point(tm[4], tm[5], cm), float(size) * abs(cm[3])))

        page.extract_text(visitor_operand_before=rectangle, visitor_text=text)
        for index, item in enumerate(drawn):
            if item[0] != 'label':
                continue
            label_count += 1
            following = next(r for r in drawn[index + 1:] if r[0] == 'rectangle')
            # Reserve descender space as well as the baseline. A later filled
            # boundary must not paint over the reviewer/date instruction.
            assert following[2][1] <= item[1][1] - .3 * item[2]
    assert label_count == 8
