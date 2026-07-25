from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_executive_brief_page_gate.v1"
_BUILD_MARKER = "__nico_executive_brief_page_gate_v1__"
_COPY_MARKER = "__nico_executive_brief_copy_v1__"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _identity_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    value = kwargs.get("identity")
    if isinstance(value, dict):
        return value
    if args and isinstance(args[0], dict):
        return args[0]
    return {}


def _brief_copy(identity: dict[str, Any]) -> tuple[str, str]:
    repository = _text(identity.get("repository"), 120) or "the assessed repository"
    commit = _text(identity.get("commit_sha"), 64) or "the retained commit"
    duration = identity.get("assessment_duration_seconds")
    duration_text = f" in {float(duration):.1f} seconds" if isinstance(duration, (int, float)) and duration >= 0 else ""
    meaning = (
        "What this means for you: treat the highest-priority evidence-bound risk as the immediate decision, "
        "convert the 0-30 day work into the active backlog, and do not authorize release or client delivery "
        "until the stated conditions are satisfied."
    )
    speed = (
        f"Automated analysis of {repository} was executed{duration_text} against immutable commit {commit}; "
        "repeat runs use the same versioned contract to measure verified change rather than rewritten narrative."
    )
    return meaning, speed


def _wrap_markdown(delegate: Callable[..., str]) -> Callable[..., str]:
    if getattr(delegate, _COPY_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> str:
        output = delegate(*args, **kwargs)
        if not isinstance(output, str) or "## Executive Decision Brief" not in output:
            return output
        meaning, speed = _brief_copy(_identity_from_call(args, kwargs))
        insertion = f"## Executive Decision Brief\n\n**{meaning}**\n\n{speed}"
        return output.replace("## Executive Decision Brief", insertion, 1)

    setattr(wrapped, _COPY_MARKER, True)
    return wrapped


def _wrap_html(delegate: Callable[..., str]) -> Callable[..., str]:
    if getattr(delegate, _COPY_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> str:
        output = delegate(*args, **kwargs)
        marker = "<section><h2>Executive Decision Brief</h2>"
        if not isinstance(output, str) or marker not in output:
            return output
        meaning, speed = _brief_copy(_identity_from_call(args, kwargs))
        insertion = (
            marker
            + f"<p><b>{html.escape(meaning)}</b></p>"
            + f"<p>{html.escape(speed)}</p>"
        )
        return output.replace(marker, insertion, 1)

    setattr(wrapped, _COPY_MARKER, True)
    return wrapped


def _fit_line(text: str, width: float, font_name: str, font_size: float) -> str:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    candidate = _text(text, 900)
    if stringWidth(candidate, font_name, font_size) <= width:
        return candidate
    while candidate and stringWidth(candidate + "...", font_name, font_size) > width:
        candidate = candidate[:-1]
    return candidate.rstrip() + "..."


def _add_page_two_copy(pdf_bytes: bytes, identity: dict[str, Any]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if len(reader.pages) < 3:
        raise ValueError("Executive Decision Brief validation requires at least three PDF pages")
    meaning, speed = _brief_copy(identity)
    overlay_buffer = io.BytesIO()
    overlay_canvas = canvas.Canvas(overlay_buffer, pagesize=letter, invariant=1)
    overlay_canvas.setFillColor(colors.white)
    overlay_canvas.rect(40, 130, 532, 42, stroke=0, fill=1)
    overlay_canvas.setFillColor(colors.HexColor("#075985"))
    overlay_canvas.setFont("Helvetica-Bold", 8)
    overlay_canvas.drawString(42, 159, "WHAT THIS MEANS FOR YOU")
    overlay_canvas.setFillColor(colors.HexColor("#475569"))
    overlay_canvas.setFont("Helvetica", 6.6)
    overlay_canvas.drawString(42, 146, _fit_line(meaning.replace("What this means for you: ", ""), 528, "Helvetica", 6.6))
    overlay_canvas.setFont("Helvetica", 6.1)
    overlay_canvas.drawString(42, 134, _fit_line(speed, 528, "Helvetica", 6.1))
    overlay_canvas.save()
    overlay = PdfReader(io.BytesIO(overlay_buffer.getvalue()))
    reader.pages[1].merge_page(overlay.pages[0], over=True)
    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    if reader.metadata:
        writer.add_metadata({str(key): str(value) for key, value in reader.metadata.items() if value is not None})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def validate_executive_brief_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts = [page.extract_text() or "" for page in reader.pages]
    brief_pages = [index + 1 for index, text in enumerate(texts) if "Executive Decision Brief" in text]
    scorecard_pages = [index + 1 for index, text in enumerate(texts) if "Canonical Technical Scorecard" in text or "Technical Scorecard" in text]
    meaning_pages = [index + 1 for index, text in enumerate(texts) if "WHAT THIS MEANS FOR YOU" in text.upper()]
    immutable_pages = [index + 1 for index, text in enumerate(texts) if "immutable commit" in text.casefold()]
    page_two = texts[1] if len(texts) >= 2 else ""
    required_markers = [
        "Executive Decision Brief",
        "Decision dashboard",
        "Top business consequences",
        "PACKAGE IDENTITY",
        "WHAT THIS MEANS FOR YOU",
    ]
    checks = {
        "pdf_has_at_least_three_pages": len(texts) >= 3,
        "executive_brief_page_count": len(brief_pages),
        "executive_brief_pages": brief_pages,
        "executive_brief_exactly_page_two": brief_pages == [2],
        "scorecard_begins_after_executive_brief": bool(scorecard_pages) and min(scorecard_pages) >= 3,
        "what_this_means_present_on_page_two": meaning_pages == [2],
        "immutable_commit_value_statement_on_page_two": 2 in immutable_pages,
        "required_page_two_markers_present": all(marker.casefold() in page_two.casefold() for marker in required_markers),
        "page_two_content_density_valid": 500 <= len(page_two) <= 7000,
        "scorecard_pages": scorecard_pages,
    }
    checks["valid"] = all(
        value is True
        for key, value in checks.items()
        if key not in {"executive_brief_page_count", "executive_brief_pages", "scorecard_pages", "valid"}
    ) and checks["executive_brief_page_count"] == 1
    return checks


def _wrap_report_builder(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _BUILD_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict) or result.get("status") != "complete":
            return result
        output = deepcopy(result)
        package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
        encoded = _text(package.get("pdf_base64"), 50_000_000)
        identity = _identity_from_call(args, kwargs)
        try:
            original = base64.b64decode(encoded, validate=True)
            revised = _add_page_two_copy(original, identity)
            validation = validate_executive_brief_pdf(revised)
        except Exception as exc:
            output["status"] = "blocked"
            output["reason"] = f"executive_decision_brief_page_gate_failed:{type(exc).__name__}"
            return output

        package["pdf_base64"] = base64.b64encode(revised).decode("ascii")
        package["pdf_sha256"] = hashlib.sha256(revised).hexdigest()
        package["executive_decision_brief_validation"] = validation
        quality = output.get("report_quality_contract") if isinstance(output.get("report_quality_contract"), dict) else {}
        quality.update(
            {
                "executive_brief_page_gate_version": VERSION,
                "executive_brief_exactly_one_page": validation["valid"],
                "executive_brief_page_count": validation["executive_brief_page_count"],
                "executive_brief_page_number": 2 if validation["valid"] else None,
                "executive_brief_what_this_means_present": validation["what_this_means_present_on_page_two"],
                "executive_brief_immutable_commit_value_present": validation["immutable_commit_value_statement_on_page_two"],
                "executive_brief_scorecard_separated": validation["scorecard_begins_after_executive_brief"],
            }
        )
        package["report_quality_contract"] = quality
        output["report_package"] = package
        output["report_quality_contract"] = quality
        if not validation["valid"]:
            output["status"] = "blocked"
            output["reason"] = "executive_decision_brief_page_gate_failed"
        return output

    setattr(wrapped, _BUILD_MARKER, True)
    return wrapped


def install_comprehensive_executive_brief_page_gate_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    report._build_markdown = _wrap_markdown(report._build_markdown)
    report._build_html = _wrap_html(report._build_html)
    report.build_comprehensive_report_package = _wrap_report_builder(report.build_comprehensive_report_package)
    return {
        "status": "installed",
        "version": VERSION,
        "executive_brief_exactly_one_page_required": True,
        "executive_brief_expected_page": 2,
        "what_this_means_for_you_required": True,
        "immutable_commit_value_statement_required": True,
        "scorecard_must_begin_after_brief": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_executive_brief_page_gate_v1",
    "validate_executive_brief_pdf",
]
