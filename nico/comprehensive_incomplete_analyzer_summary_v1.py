from __future__ import annotations

import base64
import io
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive-incomplete-analyzer-summary.v1"
_MARKDOWN_MARKER = "_nico_incomplete_analyzer_markdown_v1"
_PDF_MARKER = "_nico_incomplete_analyzer_pdf_v1"
_ACCURACY_MARKER = "_nico_incomplete_analyzer_accuracy_v1"
_CANONICAL_LABEL = "Incomplete applicable analyzers"
_SPANISH_LABEL = "Analizadores aplicables incompletos"
_LEGACY_ENGLISH_ONLY_ERROR = (
    "client report omitted the canonical incomplete analyzer count"
)


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


def _report_is_spanish(canonical: Mapping[str, Any]) -> bool:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    for value in (
        identity.get("report_language"),
        identity.get("requested_report_language"),
        identity.get("requested_locale"),
        identity.get("locale"),
        canonical.get("report_language"),
        canonical.get("locale"),
        assessment.get("report_language"),
        assessment.get("locale"),
    ):
        normalized = _text(value).casefold().replace("_", "-")
        if normalized.startswith("es"):
            return True
        if normalized.startswith("en"):
            return False
    return False


def _coverage_denominator(canonical: Mapping[str, Any]) -> int:
    contract = (
        canonical.get("client_readiness_contract")
        if isinstance(canonical.get("client_readiness_contract"), Mapping)
        else {}
    )
    for value in (
        contract.get("coverage_denominator"),
        canonical.get("coverage_denominator"),
    ):
        count = _count_value(value)
        if count is not None:
            return count
    return 0


def _rendered_surface_text(package: Mapping[str, Any]) -> str:
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    try:
        from pypdf import PdfReader

        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
        extracted = "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
        )
    except Exception:
        extracted = ""
    return "\n".join((markdown, rendered_html, extracted))


def _validate_localized_accuracy(
    current: Callable[[Mapping[str, Any]], dict[str, Any]],
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve every legacy accuracy check while removing one English-only assumption.

    The historical validator correctly requires the canonical analyzer count, but its
    zero-incomplete check recognizes only the English presentation label. A valid es-MX
    package is therefore rejected after rendering the localized count. Validate the
    actual locale-specific line first, then supply an English-only compatibility probe
    solely to the legacy validator so all of its remaining checks still execute. The
    probe is never returned or published.
    """

    canonical = (
        package.get("json")
        if isinstance(package.get("json"), Mapping)
        else {}
    )
    spanish = _report_is_spanish(canonical)
    expected_line = canonical_summary_line(canonical, spanish=spanish)
    scanner_backed = _coverage_denominator(canonical) >= 9
    if scanner_backed and expected_line.casefold() not in _rendered_surface_text(
        package
    ).casefold():
        raise ValueError(
            "client report omitted the locale-specific canonical incomplete analyzer "
            f"count: {expected_line}"
        )

    compatibility_probe_used = False
    try:
        result = current(package)
    except ValueError as exc:
        if (
            not scanner_backed
            or not spanish
            or _text(exc) != _LEGACY_ENGLISH_ONLY_ERROR
        ):
            raise
        compatibility_probe = dict(package)
        compatibility_probe["markdown"] = (
            str(package.get("markdown") or "").rstrip()
            + "\n\n"
            + canonical_summary_line(canonical, spanish=False)
            + "\n"
        )
        result = current(compatibility_probe)
        compatibility_probe_used = True

    validated = dict(result)
    validated.update(
        {
            "canonical_incomplete_analyzer_count": (
                canonical_incomplete_analyzer_count(canonical)
            ),
            "canonical_incomplete_analyzer_summary": expected_line,
            "canonical_incomplete_analyzer_summary_language": (
                "es-MX" if spanish else "en"
            ),
            "locale_aware_incomplete_analyzer_validation": True,
            "legacy_english_only_probe_used": compatibility_probe_used,
            "legacy_english_only_probe_published": False,
        }
    )
    return validated


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

    heading = (
        "## Evidence Package Summary"
        if not spanish
        else "## Resumen del paquete de evidencia"
    )
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
    first_text = " ".join((reader.pages[0].extract_text() or "").casefold().split())
    branded_cover = any(
        marker in first_text
        for marker in (
            "evidence-bound technical review package",
            "paquete de revisión técnica basado en evidencia",
        )
    )
    target_index = 1 if len(reader.pages) > 1 and branded_cover else 0
    reader.pages[target_index].merge_page(overlay_page)

    writer = PdfWriter()
    for page in reader.pages:
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
    from nico import comprehensive_client_report_render_v60 as report_render

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

    current_accuracy = report_render.validate_existing_report_accuracy
    if not getattr(current_accuracy, _ACCURACY_MARKER, False):

        @wraps(current_accuracy)
        def validate_existing_report_accuracy(
            package: Mapping[str, Any],
        ) -> dict[str, Any]:
            return _validate_localized_accuracy(current_accuracy, package)

        setattr(validate_existing_report_accuracy, _ACCURACY_MARKER, True)
        setattr(validate_existing_report_accuracy, "_nico_previous", current_accuracy)
        report_render.validate_existing_report_accuracy = (
            validate_existing_report_accuracy
        )

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
        "accuracy_validator_bound": getattr(
            report_render.validate_existing_report_accuracy,
            _ACCURACY_MARKER,
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
        "legacy_english_only_validator_not_authoritative": True,
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
