from __future__ import annotations

import base64
import html
import io
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.express_report_finding_dossiers_v15 import build_finding_dossiers, report_labels
from nico.express_report_premium_v14 import _premium_pdf
from nico.express_report_visual_qa_v16 import validate_express_pdf


VERSION = "express_dossier_export_v15"
_PATCH_MARKER = "_nico_express_dossier_export_v15"


def _locale(result: dict[str, Any]) -> str:
    value = str(result.get("report_language") or result.get("language") or result.get("locale") or "en")
    return "es" if value.lower().replace("_", "-").startswith("es") else "en"


def _dossier_markdown(result: dict[str, Any]) -> str:
    locale = _locale(result)
    labels = report_labels(locale)
    dossiers = build_finding_dossiers(result)
    lines = [f"\n\n# {labels['finding_dossier']} Appendix"]
    for dossier in dossiers:
        lines.extend([
            "",
            f"## {dossier.finding_id} — {dossier.title}",
            f"- Section: {dossier.section_id}",
            f"- Severity: {dossier.severity}",
            f"- Confidence: {dossier.confidence}",
            f"- {labels['business_impact']}: {dossier.business_impact}",
            f"- {labels['repair_specification']}: {dossier.repair_specification}",
            f"- Owner: {dossier.owner}",
            f"- Effort: {dossier.effort}",
            f"- {labels['verification']}: {dossier.verification}",
            f"- {labels['rollback']}: {dossier.rollback}",
            f"- {labels['residual_risk']}: {dossier.residual_risk}",
            f"- Disposition: {dossier.disposition}",
            "- Evidence:",
        ])
        lines.extend(f"  - {item}" for item in dossier.evidence)
    lines.extend(["", f"**{labels['human_review']}**"])
    return "\n".join(lines)


def _dossier_html(result: dict[str, Any]) -> str:
    locale = _locale(result)
    labels = report_labels(locale)
    cards: list[str] = []
    for dossier in build_finding_dossiers(result):
        evidence = "".join(f"<li>{html.escape(item)}</li>" for item in dossier.evidence)
        cards.append(
            "<article class='nico-finding-dossier'>"
            f"<h2>{html.escape(dossier.finding_id)} — {html.escape(dossier.title)}</h2>"
            f"<p><b>Section:</b> {html.escape(dossier.section_id)}</p>"
            f"<p><b>Severity:</b> {html.escape(dossier.severity)} · <b>Confidence:</b> {html.escape(dossier.confidence)}</p>"
            f"<p><b>{html.escape(labels['business_impact'])}:</b> {html.escape(dossier.business_impact)}</p>"
            f"<p><b>{html.escape(labels['repair_specification'])}:</b> {html.escape(dossier.repair_specification)}</p>"
            f"<p><b>Owner:</b> {html.escape(dossier.owner)} · <b>Effort:</b> {html.escape(dossier.effort)}</p>"
            f"<p><b>{html.escape(labels['verification'])}:</b> {html.escape(dossier.verification)}</p>"
            f"<p><b>{html.escape(labels['rollback'])}:</b> {html.escape(dossier.rollback)}</p>"
            f"<p><b>{html.escape(labels['residual_risk'])}:</b> {html.escape(dossier.residual_risk)}</p>"
            f"<ul>{evidence}</ul>"
            "</article>"
        )
    return f"<section class='nico-finding-dossiers'><h1>{html.escape(labels['finding_dossier'])} Appendix</h1>{''.join(cards)}<p><b>{html.escape(labels['human_review'])}</b></p></section>"


def _dossier_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    locale = _locale(result)
    labels = report_labels(locale)
    dossiers = build_finding_dossiers(result)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.58 * inch,
        leftMargin=0.58 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.68 * inch,
        title=labels["title"],
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DossierTitle", parent=styles["Title"], fontSize=19, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=9)
    h2 = ParagraphStyle("DossierH2", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#075985"), spaceAfter=6)
    body = ParagraphStyle("DossierBody", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("DossierSmall", parent=body, fontSize=7.3, leading=9.2, textColor=colors.HexColor("#475569"))

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(" ".join(str(value or "").split())), style)

    story: list[Any] = [p(f"{labels['finding_dossier']} Appendix", title), p(labels["human_review"], h2)]
    for index, dossier in enumerate(dossiers):
        if index:
            story.append(PageBreak())
        story.extend([
            p(f"{dossier.finding_id} — {dossier.title}", title),
            Table([
                [p("Section", small), p(dossier.section_id, small), p("Severity", small), p(dossier.severity.upper(), small)],
                [p("Confidence", small), p(dossier.confidence, small), p("Disposition", small), p(dossier.disposition, small)],
                [p("Owner", small), p(dossier.owner, small), p("Effort", small), p(dossier.effort, small)],
            ], colWidths=[0.85*inch, 2.65*inch, 0.85*inch, 2.65*inch], style=TableStyle([
                ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#e0f2fe")),
                ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#e0f2fe")),
                ("LEFTPADDING", (0,0), (-1,-1), 5),
                ("RIGHTPADDING", (0,0), (-1,-1), 5),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ])),
            Spacer(1, 0.08*inch),
            p(labels["business_impact"], h2), p(dossier.business_impact),
            p("Evidence", h2),
        ])
        story.extend(p(f"• {item}", small) for item in dossier.evidence)
        story.extend([
            p(labels["repair_specification"], h2), p(dossier.repair_specification),
            p(labels["verification"], h2), p(dossier.verification),
            p(labels["rollback"], h2), p(dossier.rollback),
            p(labels["residual_risk"], h2), p(dossier.residual_risk),
        ])
    doc.build(story)
    return buffer.getvalue()


def build_express_dossier_export(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
        markdown = str(reports.get("markdown") or "")
        dossier_md = _dossier_markdown(result)
        if "FND-" not in markdown:
            reports["markdown"] = markdown + dossier_md
        html_report = str(reports.get("html") or "")
        dossier_html = _dossier_html(result)
        if "nico-finding-dossiers" not in html_report:
            reports["html"] = html_report + dossier_html
        result["reports"] = reports

        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(_premium_pdf(result))).pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(_dossier_pdf(result))).pages:
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        pdf_bytes = output.getvalue()
        dossiers = build_finding_dossiers(result)
        result["express_finding_dossier_export"] = {
            "status": "complete",
            "version": VERSION,
            "locale": _locale(result),
            "dossier_count": len(dossiers),
            "stable_finding_ids": True,
            "pdf_bound": True,
            "markdown_bound": True,
            "html_bound": True,
            "human_review_required": True,
        }
        qa = validate_express_pdf(pdf_bytes, result)
        result["express_visual_qa"] = qa
        reports["pdf_quality_status"] = qa.get("status")
        reports["pdf_quality_issues"] = list(qa.get("issues") or [])
        reports["client_delivery_allowed"] = bool(qa.get("client_delivery_allowed"))
        result["reports"] = reports
        result["client_delivery_allowed"] = bool(qa.get("client_delivery_allowed"))
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

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(build_express_dossier_export, _PATCH_MARKER, True)
    setattr(build_express_dossier_export, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_dossier_export
    return {"status": "installed", "version": VERSION, "production_renderer_bound": True}


__all__ = ["VERSION", "build_express_dossier_export", "install_express_dossier_export_v15"]
