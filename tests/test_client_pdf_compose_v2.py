from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf


def _pdf(*pages: list[str]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        y = 740
        for line in lines:
            document.drawString(45, y, line)
            y -= 16
        document.showPage()
    document.save()
    return output.getvalue()


@pytest.mark.parametrize("title,evidence", [("Six-Month Roadmap", "Retained Evidence"),
                                           ("Hoja de ruta de seis meses", "Evidencia conservada")])
def test_companion_does_not_replace_detailed_stage_evidence_or_its_continuations(title, evidence):
    base = _pdf(["NICO COMPREHENSIVE"],
                [title, "Stage ID: six_month_roadmap", evidence, "NICO-WORK-001 retained decision"],
                [title + " — " + evidence, "NICO-WORK-002 retained dependency"],
                [title, "Generic summary replaced by the review companion"])
    result = compose_compact_client_pdf(base, _pdf(["Register"]), _pdf(["Gate"]), review_pdf=_pdf(["Review companion"]))
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(result)).pages)
    assert "NICO-WORK-001 retained decision" in text
    assert "NICO-WORK-002 retained dependency" in text
    assert "Generic summary replaced" not in text


def test_compose_uses_section_headings_not_incidental_appendix_mentions() -> None:
    base = _pdf(
        [
            "NICO COMPREHENSIVE",
            "The package includes a full evidence appendix in structured exports.",
        ],
        ["Executive Decision Brief", "Useful decision content."],
        [
            "P1 · Reduce complexity · NICO-FINDING-DUPLICATE",
            "Exact source",
            "Implementation sequence",
            "Disposition",
        ],
        ["Evidence Appendix", "raw internal material"],
        ["This page is after the appendix and must never be retained."],
    )
    register = _pdf(["Compact Finding and Remediation Register", "Complete Exact-Source Index"])
    gate = _pdf(["Human Review and Acceptance Gate", "CLIENT DELIVERY BLOCKED"])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 4
    assert "full evidence appendix in structured exports" in extracted
    assert "Useful decision content" in extracted
    assert "NICO-FINDING-DUPLICATE" not in extracted
    assert "raw internal material" not in extracted
    assert "after the appendix" not in extracted
    assert "Complete Exact-Source Index" in extracted
    assert "Human Review and Acceptance Gate" in extracted


def test_compose_never_silently_drops_late_primary_semantic_sections() -> None:
    ordinary_pages = [
        [f"Primary evidence section {index}", f"Retained evidence line {index}"]
        for index in range(1, 43)
    ]
    base = _pdf(
        *ordinary_pages,
        ["Evidence Reconciliation and Scoring", "Canonical score reconciliation retained."],
        [
            "Executive Risk Register and Decision Briefing",
            "Executive risk decision evidence retained.",
        ],
    )
    register = _pdf(["Compact Finding and Remediation Register", "Register retained."])
    gate = _pdf(["Human Review and Acceptance Gate", "Gate retained."])

    result = compose_compact_client_pdf(base, register, gate)
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 46
    assert "Evidence Reconciliation and Scoring" in extracted
    assert "Canonical score reconciliation retained." in extracted
    assert "Executive Risk Register and Decision Briefing" in extracted
    assert "Executive risk decision evidence retained." in extracted


def test_footer_only_overflow_is_removed_before_page_budget():
    base = _pdf(*[[f"Primary evidence {i}"] for i in range(58)],
                ["NICO Comprehensive · synthetic · AUTOMATED DRAFT", "Page 59"])
    result = compose_compact_client_pdf(base, _pdf(["Register"]), _pdf(["Gate"]))
    pages = PdfReader(io.BytesIO(result)).pages
    assert len(pages) == 60
    text = "\n".join(page.extract_text() for page in pages)
    assert all(f"Primary evidence {i}" in text for i in range(58))


def test_existing_sparse_reflow_precedes_intermediate_page_budget():
    sparse = [["NICO Comprehensive · synthetic · AUTOMATED DRAFT", f"Sparse section {i}",
               "This retained synthetic evidence is a bounded observation; independent verification remains incomplete."]
              for i in range(2)]
    result = compose_compact_client_pdf(
        _pdf(*[[f"Primary evidence {i}"] for i in range(57)], *sparse),
        _pdf(["Register"]), _pdf(["Gate"]))
    pages = PdfReader(io.BytesIO(result)).pages
    assert len(pages) <= 60
    text = "\n".join(page.extract_text() for page in pages)
    assert all(f"Primary evidence {i}" in text for i in range(57))
    assert all(f"Sparse section {i}" in text for i in range(2))
    assert text.count("independent verification remains incomplete.") == 2


def test_unreflowable_content_still_fails_the_page_budget():
    with pytest.raises(ValueError, match="cannot preserve every"):
        compose_compact_client_pdf(_pdf(*[[f"Primary evidence {i}"] for i in range(59)]),
                                  _pdf(["Register"]), _pdf(["Gate"]))


@pytest.mark.parametrize(
    "heading",
    (
        "CI/CD Operational Readiness and Historical Health",
        "Preparación operativa y salud histórica de CI/CD",
    ),
)
def test_compose_keeps_one_authoritative_ci_boundary_body_page(heading: str) -> None:
    base = _pdf(
        ["NICO COMPREHENSIVE"],
        [heading, "Superseded base boundary copy."],
        ["Client Evidence Summary", "Primary report content retained."],
    )
    ci_boundary = _pdf([heading, "Authoritative boundary copy."])
    register = _pdf(["Compact Finding and Remediation Register"])
    gate = _pdf(["Human Review and Acceptance Gate"])

    result = compose_compact_client_pdf(
        base,
        register,
        gate,
        ci_boundary_pdf=ci_boundary,
    )
    reader = PdfReader(io.BytesIO(result))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 5
    assert extracted.count(heading) == 1
    assert "Superseded base boundary copy." not in extracted
    assert "Authoritative boundary copy." in extracted
    assert "Primary report content retained." in extracted
