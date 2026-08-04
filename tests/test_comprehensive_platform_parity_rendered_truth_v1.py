from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_platform_parity_summary_v1 import (
    canonical_platform_parity_line,
    canonical_platform_parity_status,
    overlay_platform_parity_summary,
)


FORBIDDEN = "Platform Parity: Complete"
EN_BOUNDED = (
    "Repository indicator review complete; runtime platform parity not assessed."
)
ES_BOUNDED = (
    "Revisión de indicadores del repositorio completa; "
    "paridad de plataforma en ejecución no evaluada."
)


def _canonical(status: str) -> dict:
    return {
        "stage_summaries": [
            {
                "stage_id": "platform_parity",
                "status": status,
                "summary": "Repository indicators retained for bounded review.",
            }
        ]
    }


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 760, "NICO Comprehensive evidence summary")
    document.showPage()
    document.save()
    return buffer.getvalue()


def _text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_repository_indicator_completion_does_not_claim_runtime_platform_parity() -> None:
    canonical = _canonical("complete")

    assert canonical_platform_parity_status(canonical) == "complete_repository_only"
    assert canonical_platform_parity_line(canonical, spanish=False) == EN_BOUNDED
    assert canonical_platform_parity_line(canonical, spanish=True) == ES_BOUNDED
    assert FORBIDDEN not in canonical_platform_parity_line(canonical, spanish=False)
    assert "Paridad de plataforma: Completa" not in canonical_platform_parity_line(
        canonical,
        spanish=True,
    )


def test_unassessed_state_remains_explicitly_bounded() -> None:
    canonical = _canonical("unavailable")
    english = canonical_platform_parity_line(canonical, spanish=False)
    spanish = canonical_platform_parity_line(canonical, spanish=True)

    assert canonical_platform_parity_status(canonical) == "not_assessed"
    assert "runtime platform parity not assessed" in english
    assert "human input required" in english
    assert "paridad de plataforma en ejecución no evaluada" in spanish
    assert "se requiere intervención humana" in spanish
    assert FORBIDDEN not in english


def test_pdf_overlay_retains_bounded_wording_and_page_count() -> None:
    source = _pdf()
    rendered = overlay_platform_parity_summary(
        source,
        _canonical("complete"),
        spanish=False,
    )
    extracted = _text(rendered)

    assert len(PdfReader(io.BytesIO(rendered)).pages) == len(
        PdfReader(io.BytesIO(source)).pages
    )
    assert EN_BOUNDED in extracted
    assert FORBIDDEN not in extracted
    assert "runtime platform parity not assessed" in extracted


def test_pdf_overlay_is_idempotent_for_the_exact_bounded_line() -> None:
    once = overlay_platform_parity_summary(
        _pdf(),
        _canonical("complete"),
        spanish=False,
    )
    twice = overlay_platform_parity_summary(
        once,
        _canonical("complete"),
        spanish=False,
    )

    assert twice == once
    assert _text(twice).count(EN_BOUNDED) == 1
