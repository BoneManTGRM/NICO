from __future__ import annotations

import html
import io
from typing import Any

REPORT_FLOWABLE_SAFETY_VERSION = "nico.report_flowable_safety.v1"
_INSTALLED = False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _texts(value: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        text = _text(item)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            output.append(text)
    return output


def _document_styles(prefix: str) -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(f"{prefix}Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=colors.HexColor("#0f172a"), spaceAfter=8),
        "h2": ParagraphStyle(f"{prefix}H2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5, keepWithNext=True),
        "h3": ParagraphStyle(f"{prefix}H3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=9.7, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3, keepWithNext=True),
        "body": ParagraphStyle(f"{prefix}Body", parent=base["BodyText"], fontName="Helvetica", fontSize=8.1, leading=10.3, textColor=colors.HexColor("#334155"), spaceAfter=3),
        "small": ParagraphStyle(f"{prefix}Small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.25, leading=8.9, textColor=colors.HexColor("#475569"), spaceAfter=2),
        "label": ParagraphStyle(f"{prefix}Label", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=colors.HexColor("#64748b"), spaceAfter=1),
        "callout": ParagraphStyle(f"{prefix}Callout", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8.1, leading=10.3, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=7),
        "warning": ParagraphStyle(f"{prefix}Warning", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8.1, leading=10.3, textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=7),
    }


def _paragraph(value: Any, style: Any, limit: int = 1000) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_text(value, limit)), style)


def _bullets(values: Any, style: Any, *, max_items: int = 6, limit: int = 620) -> list[Any]:
    rows = [_paragraph(f"- {item}", style, limit) for item in _texts(values)[:max_items]]
    count = len(_texts(values))
    if count > max_items:
        rows.append(_paragraph(f"- {count - max_items} additional item(s) retained in Markdown/JSON evidence.", style))
    return rows


def _table(rows: list[list[Any]], widths: list[Any], *, header_color: str = "#e0f2fe") -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _footer(label: str):
    def draw(canvas: Any, document: Any) -> None:
        from reportlab.lib import colors
        from reportlab.lib.units import inch

        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbeafe"))
        canvas.line(document.leftMargin, 0.49 * inch, document.pagesize[0] - document.rightMargin, 0.49 * inch)
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.31 * inch, label)
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.31 * inch, f"Page {document.page}")
        canvas.restoreState()

    return draw


