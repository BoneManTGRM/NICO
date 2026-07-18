from __future__ import annotations

import base64
import io
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from nico.express_report_premium_v14 import (
    _build_decision_brief,
    _build_pdf_sections,
    _evidence_citations,
    _finding_blocks,
    _finding_rows,
    _humanize,
    _normalize_result,
    _recommended_actions,
    _repo_name,
    _safe_markup,
    _score_band,
)

VERSION = "nico.express_report_dossier_export.v15"
_PATCH_MARKER = "_nico_express_report_dossier_export_v15"


class _NumberedCanvasMixin:
    pass


def _hex(value: str) -> colors.Color:
    return colors.HexColor(value)


_NAVY = _hex("#0B1F3A")
_BLUE = _hex("#1167B1")
_CYAN = _hex("#2AB7CA")
_LIGHT = _hex("#F3F6FA")
_MUTED = _hex("#5B6678")
_GREEN = _hex("#1B8A5A")
_AMBER = _hex("#B36B00")
_RED = _hex("#B42318")


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("NicoTitle", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=colors.white, spaceAfter=12),
        "subtitle": ParagraphStyle("NicoSubtitle", parent=sample["Normal"], fontName="Helvetica", fontSize=10.5, leading=14, textColor=_hex("#DCE8F5")),
        "h1": ParagraphStyle("NicoH1", parent=sample["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=_NAVY, spaceBefore=8, spaceAfter=8),
        "h2": ParagraphStyle("NicoH2", parent=sample["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=_BLUE, spaceBefore=6, spaceAfter=5),
        "body": ParagraphStyle("NicoBody", parent=sample["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.2, textColor=_hex("#172033"), spaceAfter=6),
        "small": ParagraphStyle("NicoSmall", parent=sample["BodyText"], fontName="Helvetica", fontSize=7.6, leading=10, textColor=_MUTED),
        "callout": ParagraphStyle("NicoCallout", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=_NAVY),
        "label": ParagraphStyle("NicoLabel", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=_MUTED, uppercase=True),
    }


def _footer(canvas, doc) -> None:
    canvas.saveState()
    width, _height = LETTER
    canvas.setStrokeColor(_hex("#D6DEE9"))
    canvas.line(0.55 * inch, 0.49 * inch, width - 0.55 * inch, 0.49 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_MUTED)
    canvas.drawString(0.55 * inch, 0.31 * inch, "NICO · Authorized Technical Assessment · Draft for Human Review")
    canvas.drawRightString(width - 0.55 * inch, 0.31 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _cover(canvas, doc) -> None:
    _footer(canvas, doc)


def _later(canvas, doc) -> None:
    _footer(canvas, doc)


def _score_color(score: float) -> colors.Color:
    if score >= 80:
        return _GREEN
    if score >= 60:
        return _AMBER
    return _RED


def _text(value: Any, default: str = "Not available") -> str:
    rendered = str(value or "").strip()
    return rendered or default


def _table(data: list[list[Any]], widths: list[float], *, header: bool = True) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.35, _hex("#D9E1EC")),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    for row in range(1 if header else 0, len(data)):
        commands.append(("BACKGROUND", (0, row), (-1, row), colors.white if row % 2 else _LIGHT))
    table.setStyle(TableStyle(commands))
    return table


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_safe_markup(_text(value)), style)


def _section_title(title: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    return [Spacer(1, 4), Paragraph(_safe_markup(title), styles["h1"]), HRFlowable(width="100%", thickness=0.8, color=_CYAN, spaceAfter=8)]


def _finding_story(result: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = []
    findings = _finding_rows(result)
    if not findings:
        return [_paragraph("No evidence-backed findings were available for this assessment.", styles["body"])]
    for index, finding in enumerate(findings[:40], start=1):
        severity = _humanize(finding.get("severity") or "unknown")
        title = _text(finding.get("title"), f"Finding {index}")
        citation = _text(finding.get("citation") or finding.get("source") or finding.get("path"), "Evidence citation unavailable")
        impact = _text(finding.get("impact") or finding.get("description"), "Impact requires authorized review.")
        recommendation = _text(finding.get("recommendation") or finding.get("repair"), "Recommendation requires authorized review.")
        block = [
            Paragraph(_safe_markup(f"{index}. {title}"), styles["h2"]),
            _table([
                [Paragraph("Severity", styles["small"]), Paragraph("Evidence", styles["small"])],
                [Paragraph(_safe_markup(severity), styles["body"]), Paragraph(_safe_markup(citation), styles["body"])],
            ], [1.15 * inch, 5.65 * inch]),
            Spacer(1, 5),
            Paragraph(_safe_markup(f"<b>Why it matters:</b> {impact}"), styles["body"]),
            Paragraph(_safe_markup(f"<b>Recommended action:</b> {recommendation}"), styles["body"]),
            Spacer(1, 7),
        ]
        story.append(KeepTogether(block))
    return story


def build_express_dossier_export(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        normalized = _normalize_result(result)
        styles = _styles()
        buffer = io.BytesIO()
        doc = BaseDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=0.55 * inch,
            rightMargin=0.55 * inch,
            topMargin=0.58 * inch,
            bottomMargin=0.62 * inch,
            title=f"NICO Express Assessment · {_repo_name(normalized)}",
            author="NICO",
            subject="Authorized technical assessment draft for human review",
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
        doc.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=_cover),
            PageTemplate(id="later", frames=[frame], onPage=_later),
        ])

        score = float((_record := normalized.get("maturity_signal") or {}).get("score") or normalized.get("technical_score") or 0)
        band = _score_band(score)
        repository = _repo_name(normalized)
        generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        decision = _build_decision_brief(normalized)
        actions = _recommended_actions(normalized)
        citations = _evidence_citations(normalized)

        story: list[Any] = []
        cover = Table([
            [Paragraph("NICO", ParagraphStyle("Brand", parent=styles["title"], fontSize=29, leading=31)), ""],
            [Paragraph("Express Technical Assessment", styles["title"]), ""],
            [Paragraph(_safe_markup(repository), styles["subtitle"]), ""],
            [Spacer(1, 14), ""],
            [Paragraph(_safe_markup(f"Technical score: <b>{score:.1f}/100</b> · {_humanize(band)}"), styles["subtitle"]), ""],
            [Paragraph(_safe_markup(f"Generated {generated} · Draft for required human review"), styles["subtitle"]), ""],
        ], colWidths=[5.9 * inch, 0.9 * inch], rowHeights=[0.42 * inch, 0.53 * inch, 0.31 * inch, 0.2 * inch, 0.35 * inch, 0.32 * inch])
        cover.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
            ("SPAN", (0, 0), (1, 0)),
            ("SPAN", (0, 1), (1, 1)),
            ("SPAN", (0, 2), (1, 2)),
            ("SPAN", (0, 3), (1, 3)),
            ("SPAN", (0, 4), (1, 4)),
            ("SPAN", (0, 5), (1, 5)),
            ("LEFTPADDING", (0, 0), (-1, -1), 18),
            ("RIGHTPADDING", (0, 0), (-1, -1), 18),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([cover, Spacer(1, 20)])

        score_table = _table([
            [Paragraph("Score", styles["small"]), Paragraph("Maturity", styles["small"]), Paragraph("Evidence readiness", styles["small"])],
            [Paragraph(f"<b>{score:.1f}/100</b>", styles["callout"]), Paragraph(_safe_markup(_humanize(band)), styles["callout"]), Paragraph(_safe_markup(_text((normalized.get("evidence_readiness") or {}).get("status"))), styles["callout"])],
        ], [1.7 * inch, 2.2 * inch, 2.9 * inch])
        score_table.setStyle(TableStyle([("TEXTCOLOR", (0, 1), (0, 1), _score_color(score))]))
        story.extend(score_table)
        story.extend(_section_title("Executive decision brief", styles))
        story.append(_paragraph(decision, styles["body"]))

        story.extend(_section_title("Priority actions", styles))
        action_rows = [[Paragraph("Priority", styles["small"]), Paragraph("Recommended action", styles["small"])]]
        for index, action in enumerate(actions[:12], start=1):
            action_rows.append([Paragraph(str(index), styles["body"]), _paragraph(action, styles["body"])])
        story.append(_table(action_rows, [0.7 * inch, 6.1 * inch]))

        story.append(PageBreak())
        story.extend(_section_title("Evidence-backed findings", styles))
        story.extend(_finding_story(normalized, styles))

        story.append(PageBreak())
        story.extend(_section_title("Assessment sections", styles))
        for section in _build_pdf_sections(normalized):
            title = _text(section.get("title"), "Assessment section")
            summary = _text(section.get("summary"), "No section summary was available.")
            section_score = section.get("score")
            header = title if section_score is None else f"{title} · {section_score}/100"
            story.append(KeepTogether([
                Paragraph(_safe_markup(header), styles["h2"]),
                _paragraph(summary, styles["body"]),
                Spacer(1, 4),
            ]))

        story.append(PageBreak())
        story.extend(_section_title("Evidence ledger", styles))
        citation_rows = [[Paragraph("#", styles["small"]), Paragraph("Evidence citation", styles["small"])]]
        for index, citation in enumerate(citations[:80], start=1):
            citation_rows.append([Paragraph(str(index), styles["small"]), _paragraph(citation, styles["small"])])
        story.append(_table(citation_rows, [0.45 * inch, 6.35 * inch]))

        story.extend(_section_title("Review and delivery controls", styles))
        story.append(_paragraph(
            "This artifact is a draft technical assessment. Human review is required before client delivery, repair execution, or any claim of production readiness.",
            styles["body"],
        ))

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        qa = {
            "status": "pass" if pdf_bytes.startswith(b"%PDF-") and b"%%EOF" in pdf_bytes[-2048:] else "fail",
            "bytes": len(pdf_bytes),
            "page_count_estimate": pdf_bytes.count(b"/Type /Page"),
            "generated_at": generated,
        }
        result["express_visual_qa"] = qa
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        if qa.get("status") != "pass":
            result["client_delivery_block_reason"] = "Express visual QA did not pass."
        elif bool(result.get("human_review_required", True)):
            result["client_delivery_allowed"] = False
            result["client_delivery_block_reason"] = "Authorized human review is still required."
        else:
            result.pop("client_delivery_block_reason", None)
        return base64.b64encode(pdf_bytes).decode("ascii"), None
    except Exception as exc:  # pragma: no cover
        return None, f"Express dossier export v15 failed: {type(exc).__name__}: {exc}"


def install_express_dossier_export_v15() -> dict[str, Any]:
    from nico import assessment_quality
    from nico.express_backend_final_gate_truth import install_express_backend_final_gate_truth

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        backend_gate = install_express_backend_final_gate_truth()
        return {"status": "already_installed", "version": VERSION, "backend_final_gate": backend_gate}
    setattr(build_express_dossier_export, _PATCH_MARKER, True)
    setattr(build_express_dossier_export, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_dossier_export
    backend_gate = install_express_backend_final_gate_truth()
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "backend_final_gate": backend_gate,
    }


__all__ = ["VERSION", "build_express_dossier_export", "install_express_dossier_export_v15"]
