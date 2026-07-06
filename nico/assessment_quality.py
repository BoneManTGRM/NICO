from __future__ import annotations

import base64
import html
import io
from typing import Any


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in result.get("sections", []) or []:
        if item.get("id") == section_id:
            return item
    return None


def _metadata_limited(text: str) -> bool:
    lower = text.lower()
    return "github returned 403" in lower or "github returned 429" in lower or "api rate" in lower or "request limit" in lower


def _notes_limited(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    notes = list(item.get("unavailable", []) or []) + list(item.get("evidence", []) or [])
    return any(_metadata_limited(str(note)) for note in notes)


def _clean_text(value: Any, limit: int = 1400) -> str:
    text = str(value or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: max(0, limit - 18)].rstrip() + "... [truncated]"
    return text


def _status_color(status: str) -> str:
    status = (status or "").lower()
    if status == "green":
        return "#059669"
    if status == "yellow":
        return "#d97706"
    if status == "red":
        return "#dc2626"
    return "#64748b"


def _status_label(item: dict[str, Any]) -> str:
    return f"{str(item.get('status') or 'unknown').upper()} · {item.get('score', 'N/A')}/100"


def _p(text: Any, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_clean_text(text)).replace("\n", "<br/>"), style)


def _bullets(items: list[str], style: Any, max_items: int = 6, limit: int = 520) -> list[Any]:
    if not items:
        return [_p("No evidence returned.", style)]
    flowables: list[Any] = []
    for item in items[:max_items]:
        flowables.append(_p(f"• {_clean_text(item, limit)}", style))
    if len(items) > max_items:
        flowables.append(_p(f"• {len(items) - max_items} additional item(s) omitted from PDF; use Markdown/HTML for full detail.", style))
    return flowables


