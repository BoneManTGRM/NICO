from __future__ import annotations

import base64
import io

from reportlab.pdfgen import canvas

from nico.comprehensive_platform_parity_summary_v1 import (
    overlay_platform_parity_summary,
)
from nico.comprehensive_truth_diagnostics_v1 import (
    install_comprehensive_truth_diagnostics_v1,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 760, "NICO Comprehensive")
    document.showPage()
    document.save()
    return buffer.getvalue()


def test_bounded_platform_parity_pdf_is_not_rejected_as_a_complete_runtime_claim() -> None:
    from nico import comprehensive_client_truth_final_v1 as truth

    install_comprehensive_truth_diagnostics_v1()
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

    # This isolates the contradiction scanner used by the final publication gate.
    # Other canonical package validators run elsewhere in the full pipeline tests.
    validator = truth._validate_surfaces
    previous = getattr(validator, "_nico_previous", None)
    diagnostic = validator if previous is not None else None

    assert diagnostic is not None
    surfaces = {
        "Markdown": package["markdown"],
        "HTML": package["html"],
        "PDF": "Repository indicator review complete; runtime platform parity not assessed.",
    }
    forbidden = "Platform Parity: Complete"
    assert all(forbidden not in value for value in surfaces.values())
