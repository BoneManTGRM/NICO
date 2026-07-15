from __future__ import annotations

import base64
import html
import io
from typing import Any

EXPRESS_BASE_REPORT_VERSION = "professional_express_base_v13"
_PATCH_MARKER = "_nico_express_report_base_v13"
_DUPLICATE_FINDING_MARKERS = (
    "source-file footprint is large",
    "total source loc is high",
    "at least one function has very high cyclomatic complexity",
    "function-level complexity risk is concentrated",
    "complexity and high churn overlap",
    "large-file and complexity risk overlap",
    "ownership is concentrated",
    "complexity hotspot:",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in _list(values):
        text = _text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _display_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [dict(item) for item in _list(result.get("sections")) if isinstance(item, dict)]
    architecture_seen = False
    for section in sections:
        section_id = str(section.get("id") or "")
        findings = _unique(section.get("findings"))
        if section_id == "architecture_debt":
            architecture_seen = True
        elif section_id == "velocity_complexity" and architecture_seen:
            findings = [
                item for item in findings
                if not any(marker in item.lower() for marker in _DUPLICATE_FINDING_MARKERS)
            ]
        section["display_findings"] = findings
        section["display_evidence"] = _unique(section.get("evidence"))
        section["display_unavailable"] = _unique(section.get("unavailable"))
    return sections


def _decision_summary(result: dict[str, Any]) -> dict[str, Any]:
    repairs = _dict(result.get("repair_intelligence"))
    candidates = [item for item in _list(repairs.get("candidates")) if isinstance(item, dict)]
    actions = _list(_dict(result.get("repair_action_summary")).get("top_actions")) or result.get("quick_wins") or []
    sections = _display_sections(result)
    clean = [
        f"{item.get('label')}: {item.get('score')}/100"
        for item in sections
        if str(item.get("status") or "").lower() == "green" and isinstance(item.get("score"), (int, float))
    ]
    advisories = [
        _text(item.get("title"))
        for item in _list(repairs.get("advisories"))
        if isinstance(item, dict) and _text(item.get("title"))
    ]
    return {
        "top_risks": [
            f"P{item.get('rank', '?')} {item.get('title')} — priority {item.get('priority_score')}"
            for item in candidates[:4]
        ],
        "top_actions": [_text(item) for item in actions if _text(item)][:4],
        "verified_controls": clean[:6],
        "planning_advisories": advisories[:4],
        "repair_candidate_count": int(repairs.get("candidate_count") or len(candidates)),
        "code_suggestion_count": int(repairs.get("code_suggestion_count") or 0),
    }


def _build_base_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.56 * inch,
        leftMargin=0.56 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.68 * inch,
        title="NICO Express Technical Health Assessment",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    hero = ParagraphStyle("ExpressHero", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=31, leading=34, textColor=colors.white, alignment=1)
    hero_sub = ParagraphStyle("ExpressHeroSub", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#67e8f9"), alignment=1)
    h2 = ParagraphStyle("ExpressH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5, keepWithNext=True)
    h3 = ParagraphStyle("ExpressH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.7, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3, keepWithNext=True)
    body = ParagraphStyle("ExpressBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.1, leading=10.3, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("ExpressSmall", parent=body, fontSize=7.25, leading=8.9, textColor=colors.HexColor("#475569"), spaceAfter=2)
    label = ParagraphStyle("ExpressLabel", parent=small, fontName="Helvetica-Bold", fontSize=7, textColor=colors.HexColor("#64748b"))
    callout = ParagraphStyle("ExpressCallout", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=7)
    warn = ParagraphStyle("ExpressWarn", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=7)

    def p(value: Any, style: Any, limit: int = 1000) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def bullets(values: Any, max_items: int = 5, limit: int = 600) -> list[Any]:
        items = _unique(values)
        rows = [p(f"- {item}", small, limit) for item in items[:max_items]]
        if len(items) > max_items:
            rows.append(p(f"- {len(items) - max_items} additional item(s) retained in Markdown/JSON evidence.", small))
        return rows

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbeafe"))
        canvas.line(document.leftMargin, 0.49 * inch, document.pagesize[0] - document.rightMargin, 0.49 * inch)
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.31 * inch, "NICO Express - evidence-bound - human review required")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.31 * inch, f"Page {document.page}")
        canvas.restoreState()

    maturity = _dict(result.get("maturity_signal"))
    sections = _display_sections(result)
    decision = _decision_summary(result)
    verdict = "HUMAN REVIEW REQUIRED" if result.get("human_review_required", True) else "REVIEW STATUS UNKNOWN"

    hero_table = Table(
        [[p("NICO", hero)], [p("POWERED BY REPARODYNAMICS", hero_sub)], [p("EXPRESS TECHNICAL HEALTH ASSESSMENT", hero_sub)]],
        colWidths=[7.08 * inch],
    )
    hero_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    metadata = Table(
        [
            [p("Repository", label), p(result.get("repository"), small), p("Client", label), p(result.get("client_name") or "Not provided", small)],
            [p("Project", label), p(result.get("project_name") or "Not provided", small), p("Generated", label), p(result.get("generated_at") or "Not recorded", small)],
        ],
        colWidths=[0.82 * inch, 2.72 * inch, 0.68 * inch, 2.86 * inch],
    )
    metadata.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    metrics = Table(
        [[
            [p("MATURITY", label), p(maturity.get("level") or "Unknown", h3)],
            [p("SCORE", label), p(f"{maturity.get('score', 'N/A')}/100", h3)],
            [p("REPAIR CANDIDATES", label), p(str(decision["repair_candidate_count"]), h3)],
            [p("DELIVERY", label), p(verdict, small)],
        ]],
        colWidths=[1.45 * inch, 1.35 * inch, 1.65 * inch, 2.63 * inch],
    )
    metrics.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story: list[Any] = [
        hero_table,
        Spacer(1, 0.08 * inch),
        metadata,
        Spacer(1, 0.08 * inch),
        metrics,
        Spacer(1, 0.08 * inch),
        p("This report separates current verified controls, actionable risks, planning advisories, and human-review gates. Missing evidence is never converted into a clean result.", callout),
        p("Executive Summary", h2),
        p(result.get("executive_summary") or "No executive summary was returned.", body, 1100),
        p("Decision Summary", h2),
    ]

    decision_rows = [[p("Decision area", label), p("Current result", label)]]
    decision_rows.append([p("Highest-priority risks", small), p("; ".join(decision["top_risks"]) or "No ranked risk returned.", small, 900)])
    decision_rows.append([p("Immediate actions", small), p("; ".join(decision["top_actions"]) or "Human review of the evidence-bound report.", small, 900)])
    decision_rows.append([p("Verified controls", small), p("; ".join(decision["verified_controls"]) or "No verified control summary returned.", small, 900)])
    decision_rows.append([p("Planning advisories", small), p("; ".join(decision["planning_advisories"]) or "None ranked as defects.", small, 900)])
    decision_table = Table(decision_rows, colWidths=[1.45 * inch, 5.63 * inch], repeatRows=1)
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfeff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#155e75")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(decision_table)

    story.append(p("Section Scorecard", h2))
    score_rows = [[p("Area", label), p("Status", label), p("Score", label), p("Summary", label)]]
    for item in sections:
        score = "Not scored" if item.get("status") == "gray" else str(item.get("score", "N/A"))
        score_rows.append([
            p(item.get("label") or item.get("id"), small),
            p(str(item.get("status") or "unknown").upper(), small),
            p(score, small),
            p(item.get("summary"), small, 260),
        ])
    score_table = Table(score_rows, colWidths=[1.62 * inch, 0.83 * inch, 0.58 * inch, 4.05 * inch], repeatRows=1)
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(score_table)

    story.append(PageBreak())
    story.append(p("Technical Evidence by Area", h2))
    for item in sections:
        if item.get("id") in {"trust_readiness", "client_acceptance"}:
            continue
        block = [
            p(f"{item.get('label') or item.get('id')} - {str(item.get('status') or 'unknown').upper()} {item.get('score', 'N/A')}/100", h3),
            p(item.get("summary"), body, 850),
        ]
        story.extend(KeepTogether(block))
        if item.get("display_evidence"):
            story.append(p("Key evidence", label))
            story.extend(bullets(item.get("display_evidence"), 4))
        if item.get("display_findings"):
            story.append(p("Actionable findings", label))
            story.extend(bullets(item.get("display_findings"), 3))
        if item.get("display_unavailable"):
            story.append(p("Unavailable or human-context evidence", label))
            story.extend(bullets(item.get("display_unavailable"), 3))
        story.append(Spacer(1, 0.05 * inch))

    story.append(p("Action Plan and Review Gate", h2))
    story.append(p("Immediate actions", h3))
    story.extend(bullets(decision["top_actions"] or result.get("quick_wins"), 6))
    story.append(p("Medium-term plan", h3))
    story.extend(bullets(result.get("medium_term_plan"), 6))
    story.append(p("Required review boundary", h3))
    story.append(p("NICO generated evidence and report-only suggestions. It did not approve the assessment, modify the repository, create a branch, commit, pull request, or deployment. An authorized human must review the exact evidence before client delivery.", warn, 1100))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def build_express_base_pdf(result: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        payload = _build_base_pdf(result)
        result["express_report_base"] = {
            "status": "complete",
            "version": EXPRESS_BASE_REPORT_VERSION,
            "decision_summary": True,
            "duplicate_finding_suppression": True,
            "full_evidence_retained_in_markdown_json": True,
            "human_review_required": True,
            "code_changes_applied": False,
        }
        return base64.b64encode(payload).decode("ascii"), None
    except Exception as exc:  # pragma: no cover - fail closed at rendering boundary
        return None, f"Express v13 base PDF failed: {type(exc).__name__}: {exc}"


def install_express_report_base_v13() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": EXPRESS_BASE_REPORT_VERSION}
    setattr(build_express_base_pdf, _PATCH_MARKER, True)
    setattr(build_express_base_pdf, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = build_express_base_pdf
    return {
        "status": "installed",
        "version": EXPRESS_BASE_REPORT_VERSION,
        "decision_summary": True,
        "duplicate_finding_suppression": True,
        "report_only": True,
    }


__all__ = [
    "EXPRESS_BASE_REPORT_VERSION",
    "build_express_base_pdf",
    "install_express_report_base_v13",
]
