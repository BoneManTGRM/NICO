from __future__ import annotations

import base64
import html
import io
from collections import Counter
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.express_report_finding_dossiers_v15 import build_finding_dossiers, report_labels
from nico.express_report_premium_v14 import _premium_pdf
from nico.express_report_visual_qa_v16 import validate_express_pdf


VERSION = "express_dossier_export_v16_compact"
_PATCH_MARKER = "_nico_express_dossier_export_v16_compact"
_MAX_DETAILED_PDF_DOSSIERS = 5


def _locale(result: dict[str, Any]) -> str:
    value = str(result.get("report_language") or result.get("language") or result.get("locale") or "en")
    return "es" if value.lower().replace("_", "-").startswith("es") else "en"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _severity_rank(value: Any) -> int:
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "informational": 4,
        "unclassified": 5,
    }.get(_clean(value).lower(), 6)


def _confidence_rank(value: Any) -> int:
    return {"high": 0, "standard": 1, "medium": 1, "review-limited": 2, "low": 3}.get(
        _clean(value).lower(), 4
    )


def _ordered_dossiers(result: dict[str, Any]) -> list[Any]:
    dossiers = list(build_finding_dossiers(result))
    dossiers.sort(
        key=lambda item: (
            _severity_rank(getattr(item, "severity", "")),
            _confidence_rank(getattr(item, "confidence", "")),
            _clean(getattr(item, "finding_id", "")),
        )
    )
    return dossiers


def _dossier_markdown(result: dict[str, Any]) -> str:
    locale = _locale(result)
    labels = report_labels(locale)
    lines = [f"\n\n# {labels['finding_dossier']} Appendix"]
    for dossier in _ordered_dossiers(result):
        lines.extend(
            [
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
            ]
        )
        lines.extend(f"  - {item}" for item in dossier.evidence)
    lines.extend(["", f"**{labels['human_review']}**"])
    return "\n".join(lines)


def _dossier_html(result: dict[str, Any]) -> str:
    locale = _locale(result)
    labels = report_labels(locale)
    cards: list[str] = []
    for dossier in _ordered_dossiers(result):
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
    return (
        f"<section class='nico-finding-dossiers'><h1>{html.escape(labels['finding_dossier'])} Appendix</h1>"
        f"{''.join(cards)}<p><b>{html.escape(labels['human_review'])}</b></p></section>"
    )


def _dossier_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    locale = _locale(result)
    labels = report_labels(locale)
    dossiers = _ordered_dossiers(result)
    detailed = dossiers[:_MAX_DETAILED_PDF_DOSSIERS]
    remaining = dossiers[_MAX_DETAILED_PDF_DOSSIERS:]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.46 * inch,
        leftMargin=0.46 * inch,
        topMargin=0.44 * inch,
        bottomMargin=0.52 * inch,
        title=labels["title"],
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DossierTitle", parent=styles["Title"], fontSize=16, leading=18, textColor=colors.HexColor("#0f172a"), spaceAfter=6)
    h2 = ParagraphStyle("DossierH2", parent=styles["Heading2"], fontSize=9.2, leading=11, textColor=colors.HexColor("#075985"), spaceBefore=3, spaceAfter=2)
    body = ParagraphStyle("DossierBody", parent=styles["BodyText"], fontSize=7.0, leading=8.6, textColor=colors.HexColor("#334155"), spaceAfter=2)
    tiny = ParagraphStyle("DossierTiny", parent=body, fontSize=6.1, leading=7.2, textColor=colors.HexColor("#475569"))

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(_clean(value)), style)

    inventory_note = (
        "The PDF contains the highest-priority decision records. The complete finding set remains available in Markdown, HTML, the JSON evidence bundle, and the immutable evidence ledger."
        if locale == "en"
        else "El PDF contiene los registros de decisión de mayor prioridad. El conjunto completo de hallazgos permanece disponible en Markdown, HTML, el paquete JSON y el libro mayor inmutable de evidencia."
    )
    story: list[Any] = [p(f"{labels['finding_dossier']} Appendix", title), p(labels["human_review"], h2), p(inventory_note), Spacer(1, 0.04 * inch)]

    for dossier in detailed:
        evidence = list(dossier.evidence or [])[:2]
        card: list[Any] = [
            Table(
                [
                    [p(f"{dossier.finding_id} — {dossier.title}", h2)],
                    [p(f"Section: {dossier.section_id} · Severity: {str(dossier.severity).upper()} · Confidence: {dossier.confidence} · Disposition: {dossier.disposition}", tiny)],
                ],
                colWidths=[7.58 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#94a3b8")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                ),
            ),
            p(f"{labels['business_impact']}: {dossier.business_impact}"),
        ]
        if evidence:
            card.append(p("Evidence: " + " | ".join(_clean(item) for item in evidence), tiny))
        card.extend(
            [
                p(f"{labels['repair_specification']}: {dossier.repair_specification}"),
                p(f"{labels['verification']}: {dossier.verification}", tiny),
                Spacer(1, 0.05 * inch),
            ]
        )
        story.append(KeepTogether(card))

    if remaining:
        severity_counts = Counter(_clean(item.severity).lower() or "pending" for item in remaining)
        section_counts = Counter(_clean(item.section_id) or "unknown" for item in remaining)
        story.extend(
            [
                p("Remaining finding inventory", h2),
                p(
                    f"{len(remaining)} additional decision records are retained outside the concise PDF appendix. "
                    f"Severity inventory: {', '.join(f'{key}={value}' for key, value in sorted(severity_counts.items()))}. "
                    f"Section inventory: {', '.join(f'{key}={value}' for key, value in sorted(section_counts.items()))}."
                ),
            ]
        )

    doc.build(story)
    return buffer.getvalue()


def build_express_dossier_export(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
        markdown = str(reports.get("markdown") or "")
        if "FND-" not in markdown:
            reports["markdown"] = markdown + _dossier_markdown(result)
        html_report = str(reports.get("html") or "")
        if "nico-finding-dossiers" not in html_report:
            reports["html"] = html_report + _dossier_html(result)
        result["reports"] = reports

        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(_premium_pdf(result))).pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(_dossier_pdf(result))).pages:
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        pdf_bytes = output.getvalue()
        dossiers = _ordered_dossiers(result)
        pdf_dossier_count = min(len(dossiers), _MAX_DETAILED_PDF_DOSSIERS)
        result["express_finding_dossier_export"] = {
            "status": "complete",
            "version": VERSION,
            "locale": _locale(result),
            "dossier_count": len(dossiers),
            "pdf_detailed_dossier_count": pdf_dossier_count,
            "pdf_summary_inventory_count": max(0, len(dossiers) - pdf_dossier_count),
            "complete_finding_set_retained_in_markdown_html_json": True,
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
        return None, f"Express dossier export failed: {type(exc).__name__}: {exc}"


def install_express_dossier_export_v15() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(build_express_dossier_export, _PATCH_MARKER, True)
    setattr(build_express_dossier_export, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_dossier_export
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "compact_pdf_appendix": True,
        "full_evidence_retained_outside_pdf": True,
    }


__all__ = ["VERSION", "build_express_dossier_export", "install_express_dossier_export_v15"]
