from __future__ import annotations

import base64
import io

from reportlab.pdfgen import canvas

from nico.comprehensive_platform_parity_summary_v1 import (
    overlay_platform_parity_summary,
)
from nico.comprehensive_truth_diagnostics_v1 import (
    _FORBIDDEN,
    _excerpt,
    _pdf_text,
    _visible_html,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 760, "NICO Comprehensive")
    document.showPage()
    document.save()
    return buffer.getvalue()


def test_bounded_platform_parity_pdf_is_clean_for_the_exact_contradiction_scanner() -> None:
    canonical = {
        "stage_summaries": [
            {
                "stage_id": "platform_parity",
                "status": "complete_repository_evidence_only",
            }
        ]
    }
    pdf = overlay_platform_parity_summary(_pdf(), canonical, spanish=False)
    package = {
        "json": canonical,
        "markdown": (
            "Repository indicator review complete; "
            "runtime platform parity not assessed."
        ),
        "html": (
            "<p>Repository indicator review complete; "
            "runtime platform parity not assessed.</p>"
        ),
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
    }
    surfaces = {
        "Markdown": " ".join(package["markdown"].split()),
        "HTML": _visible_html(package["html"]),
        "PDF": _pdf_text(package),
    }

    assert "Platform Parity: Complete" in _FORBIDDEN
    assert "runtime platform parity not assessed" in surfaces["PDF"]
    for marker in _FORBIDDEN:
        for value in surfaces.values():
            assert _excerpt(value, marker) == ""


def test_contradiction_scanner_still_detects_the_prohibited_runtime_completion_claim() -> None:
    marker = "Platform Parity: Complete"
    rendered = (
        "Platform Parity: Complete (repository evidence only); "
        "human-context validation: Not assessed."
    )

    assert marker in _FORBIDDEN
    assert marker in _excerpt(rendered, marker)