def _draw_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO · Powered by Reparodynamics · evidence-bound · human review required")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.33 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _panel(rows: list[list[Any]], widths: list[float], background: str = "#ffffff") -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#dbe3ef")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eef2f7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _build_polished_pdf_base64(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        return None, f"PDF polish unavailable because reportlab is not installed: {exc}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.72 * inch,
        title="NICO Express Technical Health Assessment",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    brand = ParagraphStyle("NicoBrand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=colors.HexColor("#0369a1"), alignment=1, spaceAfter=2)
    title = ParagraphStyle("NicoTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), alignment=1, spaceAfter=7)
    subtitle = ParagraphStyle("NicoSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9.4, leading=12.5, textColor=colors.HexColor("#334155"), alignment=1, spaceAfter=5)
    h2 = ParagraphStyle("NicoH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("NicoH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=12.5, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("NicoBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.8, leading=12, textColor=colors.HexColor("#1f2937"), spaceAfter=5)
    small = ParagraphStyle("NicoSmall", parent=body, fontSize=7.8, leading=10.3, textColor=colors.HexColor("#475569"), spaceAfter=3)
    label_style = ParagraphStyle("NicoLabel", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    callout = ParagraphStyle("NicoCallout", parent=body, fontName="Helvetica-Bold", fontSize=8.8, leading=12, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, alignment=1, spaceAfter=8)
    section_title = ParagraphStyle("NicoSectionTitle", parent=h2, fontSize=12.5, leading=15.5, spaceBefore=9, spaceAfter=4)

    generated = result.get("generated_at") or "Not specified"
    repo = result.get("repository") or "Not specified"
    maturity = result.get("maturity_signal") or {}
    quality = result.get("assessment_quality") or "standard"
    sections = result.get("sections") or []
    target = (result.get("coverage_targets") or {}).get("express_technical_health_assessment", {}).get("target") or "90-95%"

    story: list[Any] = [
        _p("NICO · Powered by Reparodynamics", brand),
        _p("Express Technical Health Assessment", title),
        _p(f"Repository: {repo}", subtitle),
        _p(f"Client: {result.get('client_name') or 'Not specified'} · Project: {result.get('project_name') or 'Not specified'}", subtitle),
        _p(f"Generated: {generated}", subtitle),
        _p("Human review is required before client-facing delivery. Missing evidence is shown as unavailable, not invented.", callout),
    ]

    summary_rows = [
        [_p("Maturity", label_style), _p(maturity.get("level") or "Unknown", body), _p("Score", label_style), _p(maturity.get("score") or "N/A", body)],
        [_p("Assessment quality", label_style), _p(quality, body), _p("Target", label_style), _p(target, body)],
    ]
    story += [_panel(summary_rows, [1.25 * inch, 2.05 * inch, 0.85 * inch, 2.1 * inch], "#f8fafc"), Spacer(1, 0.12 * inch)]
    story += [_p("Executive Summary", h2), _p(result.get("executive_summary") or "No executive summary returned.", body)]

    if sections:
        story += [_p("Section Scorecard", h2)]
        for item in sections:
            status_color = colors.HexColor(_status_color(item.get("status", "")))
            rows = [[_p(item.get("label") or item.get("id"), label_style), _p(_status_label(item), label_style)], [_p(item.get("summary") or "No summary returned.", small), ""]]
            card = Table(rows, colWidths=[4.3 * inch, 1.95 * inch], hAlign="LEFT")
            card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.35, colors.HexColor("#e5e7eb")),
                ("TEXTCOLOR", (1, 0), (1, 0), status_color),
                ("SPAN", (0, 1), (1, 1)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            story += [card, Spacer(1, 0.06 * inch)]
        story += [PageBreak()]

    for item in sections:
        heading = _p(f"{item.get('label') or item.get('id')} · {_status_label(item)}", section_title)
        intro = _p(item.get("summary") or "", body)
        story += [KeepTogether([heading, intro])]
        story.append(_p("Evidence", h3))
        story.extend(_bullets(list(item.get("evidence", []) or []), small, max_items=5, limit=430))
        if item.get("findings"):
            story.append(_p("Findings", h3))
            story.extend(_bullets(list(item.get("findings", []) or []), small, max_items=4, limit=420))
        if item.get("unavailable"):
            story.append(_p("Unavailable data", h3))
            story.extend(_bullets(list(item.get("unavailable", []) or []), small, max_items=4, limit=420))
        story += [Spacer(1, 0.07 * inch), HRFlowable(width="100%", thickness=0.35, color=colors.HexColor("#e5e7eb"))]

    action_blocks = [("Quick Wins", "quick_wins"), ("Medium-Term Plan", "medium_term_plan"), ("Resourcing Recommendation", "resourcing_recommendation"), ("Risk Register", "risk_register"), ("Verification Checklist", "verification_checklist")]
    for title_text, key in action_blocks:
        items = result.get(key) or []
        if items:
            block = [_p(title_text, h2)] + _bullets(list(items), small, max_items=7, limit=460)
            story.append(KeepTogether(block[:3]))
            story.extend(block[3:])

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _polish_pdf_report(result: dict[str, Any]) -> None:
    reports = result.setdefault("reports", {})
    pdf, error = _build_polished_pdf_base64(result)
    if pdf:
        reports["pdf_base64"] = pdf
        reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
        reports["pdf_style"] = "client_ready_polished_v2"
    elif error:
        reports.setdefault("pdf_error", error)


def polish_express_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result

    for item in result.get("sections", []) or []:
        item["evidence"] = _unique(list(item.get("evidence", []) or []))
        item["findings"] = _unique(list(item.get("findings", []) or []))
        item["unavailable"] = _unique(list(item.get("unavailable", []) or []))

    code = _section(result, "code_audit")
    ci = _section(result, "ci_cd")
    velocity = _section(result, "velocity_complexity")
    deps = _section(result, "dependency_health")
    arch = _section(result, "architecture_debt")
    arch_evidence = " ".join((arch or {}).get("evidence", []) or [])
    limited = _notes_limited(code) or _notes_limited(ci) or _notes_limited(velocity)

    if code and _notes_limited(code):
        code["findings"] = [note for note in code.get("findings", []) if "No recent pull-request evidence" not in note]
        code["evidence"] = [note for note in code.get("evidence", []) if "No recent pull-request evidence" not in note]
        code["evidence"].insert(0, "Commit and pull-request metadata were unavailable in this run; missing metadata is not treated as proof of direct-to-main work.")
        code["score"] = max(int(code.get("score", 0)), 55)
        code["status"] = "yellow"

    if ci and (_notes_limited(ci) or "Repository root contains .github/." in arch_evidence):
        if any("No CI/CD workflow" in note or "No GitHub Actions workflow" in note for note in ci.get("evidence", []) + ci.get("findings", [])):
            ci["findings"] = [note for note in ci.get("findings", []) if "No CI/CD workflow" not in note]
            ci["evidence"] = [note for note in ci.get("evidence", []) if "No GitHub Actions workflow" not in note and "No CI/CD workflow" not in note]
            ci["evidence"].insert(0, "CI/CD file metadata was unavailable or incomplete in this run; missing workflow metadata is not treated as proof that CI is absent.")
            ci["score"] = max(int(ci.get("score", 0)), 50)
            ci["status"] = "yellow"

    if velocity and limited:
        velocity["evidence"] = [note for note in velocity.get("evidence", []) if "0 commits over" not in note and "0 PRs / 0 commits" not in note]
        velocity["evidence"].insert(0, "Velocity and PR traceability are degraded because commit or PR metadata was unavailable in this run.")
        velocity["score"] = max(int(velocity.get("score", 0)), 55)
        velocity["status"] = "yellow"

    if deps:
        deps["evidence"] = _unique(deps.get("evidence", []))
        deps["findings"] = _unique(deps.get("findings", []))

    if limited:
        result["assessment_quality"] = "degraded_metadata"
        result["executive_summary"] += " Some GitHub metadata was unavailable, so affected sections are degraded rather than final negative evidence."
        all_findings: list[str] = []
        for item in result.get("sections", []) or []:
            all_findings.extend(item.get("findings", []) or [])
        result["findings"] = _unique(all_findings)

    _polish_pdf_report(result)
    return result
