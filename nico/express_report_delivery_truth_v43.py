from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader, PdfWriter

VERSION = "nico.express_report_delivery_truth.v43"
_MARKER = "_nico_express_report_delivery_truth_v43"


def _overlay(page_width: float, page_height: float) -> bytes:
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height), invariant=1)
    c.setFillColor(colors.HexColor("#fb7185"))
    c.setFont("Helvetica-Bold", 8.4)
    c.drawString(42, 31, "Not approved for client delivery")
    c.save()
    return buffer.getvalue()


def _add_delivery_truth(pdf_bytes: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes

    first = reader.pages[0]
    overlay = PdfReader(
        io.BytesIO(_overlay(float(first.mediabox.width), float(first.mediabox.height)))
    ).pages[0]
    first.merge_page(overlay)

    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_express_report_delivery_truth_v43() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    current = premium._premium_pdf
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "explicit_client_delivery_warning": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def premium_pdf(result: dict[str, Any]) -> bytes:
        pdf_bytes = current(result)
        polished = _add_delivery_truth(pdf_bytes)
        result["express_delivery_truth"] = {
            "status": "complete",
            "version": VERSION,
            "explicit_warning": "Not approved for client delivery",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return polished

    setattr(premium_pdf, _MARKER, True)
    setattr(premium_pdf, "_nico_previous", current)
    for marker in (
        "_nico_express_pdf_renderer_truth_v21",
        "_nico_express_pdf_score_assurance_v1",
        "_nico_express_report_premium_polish_v42_pdf",
    ):
        if getattr(current, marker, False):
            setattr(premium_pdf, marker, True)

    premium._premium_pdf = premium_pdf
    dossier._premium_pdf = premium_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "explicit_client_delivery_warning": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_report_delivery_truth_v43"]
