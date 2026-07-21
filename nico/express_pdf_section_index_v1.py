from __future__ import annotations

import base64
import io
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.express_section_status_truth_v26 import assurance_presentation, technical_score_band

VERSION = "nico.express_pdf_section_index.v2"
_NOT_SCORED_IDS = {
    "scanner_worker",
    "scanner_worker_evidence",
    "client_acceptance",
    "client_human_acceptance",
}


def _text(value: Any, limit: int = 240) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id")).casefold()
    status = _text(section.get("presented_status") or section.get("status")).casefold()
    if section_id in {"scanner_worker", "scanner_worker_evidence"} or status == "supplemental":
        return True
    if section_id in {"client_acceptance", "client_human_acceptance"} and status != "green":
        return True
    return section.get("directly_scored") is False or section.get(
        "presented_score", section.get("score")
    ) is None


def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"), 100)
        label = _text(section.get("label") or section.get("title") or section_id, 180)
        if not label:
            continue
        not_scored = _not_scored(section)
        score = None if not_scored else section.get("score_value")
        if score is None and not not_scored:
            score = section.get("presented_score", section.get("score"))
        status = _text(section.get("presented_status") or section.get("status") or "unknown", 40).upper()
        if section_id.casefold() in {"scanner_worker", "scanner_worker_evidence"}:
            status = "SUPPLEMENTAL"
        band = technical_score_band(score, scored=not not_scored)
        assurance = assurance_presentation(status, scored=not not_scored)
        band_label = _text(section.get("score_band_label") or band["score_band_label"], 60)
        assurance_label = _text(section.get("assurance_label") or assurance["assurance_label"], 80)
        records.append(
            {
                "section_id": section_id,
                "label": label,
                "canonical_status": status,
                "technical_band": band_label,
                "assurance": assurance_label,
                "assurance_display": f"{assurance_label} ({status})",
                "score": None if score is None else int(score),
                "score_label": "NOT SCORED" if score is None else f"{int(score)}/100",
                "directly_scored": not not_scored,
            }
        )
    return records


def _index_pdf(result: dict[str, Any], records: list[dict[str, Any]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.42 * inch,
        leftMargin=0.42 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Express Canonical Section Index",
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "CanonicalIndexTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=9,
    )
    body = ParagraphStyle(
        "CanonicalIndexBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=9.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "CanonicalIndexLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.1,
        leading=8.8,
        textColor=colors.HexColor("#64748b"),
    )

    def paragraph(value: Any, style: Any = body) -> Paragraph:
        import html

        return Paragraph(html.escape(_text(value, 500)), style)

    rows = [
        [
            paragraph("Canonical section", label_style),
            paragraph("Technical score", label_style),
            paragraph("Technical band", label_style),
            paragraph("Evidence assurance", label_style),
            paragraph("Treatment", label_style),
        ]
    ]
    for item in records:
        rows.append(
            [
                paragraph(item["label"]),
                paragraph(item["score_label"]),
                paragraph(item["technical_band"]),
                paragraph(item["assurance_display"]),
                paragraph("Scored" if item["directly_scored"] else "Supplemental / review control"),
            ]
        )

    table = Table(rows, colWidths=[2.35 * inch, 0.95 * inch, 1.05 * inch, 1.65 * inch, 1.45 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source = maturity.get("source_score", maturity.get("score"))
    presented = maturity.get("presented_score", result.get("evidence_adjusted_score"))
    story = [
        paragraph("Canonical Section, Score, and Assurance Index", title),
        paragraph(
            "Technical score, technical band, and evidence assurance are separate fields. A STRONG or EXCEPTIONAL technical score can remain REVIEW LIMITED when evidence requires disposition. Supplemental scanner evidence and pending human acceptance remain NOT SCORED.",
            body,
        ),
        Spacer(1, 0.08 * inch),
        table,
        Spacer(1, 0.12 * inch),
        paragraph(f"Source maturity score: {source}/100" if source is not None else "Source maturity score: NOT SCORED"),
        paragraph(
            f"Evidence-adjusted score: {presented}/100"
            if presented is not None
            else "Evidence-adjusted score: NOT SCORED"
        ),
        paragraph("Delivery status: Human review required. Client delivery is not approved."),
    ]
    doc.build(story)
    return buffer.getvalue()


def append_canonical_section_index(result: dict[str, Any]) -> dict[str, Any]:
    reports = result.get("reports")
    if not isinstance(reports, dict):
        raise RuntimeError("Express report package is unavailable for PDF section indexing")
    encoded = reports.get("pdf_base64")
    if not isinstance(encoded, str) or not encoded.strip():
        raise RuntimeError("Express PDF is unavailable for canonical section indexing")

    raw = base64.b64decode(encoded, validate=True)
    reader = PdfReader(io.BytesIO(raw))
    records = _records(result)
    existing_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required_labels = [item["label"] for item in records]
    missing_before = [label for label in required_labels if label not in existing_text]

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if missing_before:
        index_reader = PdfReader(io.BytesIO(_index_pdf(result, records)))
        for page in index_reader.pages:
            writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    final_bytes = output.getvalue()
    final_reader = PdfReader(io.BytesIO(final_bytes))
    final_text = "\n".join(page.extract_text() or "" for page in final_reader.pages)
    missing_after = [label for label in required_labels if label not in final_text]
    score_labels = [item["score_label"] for item in records]
    missing_scores = [score for score in score_labels if score not in final_text]
    if missing_after or missing_scores:
        raise RuntimeError(
            "Express PDF canonical section parity failed: "
            f"missing_labels={missing_after}, missing_scores={missing_scores}"
        )

    reports["pdf_base64"] = base64.b64encode(final_bytes).decode("ascii")
    result["express_pdf_section_index"] = {
        "status": "complete",
        "version": VERSION,
        "record_count": len(records),
        "records": records,
        "page_count_before": len(reader.pages),
        "page_count_after": len(final_reader.pages),
        "index_appended": bool(missing_before),
        "missing_labels_before": missing_before,
        "missing_labels_after": missing_after,
        "missing_score_labels_after": missing_scores,
        "canonical_labels_present": not missing_after,
        "canonical_scores_present": not missing_scores,
        "score_band_separated_from_assurance": True,
        "canonical_status_retained": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


__all__ = ["VERSION", "append_canonical_section_index"]
