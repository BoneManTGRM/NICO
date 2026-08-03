from __future__ import annotations

import io
from functools import wraps
from typing import Any, Iterator, Mapping

VERSION = "nico.comprehensive-platform-parity-summary.v1"
_PDF_MARKER = "_nico_platform_parity_pdf_v1"
_CANONICAL_LABEL = "Platform Parity"
_SPANISH_LABEL = "Paridad de plataforma"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _iter_platform_records(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        identity = _normalized(
            value.get("stage_id")
            or value.get("section_id")
            or value.get("id")
            or value.get("label")
            or value.get("name")
            or value.get("title")
        )
        if "platform" in identity and "parity" in identity:
            yield value
        for key, item in value.items():
            key_text = _normalized(key)
            if "platform" in key_text and "parity" in key_text:
                if isinstance(item, Mapping):
                    yield item
                else:
                    yield {"status": item}
            yield from _iter_platform_records(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_platform_records(item)


def canonical_platform_parity_status(canonical: Mapping[str, Any]) -> str:
    """Return conservative client wording without implying human-context review."""

    for record in _iter_platform_records(canonical):
        status = _normalized(
            record.get("status")
            or record.get("state")
            or record.get("stage_status")
            or record.get("completion_status")
        )
        if status.startswith("complete") or status in {
            "passed",
            "ready",
            "available",
            "review-required",
        }:
            return "complete_repository_only"
    return "not_assessed"


def canonical_platform_parity_line(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    status = canonical_platform_parity_status(canonical)
    if spanish:
        if status == "complete_repository_only":
            return (
                f"{_SPANISH_LABEL}: Completo (solo evidencia del repositorio); "
                f"{_CANONICAL_LABEL}: Complete (repository evidence only)"
            )
        return (
            f"{_SPANISH_LABEL}: No evaluada - se requiere intervención humana; "
            f"{_CANONICAL_LABEL}: Not assessed - human input required"
        )
    if status == "complete_repository_only":
        return (
            f"{_CANONICAL_LABEL}: Complete (repository evidence only); "
            "human-context validation: Not assessed - human input required"
        )
    return f"{_CANONICAL_LABEL}: Not assessed - human input required"


def overlay_platform_parity_summary(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Add one truthful line to the existing evidence-summary page without reflow."""

    if not pdf.startswith(b"%PDF"):
        raise ValueError("platform-parity summary requires a valid PDF")

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("platform-parity summary requires at least one PDF page")

    existing = "\n".join(page.extract_text() or "" for page in reader.pages)
    if f"{_CANONICAL_LABEL}:".casefold() in existing.casefold():
        return pdf

    line = canonical_platform_parity_line(canonical, spanish=spanish)
    first = reader.pages[0]
    width = float(first.mediabox.width)
    height = float(first.mediabox.height)
    overlay_buffer = io.BytesIO()
    overlay = canvas.Canvas(
        overlay_buffer,
        pagesize=(width, height),
        invariant=1,
    )
    overlay.setFillColor(colors.white)
    overlay.rect(38, 38, max(1.0, width - 76), 18, stroke=0, fill=1)
    overlay.setFillColor(colors.HexColor("#475569"))
    overlay.setFont("Helvetica", 6.4)
    overlay.drawString(42, 44, line)
    overlay.save()

    overlay_page = PdfReader(io.BytesIO(overlay_buffer.getvalue())).pages[0]
    first.merge_page(overlay_page)

    writer = PdfWriter()
    writer.add_page(first)
    for page in reader.pages[1:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    rendered = output.getvalue()
    rendered_reader = PdfReader(io.BytesIO(rendered))
    if len(rendered_reader.pages) != len(reader.pages):
        raise ValueError("platform-parity summary changed the client PDF page count")
    extracted = "\n".join(page.extract_text() or "" for page in rendered_reader.pages)
    if f"{_CANONICAL_LABEL}:".casefold() not in extracted.casefold():
        raise ValueError("platform-parity summary was not retained in PDF")
    return rendered


def install_comprehensive_platform_parity_summary() -> dict[str, Any]:
    """Bind one evidence-summary renderer across projection and completion aliases."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection

    current_pdf = projection.render_evidence_review_gate_pdf
    if not getattr(current_pdf, _PDF_MARKER, False):

        @wraps(current_pdf)
        def pdf_wrapped(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> bytes:
            rendered = current_pdf(canonical, register, spanish=spanish)
            return overlay_platform_parity_summary(
                rendered,
                canonical,
                spanish=spanish,
            )

        setattr(pdf_wrapped, _PDF_MARKER, True)
        setattr(pdf_wrapped, "_nico_previous", current_pdf)
        projection.render_evidence_review_gate_pdf = pdf_wrapped

    completion.render_evidence_review_gate_pdf = (
        projection.render_evidence_review_gate_pdf
    )
    return {
        "status": "installed",
        "version": VERSION,
        "pdf_bound": getattr(
            projection.render_evidence_review_gate_pdf,
            _PDF_MARKER,
            False,
        ),
        "completion_pdf_alias_bound": (
            completion.render_evidence_review_gate_pdf
            is projection.render_evidence_review_gate_pdf
        ),
        "page_count_unchanged": True,
        "report_layout_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_platform_parity_line",
    "canonical_platform_parity_status",
    "install_comprehensive_platform_parity_summary",
    "overlay_platform_parity_summary",
]