def _safe_express_base_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer
    from nico import express_report_base_v13 as express_module

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.56 * inch, leftMargin=0.56 * inch, topMargin=0.52 * inch, bottomMargin=0.68 * inch, title="NICO Express Technical Health Assessment", author="NICO", invariant=1)
    styles = _document_styles("SafeExpress")
    p = _paragraph
    sections = express_module._display_sections(result)
    decision = express_module._decision_summary(result)
    maturity = _dict(result.get("maturity_signal"))

    story: list[Any] = [
        p("NICO Express Technical Health Assessment", styles["title"]),
        p("Powered by Reparodynamics - evidence-bound - human review required", styles["callout"]),
        _table([
            [p("Repository", styles["label"]), p(result.get("repository"), styles["small"]), p("Generated", styles["label"]), p(result.get("generated_at") or "Not recorded", styles["small"])],
            [p("Maturity", styles["label"]), p(maturity.get("level") or "Unknown", styles["small"]), p("Score", styles["label"]), p(f"{maturity.get('score', 'N/A')}/100", styles["small"])],
        ], [0.78 * inch, 2.75 * inch, 0.68 * inch, 2.87 * inch], header_color="#f8fafc"),
        Spacer(1, 0.08 * inch),
        p("Executive Summary", styles["h2"]),
        p(result.get("executive_summary") or "No executive summary was returned.", styles["body"], 1200),
        p("Decision Summary", styles["h2"]),
        _table([
            [p("Decision area", styles["label"]), p("Current result", styles["label"])],
            [p("Highest-priority risks", styles["small"]), p("; ".join(decision["top_risks"]) or "No ranked risk returned.", styles["small"], 900)],
            [p("Immediate actions", styles["small"]), p("; ".join(decision["top_actions"]) or "Human review of the evidence-bound report.", styles["small"], 900)],
            [p("Verified controls", styles["small"]), p("; ".join(decision["verified_controls"]) or "No verified control summary returned.", styles["small"], 900)],
            [p("Planning advisories", styles["small"]), p("; ".join(decision["planning_advisories"]) or "None ranked as defects.", styles["small"], 900)],
        ], [1.45 * inch, 5.63 * inch], header_color="#ecfeff"),
        p("Section Scorecard", styles["h2"]),
    ]
    score_rows = [[p("Area", styles["label"]), p("Status", styles["label"]), p("Score", styles["label"]), p("Summary", styles["label"])]]
    for item in sections:
        score_rows.append([
            p(item.get("label") or item.get("id"), styles["small"]),
            p(str(item.get("status") or "unknown").upper(), styles["small"]),
            p("Not scored" if item.get("status") == "gray" else str(item.get("score", "N/A")), styles["small"]),
            p(item.get("summary"), styles["small"], 280),
        ])
    story.append(_table(score_rows, [1.62 * inch, 0.83 * inch, 0.64 * inch, 3.99 * inch]))
    story.extend([PageBreak(), p("Technical Evidence by Area", styles["h2"])])
    for item in sections:
        if item.get("id") in {"trust_readiness", "client_acceptance"}:
            continue
        story.append(p(f"{item.get('label') or item.get('id')} - {str(item.get('status') or 'unknown').upper()} {item.get('score', 'N/A')}/100", styles["h3"]))
        story.append(p(item.get("summary"), styles["body"], 850))
        if item.get("display_evidence"):
            story.append(p("Key evidence", styles["label"]))
            story.extend(_bullets(item.get("display_evidence"), styles["small"], max_items=4))
        if item.get("display_findings"):
            story.append(p("Actionable findings", styles["label"]))
            story.extend(_bullets(item.get("display_findings"), styles["small"], max_items=3))
        if item.get("display_unavailable"):
            story.append(p("Unavailable or human-context evidence", styles["label"]))
            story.extend(_bullets(item.get("display_unavailable"), styles["small"], max_items=3))
        story.append(Spacer(1, 0.05 * inch))
    story.extend([
        p("Action Plan and Review Gate", styles["h2"]),
        p("Immediate actions", styles["h3"]),
        *_bullets(decision["top_actions"] or result.get("quick_wins"), styles["small"], max_items=6),
        p("Medium-term plan", styles["h3"]),
        *_bullets(result.get("medium_term_plan"), styles["small"], max_items=6),
        p("NICO generated evidence and report-only suggestions. It did not approve the assessment, modify the repository, create a branch, commit, pull request, or deployment. An authorized human must review the exact evidence before client delivery.", styles["warning"], 1100),
    ])
    footer = _footer("NICO Express - evidence-bound - human review required")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _safe_mid_pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer
    from nico import mid_report_professional_v3 as mid_module

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.55 * inch, leftMargin=0.55 * inch, topMargin=0.52 * inch, bottomMargin=0.68 * inch, title="NICO Mid Technical Assessment", author="NICO", invariant=1)
    styles = _document_styles("SafeMid")
    p = _paragraph
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    coverage = _dict(payload.get("evidence_coverage"))
    technical = mid_module._technical_sections(payload)
    context = mid_module._context_sections(payload)

    story: list[Any] = [
        p("NICO MID TECHNICAL ASSESSMENT", styles["title"]),
        p("DRAFT - snapshot-bound - evidence-bound - human review required", styles["warning"]),
        _table([
            [p("Repository", styles["label"]), p(payload.get("repository"), styles["small"]), p("Run", styles["label"]), p(payload.get("run_id"), styles["small"])],
            [p("Maturity", styles["label"]), p(decision.get("technical_maturity"), styles["small"]), p("Technical score", styles["label"]), p(f"{decision.get('technical_score')}/100", styles["small"])],
            [p("Evidence coverage", styles["label"]), p(f"{coverage.get('percent', 0)}%", styles["small"]), p("Delivery", styles["label"]), p("HUMAN REVIEW REQUIRED", styles["small"])],
        ], [0.88 * inch, 2.65 * inch, 0.88 * inch, 2.71 * inch], header_color="#f8fafc"),
        p("Decision Summary", styles["h2"]),
        p("The technical score is calculated from seven weighted technical sections. The five stakeholder and product-context modules are unscored and do not lower the score. Evidence coverage measures availability, not maturity.", styles["callout"], 1400),
        p("Verified strengths", styles["h3"]),
        *_bullets(decision.get("verified_strengths"), styles["small"], max_items=5),
        p("Primary score constraints", styles["h3"]),
    ]
    for item in decision.get("primary_score_constraints") or []:
        story.append(p(f"{item.get('label')} - {item.get('score')}/100: {item.get('primary_reason')}", styles["body"], 900))
    story.extend([p("Recommended actions", styles["h3"]), *_bullets(decision.get("recommended_actions"), styles["small"], max_items=5), p("Weighted Technical Scorecard", styles["h2"])])
    rows = [[p("Area", styles["label"]), p("Truth", styles["label"]), p("Score", styles["label"]), p("Weight", styles["label"]), p("Contribution", styles["label"])]]
    for row in integrity.get("weighted_rows") or []:
        rows.append([
            p(row.get("label"), styles["small"]), p(row.get("truth_status"), styles["small"]), p(str(row.get("score")), styles["small"]), p(f"{row.get('weight')}%", styles["small"]), p(str(row.get("weighted_contribution")), styles["small"]),
        ])
    story.append(_table(rows, [2.18 * inch, 1.72 * inch, 0.55 * inch, 0.58 * inch, 0.87 * inch]))
    story.append(p(f"Calculated score={integrity.get('calculated_score')}; reported score={integrity.get('reported_score')}; match={integrity.get('score_match')}. Human-context modules and coverage percentage do not directly change this score.", styles["small"]))
    story.extend([PageBreak(), p("Technical Findings and Evidence", styles["h2"])])
    for section in technical:
        score = mid_module._score(section.get("score"))
        story.append(p(f"{section.get('label')} - {score if score is not None else 'Not scored'}/100", styles["h3"]))
        story.append(p(f"Truth status: {section.get('truth_status')} | Confidence: {section.get('confidence') or 'evidence-bound'}", styles["small"]))
        story.append(p(section.get("summary"), styles["body"], 900))
        if section.get("findings"):
            story.append(p("Findings", styles["label"]))
            story.extend(_bullets(section.get("findings"), styles["small"], max_items=5))
        limitations = _texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))
        if limitations:
            story.append(p("Material limitations", styles["label"]))
            story.extend(_bullets(limitations, styles["small"], max_items=5))
        if section.get("scope_disclosures"):
            story.append(p("Scope disclosures", styles["label"]))
            story.extend(_bullets(section.get("scope_disclosures"), styles["small"], max_items=3))
        story.append(Spacer(1, 0.05 * inch))

    repairs = _dict(payload.get("repair_intelligence"))
    candidates = [item for item in _list(repairs.get("candidates")) if isinstance(item, dict)]
    if candidates:
        story.extend([PageBreak(), p("Prioritized Repair Intelligence", styles["h2"]), p("Repairs are report-only candidates. NICO did not change the assessed repository, create a branch, commit, pull request, or deployment.", styles["callout"])])
        repair_rows = [[p("Rank", styles["label"]), p("Finding", styles["label"]), p("Severity", styles["label"]), p("Priority", styles["label"]), p("Effort", styles["label"])]]
        for item in candidates[:10]:
            repair_rows.append([p(f"P{item.get('rank', '?')}", styles["small"]), p(item.get("title"), styles["small"], 260), p(str(item.get("severity") or "unknown").upper(), styles["small"]), p(str(item.get("priority_score") or "N/A"), styles["small"]), p(str(item.get("effort") or "unknown").upper(), styles["small"])])
        story.append(_table(repair_rows, [0.42 * inch, 3.92 * inch, 0.78 * inch, 0.72 * inch, 0.72 * inch], header_color="#ecfeff"))
        for item in candidates[:6]:
            story.append(p(f"P{item.get('rank', '?')} - {item.get('title')}", styles["h3"]))
            story.append(p(f"Recommended action: {item.get('recommended_action')}", styles["body"], 1000))
            story.append(p(f"Verification: {'; '.join(_texts(item.get('test_plan')))}", styles["small"], 800))

    if context:
        story.append(p("Human-Context Modules", styles["h2"]))
        story.append(p("These modules are valuable for a Mid assessment but remain unscored until submitted context is validated by a human reviewer.", styles["callout"]))
        context_rows = [[p("Module", styles["label"]), p("Status", styles["label"]), p("Submitted evidence / next step", styles["label"])]]
        for section in context:
            context_rows.append([p(section.get("label"), styles["small"]), p(section.get("truth_status"), styles["small"]), p("; ".join(_texts(section.get("evidence"))) or "No validated external context attached.", styles["small"], 500)])
        story.append(_table(context_rows, [1.6 * inch, 1.35 * inch, 4.17 * inch], header_color="#f1f5f9"))

    story.append(p("Review by Exception", styles["h2"]))
    story.append(p(f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}.", styles["small"]))
    for item in payload.get("deduplicated_review_exceptions") or []:
        story.append(p(f"{str(item.get('severity') or 'medium').upper()} - {item.get('title') or item.get('category')}", styles["h3"]))
        story.append(p(item.get("reason"), styles["body"], 800))
        story.extend(_bullets(item.get("blockers"), styles["small"], max_items=5))

    story.extend([
        p("Integrity and Safety Boundary", styles["h2"]),
        *_bullets([
            f"Source identity SHA-256: {payload.get('source_identity_sha256')}",
            f"Review packet SHA-256: {_dict(payload.get('review_packet')).get('review_packet_sha256')}",
            f"Snapshot commit SHA: {payload.get('snapshot_commit_sha')}",
            "Unsupported claims permitted: 0.",
            "Human review is required before approval or client delivery.",
            "NICO did not modify the assessed repository and cannot automatically apply report suggestions.",
        ], styles["small"], max_items=8),
    ])
    footer = _footer("NICO Mid - snapshot-bound - evidence-bound - human review required")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_report_flowable_safety() -> dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"status": "already_installed", "version": REPORT_FLOWABLE_SAFETY_VERSION}
    from nico import express_report_base_v13 as express_module
    from nico import mid_assessment_report as mid_report_module

    express_module._build_base_pdf = _safe_express_base_pdf
    mid_report_module._pdf = _safe_mid_pdf
    _INSTALLED = True
    return {
        "status": "installed",
        "version": REPORT_FLOWABLE_SAFETY_VERSION,
        "express_renderer_safe": True,
        "mid_renderer_safe": True,
        "human_review_required": True,
        "code_changes_applied": False,
    }


__all__ = [
    "REPORT_FLOWABLE_SAFETY_VERSION",
    "install_report_flowable_safety",
]
