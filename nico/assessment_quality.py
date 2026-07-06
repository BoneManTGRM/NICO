from __future__ import annotations

import base64
import html
import io
import re
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
    return any(marker in lower for marker in ["github returned 403", "github returned 429", "api rate", "request limit", "abuse detection"])


def _notes_limited(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    notes = list(item.get("unavailable", []) or []) + list(item.get("evidence", []) or [])
    return any(_metadata_limited(str(note)) for note in notes)


def _friendly_note(value: Any) -> str:
    text = str(value or "").replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    lower = text.lower()
    if "github returned 403" in lower or "github returned 429" in lower or "api rate" in lower or "abuse detection" in lower:
        prefix = "GitHub metadata was rate-limited during this run."
        if "workflow" in lower or "ci/cd" in lower or ".github/workflows" in lower:
            return f"Workflow metadata was unavailable because GitHub rate-limited the request. Treat this section as degraded and rerun later or use authenticated GitHub access."
        if "pull" in lower or "pr" in lower:
            return f"Pull-request metadata was unavailable because GitHub rate-limited the request. Do not treat missing PR metadata as proof of direct-to-main work."
        if "commit" in lower:
            return f"Commit metadata was unavailable because GitHub rate-limited the request. Do not treat missing commit metadata as proof of inactivity."
        return f"{prefix} Rerun later or configure authenticated GitHub access for stronger confidence."
    text = re.sub(r"https?://\S+", "[link omitted]", text)
    text = re.sub(r"\{\s*\"documentation_url\".*", "GitHub returned a metadata access error; raw response omitted from client report.", text)
    return " ".join(text.split())


def _sanitize_list(items: list[Any]) -> list[str]:
    return _unique([_friendly_note(item) for item in items if _friendly_note(item)])


def _clean_text(value: Any, limit: int = 1200) -> str:
    text = _friendly_note(value)
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


def _client_verdict(result: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in result.get("sections", []) if isinstance(item, dict)]
    red = sum(1 for item in sections if item.get("status") == "red")
    unavailable = sum(len(item.get("unavailable", []) or []) for item in sections)
    degraded = result.get("assessment_quality") == "degraded_metadata" or any(_notes_limited(item) for item in sections)
    blockers: list[str] = []
    if red:
        blockers.append(f"{red} red section(s) need triage before client-final delivery.")
    if degraded:
        blockers.append("GitHub metadata was degraded; rerun with authenticated metadata access before firm claims.")
    if unavailable:
        blockers.append("Unavailable evidence remains disclosed and must be reviewed.")
    return {
        "status": "human_review_required" if blockers else "review_ready",
        "blockers": blockers,
        "red_sections": red,
        "unavailable_items": unavailable,
        "confidence": "limited" if degraded else "standard",
    }


def _p(text: Any, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_clean_text(text)).replace("\n", "<br/>"), style)


def _bullets(items: list[str], style: Any, max_items: int = 6) -> list[Any]:
    if not items:
        return [_p("No evidence returned.", style)]
    flowables: list[Any] = []
    for item in _sanitize_list(items)[:max_items]:
        flowables.append(_p(f"- {_clean_text(item, 520)}", style))
    if len(items) > max_items:
        flowables.append(_p(f"- {len(items) - max_items} additional item(s) omitted from PDF; use Markdown/HTML for full detail.", style))
    return flowables


