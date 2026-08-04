from __future__ import annotations

import io

from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v2 import (
    merge_review_companion_markdown,
    render_comprehensive_review_companion_pdf,
    review_sections,
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


def test_review_companion_uses_one_readable_sheet_per_section() -> None:
    canonical = _canonical()
    expected = review_sections(canonical, spanish=False)
    pdf = render_comprehensive_review_companion_pdf(canonical, spanish=False)
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]

    assert len(expected) == 8
    assert len(reader.pages) == 8
    for section, page in zip(expected, pages, strict=True):
        assert section["title"] in page
        assert "Retained evidence" in page
        assert "Retained limitations" in page
        assert "Reviewer decisions" in page
        assert "Decision record" in page
        assert "CLIENT DELIVERY BLOCKED" in page


def test_companion_markdown_removes_orphan_heading_tokens() -> None:
    result = merge_review_companion_markdown(
        "# NICO\n\n## Roadmap\n\n#\n\n## Delivery Status\nBlocked\n",
        _canonical(),
        spanish=False,
    )

    assert "\n#\n" not in result
    assert "## Comprehensive Client Review" in result
    assert "## Delivery Status" in result
