from __future__ import annotations

import base64
import html
import io
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

VERSION = "nico.express_not_scored_pdf_append.v35"
_PATCH_MARKER = "_nico_express_not_scored_pdf_append_v35"
_SCANNER_IDS = {"scanner_worker", "scanner_worker_evidence"}
_CLIENT_ACCEPTANCE_IDS = {"client_acceptance", "client_human_acceptance"}


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id"), 100).casefold()
    if section_id in _SCANNER_IDS:
        return True
    if section_id in _CLIENT_ACCEPTANCE_IDS:
        status = _text(section.get("status") or section.get("acceptance_status")).casefold()
        return not bool(section.get("approved") or section.get("accepted") or status in {"approved", "accepted", "green"})
    return section.get("directly_scored") is False and section.get("presented_score", section.get("score")) is None


def _controls(result: dict[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or not _not_scored(section):
            continue
        section_id = _text(section.get("id"), 100).casefold()
        scanner = section_id in _SCANNER_IDS
        output.append(
            {
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "status": "SUPPLEMENTAL" if scanner else "GRAY",
                "score": "NOT SCORED",
                "reason": (
                    "Scanner output is diagnostic evidence mapped into scored controls and cannot add maturity points by itself."
                    if scanner
                    else "Client and human acceptance remains pending and cannot contribute points before exact-snapshot approval."
                ),
            }
        )
    return output


def _page(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    controls = _controls(result)
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.66 * inch,
        title="NICO Express Non-Scored Controls",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "NotScoredTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=9,
    )
    body = ParagraphStyle(
        "NotScoredBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=10.6,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    label = ParagraphStyle(
        "NotScoredLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.4,
        leading=9.2,
        textColor=colors.HexColor("#64748b"),
    )

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    rows = [[p("Control", label), p("Status", label), p("Score treatment", label), p("Reason", label)]]
    for item in controls:
        rows.append([p(item["label"]), p(item["status"]), p(item["score"]), p(item["reason"])])
    table = Table(rows, colWidths=[1.8 * inch, 1.0 * inch, 1.15 * inch, 3.1 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    document.build(
        [
            p("Non-Scored Controls and Approval Boundary", title),
            p(
                "The controls below remain visible in every report format but are excluded from automated maturity scoring. Numeric placeholders such as None/100 or 0/100 are prohibited.",
                body,
            ),
            Spacer(1, 0.08 * inch),
            table,
            Spacer(1, 0.1 * inch),
            p("Human review is required. Client delivery remains blocked until the exact-snapshot approval record is complete."),
        ]
    )
    return buffer.getvalue()


def append_not_scored_page(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
    controls = _controls(result)
    if not controls:
        return pdf_bytes
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(_page(result))).pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    result["express_not_scored_pdf_append"] = {
        "status": "complete",
        "version": VERSION,
        "control_count": len(controls),
        "labels": [item["label"] for item in controls],
        "not_scored_literal_present": True,
        "numeric_placeholder_blocked": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output.getvalue()


def install_express_not_scored_pdf_append_v35() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        encoded, error = current(result)
        if not encoded:
            return encoded, error
        try:
            pdf_bytes = base64.b64decode(encoded, validate=True)
            appended = append_not_scored_page(pdf_bytes, result)
            return base64.b64encode(appended).decode("ascii"), error
        except Exception as exc:
            return None, f"Express non-scored PDF parity append failed: {type(exc).__name__}: {exc}"

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "not_scored_pdf_page_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "append_not_scored_page",
    "install_express_not_scored_pdf_append_v35",
]
