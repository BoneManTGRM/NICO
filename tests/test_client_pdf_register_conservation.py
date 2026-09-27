"""Synthetic boundary regressions; these are not production report evidence."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf


LOCALES = (
    ("Detailed Findings Register", "Six-Month Execution Roadmap", "Evidence Appendix"),
    ("Registro detallado de hallazgos", "Hoja de ruta de ejecución de seis meses", "Apéndice de evidencia"),
)


def _pdf(*pages: list[str]) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for lines in pages:
        for index, line in enumerate(lines):
            document.drawString(45, 740 - index * 16, line)
        document.showPage()
    document.save()
    return buffer.getvalue()


def _compose(*pages: list[str]) -> tuple[str, int]:
    pdf = compose_compact_client_pdf(
        _pdf(*pages), _pdf(["Canonical register retained"]),
        _pdf(["Human review pending; delivery blocked"]),
    )
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Canonical register retained" in text
    assert "Human review pending; delivery blocked" in text
    return text, len(reader.pages)


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_unknown_following_section_is_not_consumed(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading], ["P2 · Synthetic finding · SYN-001"],
                       ["Project-specific primary section", "Mandatory content survives"])
    assert "Mandatory content survives" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_unknown_section_before_known_appendix_is_not_consumed(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading], ["P2 · Synthetic finding · SYN-001"],
                       ["Project-specific primary section", "Mandatory content survives"],
                       [appendix, "Raw appendix excluded"])
    assert "Mandatory content survives" in text
    assert "Raw appendix excluded" not in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_heading_prefix_inside_prose_does_not_begin_replacement(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading + " is discussed here, not started.",
                       "Primary explanation survives"], [resume, "Roadmap survives"])
    assert "Primary explanation survives" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_resume_heading_below_legacy_fragment_preserves_whole_shared_page(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading],
                       ["Location", "synthetic.cpp:4", resume, "Mandatory roadmap survives"],
                       [appendix])
    assert "Mandatory roadmap survives" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_register_start_below_primary_content_preserves_shared_page(heading, resume, appendix):
    text, count = _compose(["Cover"], ["Mandatory primary content survives", heading],
                          *[[f"P2 · Synthetic finding · SYN-{i:03d}"] for i in range(75)],
                          [resume, "Mandatory roadmap survives"])
    assert "Mandatory primary content survives" in text
    assert "Mandatory roadmap survives" in text
    assert "SYN-074" not in text
    assert count <= 60


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_primary_section_below_register_start_is_not_discarded(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading, resume, "Mandatory roadmap survives"], [appendix])
    assert "Mandatory roadmap survives" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_unheaded_field_continuation_is_replaced(heading, resume, appendix):
    text, count = _compose(["Cover"], [heading],
                          ["P2 · Synthetic finding · SYN-001"],
                          ["Location", "synthetic.cpp:4", "Superseded field details"],
                          [resume, "Mandatory roadmap survives"])
    assert "Superseded field details" not in text
    assert "Mandatory roadmap survives" in text
    assert count == 4


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_unclassified_content_ends_discard_state(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading],
                       ["Unclassified content must be retained"],
                       ["Location", "Required location outside proven register"],
                       [resume, "Roadmap survives"])
    assert "Unclassified content must be retained" in text
    assert "Required location outside proven register" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_absent_register_keeps_small_report(heading, resume, appendix):
    text, count = _compose(["Cover"], ["Primary content survives"], [resume, "Roadmap survives"])
    assert "Primary content survives" in text
    assert "Roadmap survives" in text
    assert count == 5


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_heading_mentioned_within_finding_sentence_is_not_a_boundary(heading, resume, appendix):
    text, _ = _compose(["Cover"], [heading],
                       ["P2 · Synthetic finding · SYN-001", "See " + resume + " for context."],
                       [resume, "Roadmap survives"])
    assert "SYN-001" not in text
    assert "Roadmap survives" in text


@pytest.mark.parametrize("heading,resume,appendix", LOCALES)
def test_ambiguous_long_tail_cannot_bypass_page_boundary(heading, resume, appendix):
    with pytest.raises(ValueError, match="60-page boundary"):
        _compose(["Cover"], [heading],
                 *[[f"Unclassified primary section {i}", f"Required content {i}"] for i in range(60)])
