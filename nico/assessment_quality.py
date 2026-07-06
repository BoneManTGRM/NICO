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


def _p(text: Any, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_clean_text(text)).replace("\n", "<br/>"), style)


def _bullets(items: list[str], style: Any, max_items: int = 8) -> list[Any]:
    if not items:
        return [_p("No evidence returned.", style)]
    flowables: list[Any] = []
    for item in items[:max_items]:
        flowables.append(_p(f"- {_clean_text(item, 650)}", style))
    if len(items) > max_items:
        flowables.append(_p(f"- {len(items) - max_items} additional item(s) omitted from PDF; see Markdown/HTML for full detail.", style))
    return flowables


def _draw_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO - authorized assessment - evidence-bound - human review required")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.33 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build_polished_pdf_base64(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        return None, f"PDF polish unavailable because reportlab is not installed: {exc}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.72 * inch,
        title="NICO Express Technical Health Assessment",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("NicoTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    subtitle = ParagraphStyle("NicoSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5, leading=14, textColor=colors.HexColor("#334155"), spaceAfter=8)
    h2 = ParagraphStyle("NicoH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#0f172a"), spaceBefore=12, spaceAfter=6)
    body = ParagraphStyle("NicoBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12.5, textColor=colors.HexColor("#1f2937"), spaceAfter=5)
    small = ParagraphStyle("NicoSmall", parent=body, fontSize=8.1, leading=10.5, textColor=colors.HexColor("#475569"), spaceAfter=3)
    callout = ParagraphStyle("NicoCallout", parent=body, fontName="Helvetica-Bold", fontSize=9.4, leading=12.5, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=8, spaceAfter=10)

    generated = result.get("generated_at") or "Not specified"
    repo = result.get("repository") or "Not specified"
    maturity = result.get("maturity_signal") or {}
    quality = result.get("assessment_quality") or "standard"
    sections = result.get("sections") or []

    story: list[Any] = [
        _p("NICO Express Technical Health Assessment", title),
        _p(f"Repository: {repo}", subtitle),
        _p(f"Generated: {generated} | Client: {result.get('client_name') or 'Not specified'} | Project: {result.get('project_name') or 'Not specified'}", subtitle),
        _p("Human review is required before client-facing delivery. Missing evidence is shown as unavailable, not invented.", callout),
    ]

    summary_rows = [
        ["Maturity", _clean_text(maturity.get("level") or "Unknown"), "Score", _clean_text(maturity.get("score") or "N/A")],
        ["Assessment quality", _clean_text(quality), "Coverage target", _clean_text((result.get("coverage_targets") or {}).get("express_technical_health_assessment", {}).get("target") or "90-95%")],
    ]
    summary_table = Table(summary_rows, colWidths=[1.45 * inch, 2.0 * inch, 1.05 * inch, 2.25 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story += [summary_table, Spacer(1, 0.16 * inch), _p("Executive Summary", h2), _p(result.get("executive_summary") or "No executive summary returned.", body)]

    semaphore = result.get("maturity_semaphore") or {}
    if semaphore:
        story.append(_p("Maturity Semaphore", h2))
        sem_rows = [[_p("Signal", small), _p("Status", small)]] + [[_p(key, small), _p(value, small)] for key, value in semaphore.items()]
        sem_table = Table(sem_rows, colWidths=[2.2 * inch, 4.55 * inch], repeatRows=1)
        sem_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ffffff")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [sem_table, Spacer(1, 0.12 * inch)]

    if sections:
        story.append(_p("Section Scorecard", h2))
        rows: list[list[Any]] = [[_p("Section", small), _p("Status", small), _p("Score", small), _p("Summary", small)]]
        for item in sections:
            rows.append([_p(item.get("label") or item.get("id"), small), _p((item.get("status") or "unknown").upper(), small), _p(f"{item.get('score', 'N/A')}/100", small), _p(item.get("summary") or "", small)])
        score_table = Table(rows, colWidths=[1.8 * inch, 0.8 * inch, 0.75 * inch, 3.4 * inch], repeatRows=1)
        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for row_idx, item in enumerate(sections, start=1):
            table_style.append(("TEXTCOLOR", (1, row_idx), (2, row_idx), colors.HexColor(_status_color(item.get("status", "")))))
            if row_idx % 2 == 0:
                table_style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#f8fafc")))
        score_table.setStyle(TableStyle(table_style))
        story += [score_table, PageBreak()]

    for item in sections:
        status = str(item.get("status") or "unknown").upper()
        story.append(_p(f"{item.get('label') or item.get('id')} - {status} {item.get('score', 'N/A')}/100", h2))
        story.append(_p(item.get("summary") or "", body))
        story.append(_p("Evidence", subtitle))
        story.extend(_bullets(list(item.get("evidence", []) or []), small, max_items=7))
        if item.get("findings"):
            story.append(_p("Findings", subtitle))
            story.extend(_bullets(list(item.get("findings", []) or []), small, max_items=5))
        if item.get("unavailable"):
            story.append(_p("Unavailable data", subtitle))
            story.extend(_bullets(list(item.get("unavailable", []) or []), small, max_items=5))
        story.append(Spacer(1, 0.08 * inch))

    for title_text, key in [("Quick Wins", "quick_wins"), ("Medium-Term Plan", "medium_term_plan"), ("Resourcing Recommendation", "resourcing_recommendation"), ("Risk Register", "risk_register"), ("Verification Checklist", "verification_checklist")]:
        items = result.get(key) or []
        if items:
            story.append(_p(title_text, h2))
            story.extend(_bullets(list(items), small, max_items=8))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _polish_pdf_report(result: dict[str, Any]) -> None:
    reports = result.setdefault("reports", {})
    pdf, error = _build_polished_pdf_base64(result)
    if pdf:
        reports["pdf_base64"] = pdf
        reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
        reports["pdf_style"] = "client_ready_polished"
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
