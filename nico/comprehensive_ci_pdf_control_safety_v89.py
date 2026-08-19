from __future__ import annotations

import io
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.comprehensive-ci-pdf-control-safety.v89"
_DEL = "\x7f"
_ORIGINAL_BOUNDARY_PDF_PAGE: Callable[..., bytes] | None = None


def _pdf_text(pdf: bytes) -> str:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("CI/CD PDF control safety requires a valid PDF")
    try:
        return "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
        )
    except Exception as exc:
        raise ValueError("CI/CD PDF control safety could not read the PDF") from exc


def _sanitize_text_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        sanitized = original.replace(_DEL, "-")
        if sanitized == original:
            return value, False
        return TextStringObject(sanitized), True

    if isinstance(value, ByteStringObject):
        original = bytes(value)
        sanitized = original.replace(b"\x7f", b"-")
        if sanitized == original:
            return value, False
        return ByteStringObject(sanitized), True

    return value, False


def sanitize_ci_pdf_control_glyphs(pdf: bytes) -> bytes:
    """Replace the production-observed DEL bullet only inside PDF text operands.

    ReportLab's Helvetica path can encode the visible bullet used by the generated
    CI/CD appendix as byte 0x7f. pypdf then extracts that byte as U+007F, which is a
    control character and correctly fails the client-artifact acceptance gate.
    Preserve every other byte and only replace that text-operand DEL marker with an
    ASCII hyphen. Clean PDFs are returned byte-for-byte unchanged.
    """

    if _DEL not in _pdf_text(pdf):
        return pdf

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    changed = False

    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue

        stream = ContentStream(contents, writer)
        page_changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _sanitize_text_operand(operands[0])
                page_changed = page_changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, item in enumerate(operands[0]):
                    operands[0][index], operand_changed = _sanitize_text_operand(item)
                    page_changed = page_changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _sanitize_text_operand(operands[-1])
                page_changed = page_changed or operand_changed

        if page_changed:
            page.replace_contents(stream)
            changed = True

    if not changed:
        raise ValueError("CI/CD PDF contained U+007F but no text operand could be repaired")

    output = io.BytesIO()
    writer.write(output)
    repaired = output.getvalue()
    if _DEL in _pdf_text(repaired):
        raise ValueError("CI/CD PDF retained a U+007F control glyph after repair")
    return repaired


def _boundary_pdf_page_v89(*args: Any, **kwargs: Any) -> bytes:
    original = _ORIGINAL_BOUNDARY_PDF_PAGE
    if original is None:
        raise RuntimeError("CI/CD PDF control-safety boundary is not installed")
    return sanitize_ci_pdf_control_glyphs(original(*args, **kwargs))


def install_comprehensive_ci_pdf_control_safety_v89() -> dict[str, Any]:
    """Bind DEL-glyph sanitation to the exact CI/CD appendix producer."""

    global _ORIGINAL_BOUNDARY_PDF_PAGE

    from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer

    if producer._boundary_pdf_page is not _boundary_pdf_page_v89:
        _ORIGINAL_BOUNDARY_PDF_PAGE = producer._boundary_pdf_page
        producer._boundary_pdf_page = _boundary_pdf_page_v89

    return {
        "status": "installed",
        "version": VERSION,
        "bound": producer._boundary_pdf_page is _boundary_pdf_page_v89,
        "del_control_glyph_sanitized": True,
        "text_operands_only": True,
        "clean_pdf_bytes_unchanged": True,
        "ci_cd_truth_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_ci_pdf_control_safety_v89",
    "sanitize_ci_pdf_control_glyphs",
]
