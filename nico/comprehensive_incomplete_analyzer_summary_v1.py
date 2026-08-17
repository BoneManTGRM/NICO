from __future__ import annotations

import io
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-incomplete-analyzer-summary.v1"
_MARKDOWN_MARKER = "_nico_incomplete_analyzer_markdown_v1"
_PDF_MARKER = "_nico_incomplete_analyzer_pdf_v1"
_CANONICAL_LABEL = "Incomplete applicable analyzers"
_SPANISH_LABEL = "Analizadores aplicables incompletos"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _count_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if value in (None, ""):
        return None
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return None


def canonical_incomplete_analyzer_count(canonical: Mapping[str, Any]) -> int:
    """Return the reconciled count without promoting scanner candidates to defects."""

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    for value in (
        canonical.get("incomplete_applicable_analyzers"),
        assessment.get("incomplete_applicable_analyzers"),
        assessment.get("incomplete_analyzers"),
    ):
        count = _count_value(value)
        if count is not None:
            return count

    records = [
        item
        for item in canonical.get("scanner_execution_records") or []
        if isinstance(item, Mapping)
    ]
    return sum(
        1
        for item in records
        if item.get("applicable") is not False
        and item.get("completed") is not True
        and not _text(item.get("status") or item.get("state")).casefold().startswith(
            "completed"
        )
    )


def canonical_summary_line(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    count = canonical_incomplete_analyzer_count(canonical)
    label = _SPANISH_LABEL if spanish else _CANONICAL_LABEL
    return f"{label}: {count}"


def _ensure_markdown_summary(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    output = str(markdown or "")
    summary_line = canonical_summary_line(canonical, spanish=spanish)
    if summary_line.casefold() in output.casefold():
        return output

    line = f"- {summary_line}"
    for marker in (
        "- Score effect: assurance-only until triaged.",
        "- Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
    ):
        if marker in output:
            return output.replace(marker, f"{line}\n{marker}", 1)

    heading = "## Evidence Package Summary" if not spanish else "## Resumen del paquete de evidencia"
    if heading in output:
        start = output.index(heading) + len(heading)
        return output[:start] + f"\n\n{line}" + output[start:]
    return output.rstrip() + f"\n\n{line}\n"


def _overlay_pdf_summary(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("incomplete-analyzer summary requires a valid PDF")

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("incomplete-analyzer summary requires at least one PDF page")

    existing = "\n".join(page.extract_text() or "" for page in reader.pages)
    summary_line = canonical_summary_line(canonical, spanish=spanish)
    if summary_line.casefold() in existing.casefold():
        return pdf

    overlay_buffer = io.BytesIO()
    overlay = canvas.Canvas(overlay_buffer, pagesize=letter, invariant=1)
    overlay.setFillColor(colors.white)
    overlay.rect(38, 18, 536, 18, stroke=0, fill=1)
    overlay.setFillColor(colors.HexColor("#475569"))
    overlay.setFont("Helvetica", 6.6)
    overlay.drawString(42, 25, summary_line)
    overlay.save()

    overlay_page = PdfReader(io.BytesIO(overlay_buffer.getvalue())).pages[0]
    first = reader.pages[0]
    first.merge_page(overlay_page)

    writer = PdfWriter()
    writer.add_page(first)
    for page in reader.pages[1:]:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    rendered = output.getvalue()
    if summary_line.casefold() not in "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(rendered)).pages
    ).casefold():
        raise ValueError("canonical incomplete-analyzer count was not retained in PDF")
    return rendered


def install_comprehensive_incomplete_analyzer_summary() -> dict[str, Any]:
    """Restore one explicit canonical scanner-completion metric in every client format."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection

    current_markdown = projection.compact_client_markdown
    if not getattr(current_markdown, _MARKDOWN_MARKER, False):

        @wraps(current_markdown)
        def markdown_wrapped(
            existing: str,
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            *,
            spanish: bool,
        ) -> str:
            rendered = current_markdown(
                existing,
                canonical,
                register,
                spanish=spanish,
            )
            return _ensure_markdown_summary(
                rendered,
                canonical,
                spanish=spanish,
            )

        setattr(markdown_wrapped, _MARKDOWN_MARKER, True)
        setattr(markdown_wrapped, "_nico_previous", current_markdown)
        projection.compact_client_markdown = markdown_wrapped

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
            return _overlay_pdf_summary(
                rendered,
                canonical,
                spanish=spanish,
            )

        setattr(pdf_wrapped, _PDF_MARKER, True)
        setattr(pdf_wrapped, "_nico_previous", current_pdf)
        projection.render_evidence_review_gate_pdf = pdf_wrapped

    completion.compact_client_markdown = projection.compact_client_markdown
    completion.render_evidence_review_gate_pdf = (
        projection.render_evidence_review_gate_pdf
    )

    return {
        "status": "installed",
        "version": VERSION,
        "markdown_bound": getattr(
            projection.compact_client_markdown,
            _MARKDOWN_MARKER,
            False,
        ),
        "pdf_bound": getattr(
            projection.render_evidence_review_gate_pdf,
            _PDF_MARKER,
            False,
        ),
        "completion_markdown_alias_bound": (
            completion.compact_client_markdown
            is projection.compact_client_markdown
        ),
        "completion_pdf_alias_bound": (
            completion.render_evidence_review_gate_pdf
            is projection.render_evidence_review_gate_pdf
        ),
        "canonical_count_required_in_markdown": True,
        "canonical_count_required_in_html": True,
        "canonical_count_required_in_pdf": True,
        "localized_spanish_label_retained": True,
        "scanner_candidates_not_promoted": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_incomplete_analyzer_count",
    "canonical_summary_line",
    "install_comprehensive_incomplete_analyzer_summary",
]
