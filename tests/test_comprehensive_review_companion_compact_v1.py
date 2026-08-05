from __future__ import annotations

import io

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
        assert len(pair) == 2
        for section in pair:
            assert section["title"] in page
        assert page.count("Retained evidence") == 2
        assert page.count("What cannot be concluded") == 2
        assert page.count("Reviewer disposition") == 2
        assert page.count("Decision record") == 2
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
