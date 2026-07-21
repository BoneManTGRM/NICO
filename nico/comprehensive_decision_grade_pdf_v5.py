from __future__ import annotations

import html
import io
import re
from typing import Any, Iterable

from nico.comprehensive_decision_grade_model_v5 import _score_band, _text
from nico.comprehensive_decision_grade_markdown_v5 import _decision_summary


def _build_pdf(
    identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]], staffing: list[dict[str, Any]],
    limitations: dict[str, int], generated_at: str, final_page_count: int | None = None,
) -> bytes:
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable, KeepTogether, LongTable, PageBreak, Paragraph,
        SimpleDocTemplate, Spacer, TableStyle,
    )

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DG-Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"), spaceAfter=14)
    subtitle = ParagraphStyle("DG-Subtitle", parent=styles["BodyText"], fontSize=10.5, leading=15, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=6)
    h1 = ParagraphStyle("DG-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=10)
    h2 = ParagraphStyle("DG-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=colors.HexColor("#075985"), spaceBefore=8, spaceAfter=6)
    h3 = ParagraphStyle("DG-H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#0f172a"), spaceBefore=5, spaceAfter=3)
    body = ParagraphStyle("DG-Body", parent=styles["BodyText"], fontSize=9.1, leading=13.2, textColor=colors.HexColor("#334155"), spaceAfter=6)
    small = ParagraphStyle("DG-Small", parent=body, fontSize=7.3, leading=9.8, textColor=colors.HexColor("#475569"))
    warning = ParagraphStyle("DG-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=9, spaceBefore=8, spaceAfter=10)

    class DecisionGradeDoc(SimpleDocTemplate):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._outline = 0

        def afterFlowable(self, flowable: Any) -> None:
            if isinstance(flowable, Paragraph) and flowable.style.name in {"DG-H1", "DG-H2"}:
                self._outline += 1
                key = f"heading-{self._outline}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(flowable.getPlainText(), key, level=0 if flowable.style.name == "DG-H1" else 1, closed=False)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 6000)), style)

    def bullets(values: Iterable[Any], limit: int = 16) -> list[Paragraph]:
        return [p(f"• {_text(item, 900)}", small) for item in list(values)[:limit] if _text(item)]

    def table(rows: list[list[Any]], widths: list[float], header: bool = True, font_size: float = 7.0) -> LongTable:
        converted = [[p(cell, small) for cell in row] for row in rows]
        t = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands: list[tuple[Any, ...]] = [
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(commands))
        return t

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState(); canvas.setFont("Helvetica", 7); canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .38 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 50)} · DRAFT")
        canvas.drawRightString(7.95 * inch, .38 * inch, f"Page {doc.page}"); canvas.restoreState()

    def score_chart(sections: list[dict[str, Any]]) -> Drawing:
        scored = [s for s in sections if isinstance(s.get("score_value"), int)]
        drawing = Drawing(500, max(70, 27 * len(scored) + 18))
        for i, section in enumerate(scored):
            y = drawing.height - 24 - i * 27; score = int(section["score_value"])
            fill = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}.get(section.get("score_tone"), "#64748b")
            drawing.add(String(0, y + 3, _text(section.get("label"), 30), fontName="Helvetica", fontSize=7.3, fillColor=colors.HexColor("#334155")))
            drawing.add(Rect(155, y, 285, 12, fillColor=colors.HexColor("#e2e8f0"), strokeColor=None))
            drawing.add(Rect(155, y, 2.85 * score, 12, fillColor=colors.HexColor(fill), strokeColor=None))
            drawing.add(String(448, y + 2, str(score), fontName="Helvetica-Bold", fontSize=8, fillColor=colors.HexColor("#0f172a")))
        return drawing

    def architecture_flow() -> Drawing:
        drawing = Drawing(500, 92); labels = ["Repository", "Immutable Snapshot", "Evidence Workers", "Scoring", "Human Review"]
        for i, label in enumerate(labels):
            x = i * 102; drawing.add(Rect(x, 34, 82, 34, rx=7, ry=7, fillColor=colors.HexColor("#e0f2fe"), strokeColor=colors.HexColor("#0284c7")))
            drawing.add(String(x + 41, 48, label, fontName="Helvetica-Bold", fontSize=6.7, textAnchor="middle", fillColor=colors.HexColor("#075985")))
            if i < len(labels) - 1:
                drawing.add(Line(x + 85, 51, x + 97, 51, strokeColor=colors.HexColor("#0284c7"), strokeWidth=1.5)); drawing.add(Polygon([x + 97, 51, x + 92, 55, x + 92, 47], fillColor=colors.HexColor("#0284c7"), strokeColor=None))
        drawing.add(String(250, 10, "Authorized delivery remains outside the automated boundary", fontName="Helvetica-Oblique", fontSize=7.5, textAnchor="middle", fillColor=colors.HexColor("#92400e")))
        return drawing

    doc = DecisionGradeDoc(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.58 * inch, bottomMargin=.62 * inch, title="NICO Comprehensive Technical Assessment", author="NICO", invariant=1)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score")); sections = [s for s in assessment.get("sections") or [] if isinstance(s, dict)]; findings = [f for f in assessment.get("findings_register") or [] if isinstance(f, dict)]
    story: list[Any] = [
        Spacer(1, .95 * inch), p("NICO", ParagraphStyle("DG-Brand", parent=title, fontSize=18, textColor=colors.HexColor("#0284c7"))),
        p("Comprehensive Technical Assessment", title), p(identity.get("repository"), subtitle), Spacer(1, .25 * inch),
        p(f"Immutable commit: {_text(identity.get('commit_sha'))}", subtitle), p(f"Run ID: {_text(identity.get('run_id'))}", subtitle), p(f"Generated: {generated_at}", subtitle),
        Spacer(1, .35 * inch), p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning), PageBreak(),
        p("Executive Decision Brief", h1), p(_decision_summary(identity, assessment, limitations), body), p("Decision Boundary", h2),
        p("Technical score, evidence assurance, and client-delivery authorization are independent. Missing evidence remains visible and cannot become a passing claim.", body),
    ]
    dashboard = [["Dimension", "Result", "Meaning"], ["Technical maturity", f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED", "Score-derived engineering health"], ["Evidence readiness", maturity.get("evidence_readiness_score") or "Pending", "Completeness and reliability"], ["Human review", "REQUIRED", "Findings and assumptions need disposition"], ["Client delivery", "NOT AUTHORIZED", "Exact-package approval required"]]
    story += [table(dashboard, [1.35 * inch, 1.55 * inch, 4.55 * inch]), Spacer(1, .12 * inch), p("Final package metadata", h2), table([["Run ID", identity.get("run_id")], ["Commit", identity.get("commit_sha")], ["Evidence ledger", identity.get("evidence_ledger_id")], ["Final PDF pages", final_page_count if final_page_count is not None else "Calculated after rendering"]], [1.3 * inch, 6.15 * inch], header=False)]
    story += [PageBreak(), p("Report Navigation", h1)] + [p(f"{i}. {name}", body) for i, name in enumerate(["Assessment dashboard", "Technical scorecard", "Executive risk register", "Architecture and complexity", "CI/CD and security", "Detailed findings", "Six-month roadmap", "Staffing", "Evidence appendix", "Human review gate"], 1)]
    story += [PageBreak(), p("Canonical Technical Scorecard", h1), score_chart(sections), Spacer(1, .12 * inch)]
    rows = [["Control", "Score", "Band", "Assurance", "Decision summary"]] + [[s.get("label"), f"{s.get('score_value')}/100" if isinstance(s.get("score_value"), int) else "NOT SCORED", s.get("score_band_label"), s.get("assurance_label"), s.get("summary")] for s in sections]
    story += [table(rows, [1.45 * inch, .62 * inch, .78 * inch, 1.05 * inch, 3.55 * inch]), Spacer(1, .12 * inch), p("Limitation Accounting", h2), table([["Metric", "Count", "Definition"], ["Stages with limitations", limitations["stages_with_limitations"], "At least one limitation"], ["Distinct limitations", limitations["individual_limitation_records"], "Deduplicated package records"], ["Score-affecting", limitations["score_affecting_records"], "Section finding or gap"], ["Informational", limitations["informational_records"], "Disclosure without independent score effect"]], [1.55 * inch, .75 * inch, 5.15 * inch])]
    story += [PageBreak(), p("Executive Risk Register", h1)]
    risk = [["Priority", "Finding", "Business impact", "Confidence", "Recommended action"]] + [[f.get("priority"), f.get("title"), f.get("impact"), f.get("confidence"), f.get("recommendation")] for f in findings[:12]]
    if len(risk) == 1: risk.append(["—", "No structured finding retained", "Human review remains required", "—", "Verify evidence completeness"])
    story.append(table(risk, [.55 * inch, 1.6 * inch, 1.7 * inch, .75 * inch, 2.85 * inch], font_size=6.5))
    story += [PageBreak(), p("Architecture and Complexity", h1), architecture_flow()]
    architecture = next((s for s in sections if s.get("id") == "architecture_debt"), {})
    story += [p("Measured complexity profile", h2), *bullets(architecture.get("evidence") or [], 12), p("Named hotspots", h2), *bullets(architecture.get("findings") or [], 12)]
    story += [PageBreak(), p("CI/CD, Security, and Dependency Evidence", h1)]
    for sid in ("ci_cd", "dependency_health", "secrets_review", "static_analysis"):
        section = next((s for s in sections if s.get("id") == sid), None)
        if not section: continue
        block = [p(f"{section.get('label')} — {section.get('technical_score_display')} · {section.get('assurance_label')}", h2), p(section.get("summary"), body), *bullets(section.get("evidence") or [], 8)]
        if section.get("findings"): block += [p("Findings", h3), *bullets(section.get("findings") or [], 8)]
        if section.get("unavailable"): block += [p("Evidence limitations", h3), *bullets(section.get("unavailable") or [], 8)]
        story += [KeepTogether(block), HRFlowable(width="100%", thickness=.4, color=colors.HexColor("#cbd5e1"), spaceBefore=5, spaceAfter=5)]
    story += [PageBreak(), p("Detailed Findings Register", h1)]
    for index, finding in enumerate(findings):
        story += [p(f"{finding.get('priority')} · {finding.get('title')}", h2), table([["Category", finding.get("category")], ["Location", finding.get("location")], ["Evidence", finding.get("evidence")], ["Impact", finding.get("impact")], ["Owner / effort", f"{finding.get('owner_role')} · {finding.get('effort')}"], ["Recommendation", finding.get("recommendation")], ["Acceptance", finding.get("acceptance_criteria")]], [1.15 * inch, 6.3 * inch], header=False, font_size=6.9), Spacer(1, .1 * inch)]
        if index and index % 3 == 0: story.append(PageBreak())
    if not findings: story.append(p("No structured technical finding was retained; human review remains required.", warning))
    story += [PageBreak(), p("Six-Month Execution Roadmap", h1)]
    for window in roadmap:
        if not isinstance(window, dict): continue
        story.append(p(f"{window.get('window')} — {window.get('objective')}", h2))
        roadmap_rows = [["Work package", "Owner", "Effort", "Acceptance", "Expected impact"]] + [[pkg.get("title"), pkg.get("owner_role"), pkg.get("effort"), "; ".join(pkg.get("acceptance_criteria") or []), pkg.get("expected_impact")] for pkg in window.get("work_packages") or [] if isinstance(pkg, dict)]
        if len(roadmap_rows) > 1: story += [table(roadmap_rows, [1.4 * inch, 1.05 * inch, .65 * inch, 2.5 * inch, 1.85 * inch], font_size=6.4), Spacer(1, .12 * inch)]
    story += [PageBreak(), p("Staffing and Sequencing", h1)]
    staffing_rows = [["Sequence", "Role", "Focus", "Indicative capacity"]] + [[s.get("sequence"), s.get("role"), s.get("focus"), s.get("estimated_load") or "Requires planning"] for s in staffing if isinstance(s, dict)]
    if len(staffing_rows) == 1: staffing_rows.append(["—", "Stakeholder decision required", "Staffing evidence unavailable", "Not committed"])
    story += [table(staffing_rows, [.65 * inch, 1.55 * inch, 3.65 * inch, 1.6 * inch]), p("Cost boundary", h2), p("Labor rates, contract structure, geographic mix, and budget ceilings remain stakeholder decisions.", body)]
    story += [PageBreak(), p("Evidence Appendix", h1), p("Bounded decision-relevant evidence is rendered here; the complete machine-readable ledger is included in JSON and CSV artifacts.", body)]
    for index, stage in enumerate(stages, 1):
        story += [PageBreak(), p(f"A{index}. {stage['title']} — {stage['status'].upper()}", h1), p(f"Stage ID: {stage['stage_id']}", small), p(stage["summary"], body), p(f"Evidence records: {len(stage.get('evidence') or [])} · Findings: {len(stage.get('findings') or [])} · Limitations: {len(stage.get('unavailable') or [])}", small), p("Retained evidence", h2), *bullets(stage.get("evidence") or [], 12)]
        if stage.get("findings"): story += [p("Findings", h2), *bullets(stage.get("findings") or [], 8)]
        if stage.get("unavailable"): story += [p("Unavailable or limited evidence", h2), *bullets(stage.get("unavailable") or [], 8)]
    story += [PageBreak(), p("Human Review and Acceptance Gate", h1), p("The automated assessment is complete only as a draft.", body), *bullets(["Verify exact repository, run, commit, evidence-ledger, customer, and project identities.", "Triage every material, review-required, failed, timed-out, and unavailable analyzer result.", "Confirm JSON, CSV, Markdown, HTML, and PDF show the same score, band, assurance, limitation accounting, and delivery status.", "Validate business context, requirements, roadmap, staffing, effort, and cost assumptions.", "Approve or reject the exact immutable report package before delivery."], 10), p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _pdf_with_final_count(
    identity: dict[str, Any], assessment: dict[str, Any], stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]], staffing: list[dict[str, Any]],
    limitations: dict[str, int], generated_at: str,
) -> tuple[bytes, int]:
    from pypdf import PdfReader
    first = _build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    count = len(PdfReader(io.BytesIO(first)).pages)
    final = _build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, count)
    final_count = len(PdfReader(io.BytesIO(final)).pages)
    if final_count != count:
        final = _build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, final_count)
        final_count = len(PdfReader(io.BytesIO(final)).pages)
    return final, final_count


__all__ = ["_build_pdf", "_pdf_with_final_count"]
