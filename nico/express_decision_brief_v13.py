from __future__ import annotations

import base64
import html
import io
from typing import Any, Callable

EXPRESS_DECISION_BRIEF_VERSION = "professional_report_v13_executive_brief"
_PATCH_MARKER = "_nico_express_decision_brief_v13"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u2014", "-").replace("\u2013", "-").split())


def _paragraph(value: Any, style: Any, limit: int = 1000) -> Any:
    from reportlab.platypus import Paragraph

    text = _text(value)
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return Paragraph(html.escape(text), style)


def _brief_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.5 * inch, bottomMargin=0.58 * inch, title="NICO Express Executive Decision Brief", author="NICO")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("BriefTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=24, textColor=colors.white, spaceAfter=6)
    subtitle = ParagraphStyle("BriefSubtitle", parent=styles["BodyText"], fontSize=9, leading=11.5, textColor=colors.HexColor("#cbd5e1"))
    h1 = ParagraphStyle("BriefH1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=7, spaceAfter=4, keepWithNext=True)
    body = ParagraphStyle("BriefBody", parent=styles["BodyText"], fontSize=8.2, leading=10.6, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("BriefSmall", parent=body, fontSize=7.2, leading=8.8, textColor=colors.HexColor("#475569"))
    label = ParagraphStyle("BriefLabel", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#334155"))
    callout = ParagraphStyle("BriefCallout", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#38bdf8"), borderWidth=0.7, borderPadding=7, spaceAfter=7)

    maturity = _dict(result.get("maturity_signal"))
    repairs = _dict(result.get("repair_intelligence"))
    candidates = [item for item in _list(repairs.get("candidates")) if isinstance(item, dict)]
    portfolio = _dict(repairs.get("portfolio"))
    severity = _dict(portfolio.get("severity_counts"))
    action_summary = _dict(result.get("repair_action_summary"))
    coverage = _dict(result.get("evidence_coverage"))
    sections = [item for item in _list(result.get("sections")) if isinstance(item, dict)]
    unavailable = sum(len(_list(item.get("unavailable"))) for item in sections)

    story: list[Any] = []
    banner = Table([[
        _paragraph("NICO EXPRESS", title),
        _paragraph("POWERED BY REPARODYNAMICS\nExecutive decision brief - evidence-bound - human review required", subtitle),
    ]], colWidths=[2.2 * inch, 4.6 * inch])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
    ]))
    story.extend([banner, Spacer(1, 0.1 * inch)])

    metrics = [[_paragraph("Maturity", label), _paragraph("Technical score", label), _paragraph("Evidence coverage", label), _paragraph("Delivery", label)], [
        _paragraph(maturity.get("level") or "Unclassified", h1),
        _paragraph(f"{maturity.get('score', 0)}/100", h1),
        _paragraph(f"{coverage.get('percent')}%" if coverage.get("calculated") else "Calculated after run", h1),
        _paragraph("Human review required", h1),
    ]]
    metric_table = Table(metrics, colWidths=[1.7 * inch] * 4)
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#cffafe")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([metric_table, _paragraph("What this means", h1), _paragraph(
        "The repository has strong current technical controls, but the report remains a review artifact rather than an automatic delivery decision. The ranked portfolio below separates immediate engineering risk from planning context and keeps suggested code report-only.",
        callout,
    )])

    story.append(_paragraph("Repair portfolio", h1))
    portfolio_rows = [[_paragraph("Candidates", label), _paragraph("Critical / High", label), _paragraph("Medium", label), _paragraph("Code candidates", label), _paragraph("Advisories", label)], [
        _paragraph(repairs.get("candidate_count", len(candidates)), body),
        _paragraph(_int(severity.get("critical")) + _int(severity.get("high")), body),
        _paragraph(_int(severity.get("medium")), body),
        _paragraph(repairs.get("code_suggestion_count", 0), body),
        _paragraph(len(_list(repairs.get("advisories"))), body),
    ]]
    portfolio_table = Table(portfolio_rows, colWidths=[1.36 * inch] * 5)
    portfolio_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, 1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(portfolio_table)

    story.append(_paragraph("Top actions", h1))
    actions = [str(item) for item in _list(action_summary.get("top_actions")) if str(item).strip()]
    if not actions:
        actions = [str(item.get("recommended_action") or "") for item in candidates[:4] if item.get("recommended_action")]
    for index, action in enumerate(actions[:4], 1):
        story.append(_paragraph(f"{index}. {action}", body))

    story.append(_paragraph("Why the score is not higher", h1))
    constraints: list[str] = []
    if unavailable:
        constraints.append(f"{unavailable} unavailable or limitation note(s) remain across scored and review sections.")
    if candidates:
        constraints.append(f"The top repair is {candidates[0].get('title')} at priority {candidates[0].get('priority_score')} with {str(candidates[0].get('effort') or 'unknown').lower()} effort.")
    if result.get("human_review_required"):
        constraints.append("Human review and client acceptance are intentionally not inferred from repository evidence.")
    constraints.append("Repository size is retained as planning context and is not scored as a defect by itself.")
    for item in constraints[:4]:
        story.append(_paragraph(f"- {item}", body))

    story.append(_paragraph("Top ranked repairs", h1))
    rows = [[_paragraph("Rank", label), _paragraph("Finding", label), _paragraph("Severity", label), _paragraph("Priority", label), _paragraph("Effort", label)]]
    for item in candidates[:5]:
        rows.append([
            _paragraph(f"P{item.get('rank', '?')}", small),
            _paragraph(item.get("title"), small, 300),
            _paragraph(str(item.get("severity") or "unknown").upper(), small),
            _paragraph(item.get("priority_score"), small),
            _paragraph(str(item.get("effort") or "unknown").upper(), small),
        ])
    repairs_table = Table(rows, colWidths=[0.42 * inch, 3.65 * inch, 0.75 * inch, 0.72 * inch, 0.9 * inch], repeatRows=1)
    repairs_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(repairs_table)
    story.append(Spacer(1, 0.08 * inch))
    story.append(_paragraph("Safety boundary: NICO did not edit, commit, push, deploy, or open a pull request against the assessed repository. Code candidates remain unverified until exact-context tests pass and a human approves implementation.", small))

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.28 * inch, "NICO Express executive decision brief - report only - human review required")
        canvas.drawRightString(letter[0] - document.rightMargin, 0.28 * inch, "Executive Brief")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def build_express_with_decision_brief(
    original: Callable[[dict[str, Any]], tuple[str | None, str | None]],
    result: dict[str, Any],
) -> tuple[str | None, str | None]:
    base, error = original(result)
    if not base or not isinstance(result.get("repair_intelligence"), dict):
        return base, error
    try:
        from pypdf import PdfReader, PdfWriter

        brief = _brief_pdf(result)
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(brief)).pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(base64.b64decode(base))).pages:
            writer.add_page(page)
        writer.add_metadata({
            "/Title": "NICO Express Technical Health Assessment",
            "/Author": "NICO",
            "/Subject": "Evidence-bound assessment with executive decision brief and report-only repair intelligence",
        })
        output = io.BytesIO()
        writer.write(output)
        result["express_decision_brief"] = {
            "status": "complete",
            "version": EXPRESS_DECISION_BRIEF_VERSION,
            "page_position": "first",
            "top_action_count": min(4, len(_list(_dict(result.get("repair_action_summary")).get("top_actions"))) or len(_list(_dict(result.get("repair_intelligence")).get("candidates")))),
            "score_changed": False,
            "report_only": True,
            "human_review_required": True,
            "code_changes_applied": False,
        }
        return base64.b64encode(output.getvalue()).decode("ascii"), None
    except Exception as exc:
        return None, f"Express executive decision brief failed: {type(exc).__name__}: {exc}"


def install_express_decision_brief_v13() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": EXPRESS_DECISION_BRIEF_VERSION}
    original = current

    def polished_pdf_with_brief(result: dict[str, Any]) -> tuple[str | None, str | None]:
        return build_express_with_decision_brief(original, result)

    setattr(polished_pdf_with_brief, _PATCH_MARKER, True)
    setattr(polished_pdf_with_brief, "_nico_previous", original)
    assessment_quality._build_polished_pdf_base64 = polished_pdf_with_brief
    assessment_quality.PDF_STYLE_VERSION = EXPRESS_DECISION_BRIEF_VERSION
    return {
        "status": "installed",
        "version": EXPRESS_DECISION_BRIEF_VERSION,
        "executive_decision_brief": True,
        "page_position": "first",
        "score_changed": False,
        "report_only": True,
        "automatic_application_allowed": False,
    }


__all__ = [
    "EXPRESS_DECISION_BRIEF_VERSION",
    "build_express_with_decision_brief",
    "install_express_decision_brief_v13",
]
