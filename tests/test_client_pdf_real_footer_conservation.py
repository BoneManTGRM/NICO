"""Owned real-renderer controls, not replay of a production assessment."""
from __future__ import annotations

from copy import deepcopy
import io

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.client_pdf_compose_v2 import compose_compact_client_pdf
from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY
from nico.comprehensive_premium_pdf_v6 import _build_pdf


def _pdf(pages: list[list[str]], footer: str = "", footer_first: bool = True) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        document.setFont("Helvetica", 8)
        if footer and footer_first:
            document.drawString(40, 24, footer)
        for index, line in enumerate(lines):
            document.drawString(40, 740 - index * 16, line)
        if footer and not footer_first:
            document.drawString(40, 24, footer)
        document.showPage()
    document.save()
    return output.getvalue()


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


@pytest.mark.parametrize("locale,boundary", [("en", EN_BOUNDARY), ("es-MX", ES_BOUNDARY)])
def test_real_premium_footer_does_not_keep_a_large_superseded_register(locale, boundary):
    # The actual producer accepts both footer locales; its body is not claimed
    # to be a complete Spanish artifact or a production report.
    identity = {"repository": "owned/pdf-control", "commit_sha": "a" * 40,
                "run_id": "owned-pdf-control", "report_language": locale}
    ids = [f"OWNED-{i:03d}" for i in range(180)]
    assessment = {
        "findings_register": [
            {"priority": "P2", "title": "Superseded owned detail", "finding_id": item,
             "category": "maintainability", "status": "review_required",
             "location": "owned.cpp:1", "fact": "Owned evidence, not a vulnerability.",
             "recommendation": "Review the owned test case."} for item in ids
        ],
        "scope_boundaries": [{"area": "Owned scope", "boundary": "PRIMARY-SCOPE-KEPT"}],
        "human_review_required": True, "client_delivery_allowed": False,
    }
    before = deepcopy(assessment)
    base = _build_pdf(identity, assessment, [], [], [], {}, "2026-09-25T00:00:00Z")
    assert len(PdfReader(io.BytesIO(base)).pages) > 60
    register = _pdf([["Canonical register", *ids[i:i + 30]] for i in range(0, len(ids), 30)])
    result = compose_compact_client_pdf(base, register, _pdf([[boundary]]))
    text = _text(result)
    assert len(PdfReader(io.BytesIO(result)).pages) <= 60
    assert "Superseded owned detail" not in text
    assert "Evidence Appendix" not in text
    assert "PRIMARY-SCOPE-KEPT" in text
    assert "Six-Month Execution Roadmap" in text
    assert all(text.count(item) == 1 for item in ids)
    assert boundary in text
    assert assessment == before
    # Classification must not erase the actual approval footer on retained pages.
    for page in list(PdfReader(io.BytesIO(result)).pages)[:10]:
        assert boundary in (page.extract_text() or "")


@pytest.mark.parametrize("heading,resume,boundary", [
    ("Detailed Findings Register", "Six-Month Execution Roadmap", EN_BOUNDARY),
    ("Registro detallado de hallazgos", "Hoja de ruta de ejecución de seis meses", ES_BOUNDARY),
])
@pytest.mark.parametrize("footer_first", [True, False])
def test_footer_order_preserves_primary_and_mixed_boundary_pages(heading, resume, boundary, footer_first):
    base = _pdf([
        ["Cover"], [heading], ["P2 · Superseded owned detail"],
        ["Location", "owned.cpp:1", resume, "PRIMARY-MIXED-KEPT"],
        ["Unclassified primary section", "PRIMARY-UNKNOWN-KEPT"],
    ], boundary, footer_first)
    result = compose_compact_client_pdf(base, _pdf([["Canonical register"]]), _pdf([[boundary]]))
    text = _text(result)
    assert "Superseded owned detail" not in text
    assert "PRIMARY-MIXED-KEPT" in text and "PRIMARY-UNKNOWN-KEPT" in text
    assert len(PdfReader(io.BytesIO(result)).pages) == 5
    assert boundary in (PdfReader(io.BytesIO(result)).pages[1].extract_text() or "")


@pytest.mark.parametrize("boundary", [EN_BOUNDARY, ES_BOUNDARY])
def test_approval_looking_primary_prose_is_not_treated_as_exact_footer(boundary):
    base = _pdf([["Cover"], [boundary + " is discussed here.", "Detailed Findings Register"],
                 ["P2 · Superseded owned detail"], ["Unclassified section", "PRIMARY-KEPT"]])
    result = compose_compact_client_pdf(base, _pdf([["Canonical register"]]), _pdf([[boundary]]))
    text = _text(result)
    assert boundary + " is discussed here." in text
    assert "PRIMARY-KEPT" in text
    assert "Superseded owned detail" not in text