def _draw_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO - powered by Reparodynamics - evidence-bound - human review required")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.33 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build_polished_pdf_base64(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        return None, f"PDF polish unavailable because reportlab is not installed: {exc}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.62 * inch, leftMargin=0.62 * inch, topMargin=0.58 * inch, bottomMargin=0.72 * inch, title="NICO Express Technical Health Assessment", author="NICO")
    styles = getSampleStyleSheet()
    brand = ParagraphStyle("Brand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=30, leading=33, textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    powered = ParagraphStyle("Powered", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=colors.HexColor("#0284c7"), spaceAfter=12, uppercase=True)
    title = ParagraphStyle("Title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=5)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#111827"), spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.8, leading=12.0, textColor=colors.HexColor("#334155"), spaceAfter=4)
    small = ParagraphStyle("Small", parent=body, fontSize=8.0, leading=10.6, textColor=colors.HexColor("#475569"), spaceAfter=2.5)
    callout = ParagraphStyle("Callout", parent=body, fontName="Helvetica-Bold", fontSize=9.1, leading=12, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=8, spaceAfter=10)
    warn = ParagraphStyle("Warn", parent=body, fontName="Helvetica-Bold", fontSize=9.0, leading=12, textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=8, spaceAfter=10)

    repo = result.get("repository") or "Not specified"
    generated = result.get("generated_at") or "Not specified"
    maturity = result.get("maturity_signal") or {}
    sections = [item for item in result.get("sections", []) if isinstance(item, dict)]
    verdict = _client_verdict(result)

    story: list[Any] = [
        _p("NICO", brand),
        _p("POWERED BY REPARODYNAMICS", powered),
        _p("Express Technical Health Assessment", title),
        _p(f"Repository: {repo}<br/>Client: {result.get('client_name') or 'Not specified'}<br/>Project: {result.get('project_name') or 'Not specified'}<br/>Generated: {generated}", body),
        _p("Human review is required before client-facing delivery. Missing evidence is shown as unavailable, not invented.", callout),
    ]
    if verdict["blockers"]:
        story.append(_p("Delivery verdict: human review required. " + " ".join(verdict["blockers"]), warn))

    summary_data = [
        [_p("Maturity", small), _p(str(maturity.get("level", "Unknown")), small), _p("Score", small), _p(str(maturity.get("score", "N/A")), small)],
        [_p("Confidence", small), _p(str(verdict["confidence"]), small), _p("Assessment quality", small), _p(str(result.get("assessment_quality") or "standard"), small)],
    ]
    table = Table(summary_data, colWidths=[1.05 * inch, 2.0 * inch, 1.2 * inch, 2.45 * inch])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [table, Spacer(1, 0.12 * inch), _p("Executive Summary", h2), _p(result.get("executive_summary") or "No executive summary returned.", body)]

    story.append(_p("Section Scorecard", h2))
    for item in sections:
        status = str(item.get("status") or "unknown").upper()
        score = item.get("score", "N/A")
        label = item.get("label") or item.get("id") or "Section"
        card = Table([[_p(f"{label}", h3), _p(f"{status} - {score}/100", h3)], [_p(item.get("summary") or "", small), _p("", small)]], colWidths=[4.65 * inch, 1.75 * inch])
        card.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe3ef")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")), ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor(_status_color(str(item.get("status") or "")))), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("SPAN", (0, 1), (1, 1)), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [card, Spacer(1, 0.07 * inch)]

    story.append(PageBreak())
    for item in sections:
        status = str(item.get("status") or "unknown").upper()
        score = item.get("score", "N/A")
        block: list[Any] = [_p(f"{item.get('label') or item.get('id')} - {status} {score}/100", h2), _p(item.get("summary") or "", body), _p("Evidence", h3)]
        block.extend(_bullets(list(item.get("evidence", []) or []), small, max_items=5))
        if item.get("findings"):
            block.append(_p("Findings", h3))
            block.extend(_bullets(list(item.get("findings", []) or []), small, max_items=4))
        if item.get("unavailable"):
            block.append(_p("Unavailable data", h3))
            block.extend(_bullets(list(item.get("unavailable", []) or []), small, max_items=4))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 0.08 * inch))

    for title_text, key in [("Quick Wins", "quick_wins"), ("Medium-Term Plan", "medium_term_plan"), ("Resourcing Recommendation", "resourcing_recommendation"), ("Risk Register", "risk_register"), ("Verification Checklist", "verification_checklist")]:
        items = result.get(key) or []
        if items:
            block = [_p(title_text, h2)]
            block.extend(_bullets(list(items), small, max_items=6))
            story.append(KeepTogether(block))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _polish_pdf_report(result: dict[str, Any]) -> None:
    reports = result.setdefault("reports", {})
    pdf, error = _build_polished_pdf_base64(result)
    if pdf:
        reports["pdf_base64"] = pdf
        reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
        reports["pdf_style"] = "client_ready_readable"
    elif error:
        reports.setdefault("pdf_error", error)


def polish_express_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result

    for item in result.get("sections", []) or []:
        item["evidence"] = _sanitize_list(list(item.get("evidence", []) or []))
        item["findings"] = _sanitize_list(list(item.get("findings", []) or []))
        item["unavailable"] = _sanitize_list(list(item.get("unavailable", []) or []))

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
        code["evidence"] = _unique(code["evidence"])
        code["score"] = max(int(code.get("score", 0)), 55)
        code["status"] = "yellow"

    if ci and (_notes_limited(ci) or "Repository root contains .github/." in arch_evidence):
        if any("No CI/CD workflow" in note or "No GitHub Actions workflow" in note for note in ci.get("evidence", []) + ci.get("findings", [])):
            ci["findings"] = [note for note in ci.get("findings", []) if "No CI/CD workflow" not in note]
            ci["evidence"] = [note for note in ci.get("evidence", []) if "No GitHub Actions workflow" not in note and "No CI/CD workflow" not in note]
            ci["evidence"].insert(0, "CI/CD file metadata was unavailable or incomplete in this run; missing workflow metadata is not treated as proof that CI is absent.")
            ci["evidence"] = _unique(ci["evidence"])
            ci["score"] = max(int(ci.get("score", 0)), 50)
            ci["status"] = "yellow"

    if velocity and limited:
        velocity["evidence"] = [note for note in velocity.get("evidence", []) if "0 commits over" not in note and "0 PRs / 0 commits" not in note]
        velocity["evidence"].insert(0, "Velocity and PR traceability are degraded because commit or PR metadata was unavailable in this run.")
        velocity["evidence"] = _unique(velocity["evidence"])
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

    result["client_delivery_verdict"] = _client_verdict(result)
    _polish_pdf_report(result)
    return result
