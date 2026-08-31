from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


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


def _review_canonical() -> dict:
    return {
        "stage_summaries": [
            {
                "stage_id": section_id,
                "status": "review_required",
                "summary": (
                    f"Bounded automated summary for {section_id}; retained repository "
                    "evidence does not authorize runtime or client acceptance."
                ),
                "evidence": [
                    f"Retained evidence for {section_id} at the exact assessed commit."
                ],
                "findings": [f"Review observation for {section_id}."],
                "limitations": [f"Human evidence is required for {section_id}."],
            }
            for section_id in SECTION_IDS
        ]
    }


def _semantic_fixture(*, spanish: bool) -> bytes:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS

    sections = list(CANONICAL_TOC_SECTIONS)
    assert len(sections) == 33
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
            pdf.drawString(60, y, f"semantic proof {section['section_id']}")
            y -= 24
        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _page_containing(reader: PdfReader, marker: str) -> int:
    for page_index, page in enumerate(reader.pages):
        if marker in (page.extract_text() or ""):
            return page_index
    return -1


def test_layout_polish_binds_presentation_only_contracts() -> None:
    from nico import comprehensive_client_review_companion_v7 as v7
    from nico import comprehensive_pdf_reflow_v1 as reflow
    from nico import comprehensive_semantic_navigation_v1 as semantic
    from nico.comprehensive_pdf_layout_polish_v1 import (
        install_comprehensive_pdf_layout_polish_v1,
    )

    state = install_comprehensive_pdf_layout_polish_v1()

    assert state["bound"] is True
    assert state["toc_rows_per_page"] == 33
    assert state["toc_single_page_capacity_above_four_phase_matrix"] is True
    assert state["sparse_section_keep_together"] is True
    assert state["review_companion_pages"] == 4
    assert state["review_small_font_size"] >= 6.8
    assert state["canonical_truth_mutated"] is False
    assert semantic._TOC_ROWS_PER_PAGE == 33
    assert getattr(semantic._toc_pdf, "__nico_comprehensive_pdf_layout_polish_v1__") is True
    assert getattr(reflow._render_group, "__nico_comprehensive_pdf_layout_polish_v1__") is True
    assert getattr(
        v7.render_paired_substantive_review_pdf,
        "__nico_comprehensive_pdf_layout_polish_v1__",
    ) is True


@pytest.mark.parametrize("spanish", [False, True])
def test_all_33_toc_entries_share_one_page_above_four_phase_matrix(spanish: bool) -> None:
    from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
    from nico.comprehensive_pdf_layout_polish_v1 import (
        install_comprehensive_pdf_layout_polish_v1,
    )
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline

    install_comprehensive_pdf_layout_polish_v1()
    navigated = semantic_renumber_and_outline(_semantic_fixture(spanish=spanish))
    rendered = apply_four_phase_pdf(
        navigated,
        {
            "identity": {"report_language": "es-MX" if spanish else "en"},
            "assessment_state": "review_required",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        spanish=spanish,
    )
    reader = PdfReader(io.BytesIO(rendered))
    toc_heading = "Tabla de contenido" if spanish else "Table of Contents"
    matrix_heading = (
        "PROGRAMA DE EVALUACIÓN EN CUATRO FASES"
        if spanish
        else "FOUR-PHASE ASSESSMENT PROGRAM"
    )
    final_title = (
        CANONICAL_TOC_SECTIONS[-1]["title_es"]
        if spanish
        else CANONICAL_TOC_SECTIONS[-1]["title_en"]
    )
    toc_pages = [
        page.extract_text() or ""
        for page in reader.pages
        if toc_heading in (page.extract_text() or "")
    ]

    assert len(toc_pages) == 1
    assert matrix_heading in toc_pages[0]
    assert final_title in toc_pages[0]
    assert "TOC 1/2" not in toc_pages[0]
    assert "contenido 1/2" not in toc_pages[0]


def test_sparse_reflow_keeps_velocity_evidence_with_its_heading() -> None:
    from nico import comprehensive_pdf_reflow_v1 as reflow
    from nico.comprehensive_pdf_layout_polish_v1 import (
        install_comprehensive_pdf_layout_polish_v1,
    )

    install_comprehensive_pdf_layout_polish_v1()
    header = "NICO Comprehensive · comprun_layout_fixture · AUTOMATED DRAFT"
    first = "\n".join(
        [header, "Architecture & Technical Debt", "MODERATE · 78/100"]
        + [
            f"Measured architecture evidence remains review-bound. Record {index}."
            for index in range(28)
        ]
    )
    velocity = "\n".join(
        [
            header,
            "Velocity / Complexity",
            "STRONG · 87/100",
            (
                "Sustainable delivery capacity is derived from immutable architecture "
                "maintainability and workflow automation; mutable activity volume is "
                "unscored context."
            ),
            "Evidence",
            "- Architecture and technical-debt score: 78/100.",
            "- Immutable CI configuration score: 100/100.",
            (
                "- The delivery-capacity score is 60% architecture maintainability "
                "and 40% immutable workflow automation."
            ),
            (
                "- Commit, pull-request, merge, job, and deployment counts are retained "
                "as trend context and have no score effect."
            ),
        ]
    )

    assert reflow._ordinary_sparse_stage(first) is True
    assert reflow._ordinary_sparse_stage(velocity) is True
    reader = PdfReader(io.BytesIO(reflow._render_group([first, velocity])))

    title_page = _page_containing(reader, "Velocity / Complexity")
    final_evidence_page = _page_containing(
        reader,
        "Commit, pull-request, merge, job, and deployment counts",
    )
    assert title_page >= 0
    assert final_evidence_page == title_page


def test_review_companion_uses_readable_typography_without_adding_pages() -> None:
    from nico import comprehensive_client_review_companion_v7 as v7
    from nico.comprehensive_pdf_layout_polish_v1 import (
        install_comprehensive_pdf_layout_polish_v1,
    )

    install_comprehensive_pdf_layout_polish_v1()
    pdf = v7.render_paired_substantive_review_pdf(
        _review_canonical(),
        spanish=False,
    )
    reader = PdfReader(io.BytesIO(pdf))
    font_sizes: list[float] = []

    def collect_font_size(text, _cm, _tm, _font_dict, font_size) -> None:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return
        if normalized.startswith("NICO | Comprehensive client review"):
            return
        if normalized.startswith("Review page "):
            return
        font_sizes.append(float(font_size))

    for page in reader.pages:
        page.extract_text(visitor_text=collect_font_size)

    assert len(reader.pages) == 4
    assert font_sizes
    assert min(font_sizes) >= 6.75
    from nico.comprehensive_client_review_companion_v5 import substantive_review_sections

    expected_sections = substantive_review_sections(_review_canonical(), spanish=False)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for section in expected_sections:
        assert section["title"] in full_text
    assert full_text.count("Decision record") == 8
    assert full_text.count("CLIENT DELIVERY BLOCKED") == 8
