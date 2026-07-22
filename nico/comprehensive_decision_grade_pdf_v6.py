from __future__ import annotations

import html
import io
from typing import Any, Iterable

from nico.comprehensive_decision_grade_model_v5 import _score_band, _text
from nico.comprehensive_decision_grade_markdown_v5 import _decision_summary


def _build_pdf(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
    final_page_count: int | None = None,
) -> bytes:
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        CondPageBreak,
        HRFlowable,
        KeepTogether,
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DG6-Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=31, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"), spaceAfter=13)
    subtitle = ParagraphStyle("DG6-Subtitle", parent=styles["BodyText"], fontSize=10.3, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=5)
    h1 = ParagraphStyle("DG6-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=colors.HexColor("#0f172a"), spaceBefore=7, spaceAfter=8)
    h2 = ParagraphStyle("DG6-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.2, leading=15, textColor=colors.HexColor("#075985"), spaceBefore=6, spaceAfter=4)
    h3 = ParagraphStyle("DG6-H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.7, leading=12, textColor=colors.HexColor("#0f172a"), spaceBefore=4, spaceAfter=2)
    body = ParagraphStyle("DG6-Body", parent=styles["BodyText"], fontSize=8.7, leading=12.2, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("DG6-Small", parent=body, fontSize=7.0, leading=9.2, textColor=colors.HexColor("#475569"), spaceAfter=2)
    warning = ParagraphStyle("DG6-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=8, spaceBefore=7, spaceAfter=8)

    class DecisionGradeDoc(SimpleDocTemplate):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._outline = 0

        def afterFlowable(self, flowable: Any) -> None:
            if isinstance(flowable, Paragraph) and flowable.style.name in {"DG6-H1", "DG6-H2"}:
                self._outline += 1
                key = f"heading-{self._outline}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(flowable.getPlainText(), key, level=0 if flowable.style.name == "DG6-H1" else 1, closed=False)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 6000)), style)

    def bullets(values: Iterable[Any], limit: int = 12) -> list[Paragraph]:
        return [p(f"• {_text(item, 900)}", small) for item in list(values)[:limit] if _text(item)]

    def table(rows: list[list[Any]], widths: list[float], header: bool = True, font_size: float = 6.8) -> LongTable:
        converted = [[p(cell, small) for cell in row] for row in rows]
        result = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT", splitByRow=True)
        commands: list[tuple[Any, ...]] = [
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]
        if header:
            commands += [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        result.setStyle(TableStyle(commands))
        return result

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .36 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 50)} · DRAFT")
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def score_chart(sections: list[dict[str, Any]]) -> Drawing:
        scored = [item for item in sections if isinstance(item.get("score_value"), int)]
        drawing = Drawing(500, max(60, 24 * len(scored) + 14))
        for index, section in enumerate(scored):
            y = drawing.height - 21 - index * 24
            score = int(section["score_value"])
            fill = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}.get(section.get("score_tone"), "#64748b")
            drawing.add(String(0, y + 2, _text(section.get("label"), 34), fontName="Helvetica", fontSize=7.0, fillColor=colors.HexColor("#334155")))
            drawing.add(Rect(160, y, 280, 10, fillColor=colors.HexColor("#e2e8f0"), strokeColor=None))
            drawing.add(Rect(160, y, 2.8 * score, 10, fillColor=colors.HexColor(fill), strokeColor=None))
            drawing.add(String(448, y + 1, str(score), fontName="Helvetica-Bold", fontSize=7.7, fillColor=colors.HexColor("#0f172a")))
        return drawing

    doc = DecisionGradeDoc(buffer, pagesize=letter, rightMargin=.52 * inch, leftMargin=.52 * inch, topMargin=.54 * inch, bottomMargin=.6 * inch, title="NICO Comprehensive Technical Assessment", author="NICO", invariant=1)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    findings = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    executive_risks = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    weights = [item for item in assessment.get("scoring_weight_table") or [] if isinstance(item, dict)]

    story: list[Any] = [
        Spacer(1, .9 * inch),
        p("NICO", ParagraphStyle("DG6-Brand", parent=title, fontSize=18, textColor=colors.HexColor("#0284c7"))),
        p("Comprehensive Technical Assessment", title),
        p(identity.get("repository"), subtitle),
        Spacer(1, .2 * inch),
        p(f"Immutable commit: {_text(identity.get('commit_sha'))}", subtitle),
        p(f"Run ID: {_text(identity.get('run_id'))}", subtitle),
        p(f"Generated: {generated_at}", subtitle),
        Spacer(1, .28 * inch),
        p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning),
        PageBreak(),
        p("Executive Decision Brief", h1),
        p(_decision_summary(identity, assessment, limitations), body),
        p("Decision Boundary", h2),
        p("Technical score, evidence assurance, and client-delivery authorization are independent. Unscored controls are excluded from weighted maturity rather than treated as zero.", body),
    ]
    dashboard = [
        ["Dimension", "Result", "Meaning"],
        ["Technical maturity", f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED", "Weighted engineering health across controls with sufficient technical evidence"],
        ["Evidence readiness", maturity.get("evidence_readiness_score") or "Pending", "Completeness and reliability of required evidence"],
        ["Human review", "REQUIRED", "Candidate validation and business disposition remain human responsibilities"],
        ["Client delivery", "NOT AUTHORIZED", "Exact-package approval required"],
    ]
    story += [
        table(dashboard, [1.35 * inch, 1.55 * inch, 4.55 * inch]),
        Spacer(1, .1 * inch),
        p("Final package metadata", h2),
        table([["Run ID", identity.get("run_id")], ["Commit", identity.get("commit_sha")], ["Evidence ledger", identity.get("evidence_ledger_id")], ["Final PDF pages", final_page_count if final_page_count is not None else "Calculated after rendering"]], [1.3 * inch, 6.15 * inch], header=False),
        PageBreak(),
        p("Technical Scorecard and Weighting", h1),
        score_chart(sections),
        Spacer(1, .08 * inch),
    ]
    score_rows = [["Control", "Score", "Band", "Assurance", "Decision summary"]] + [[section.get("label"), f"{section.get('score_value')}/100" if isinstance(section.get("score_value"), int) else "NOT SCORED", section.get("score_band_label"), section.get("assurance_label"), section.get("summary")] for section in sections]
    story.append(table(score_rows, [1.45 * inch, .62 * inch, .78 * inch, 1.05 * inch, 3.55 * inch]))
    story += [Spacer(1, .1 * inch), p("Weighted maturity calculation", h2)]
    weight_rows = [["Control", "Weight", "Score", "Contribution", "Included", "Assurance"]] + [[row.get("control"), row.get("weight_display"), row.get("score") if row.get("score") is not None else "—", row.get("weighted_contribution") if row.get("weighted_contribution") is not None else "—", "Yes" if row.get("included") else "No", row.get("assurance")] for row in weights]
    story.append(table(weight_rows, [1.75 * inch, .62 * inch, .62 * inch, .85 * inch, .58 * inch, 1.3 * inch], font_size=6.4))

    story += [PageBreak(), p("Executive Risk Register", h1), p("Consolidated decision risks only. Exact file-level instances remain in the technical findings register.", body)]
    risk_rows = [["Priority", "Consolidated risk", "Business impact", "Confidence", "Recommended action"]] + [[item.get("priority"), item.get("title"), item.get("impact"), item.get("confidence"), item.get("recommendation")] for item in executive_risks]
    if len(risk_rows) == 1:
        risk_rows.append(["—", "No consolidated technical risk retained", "Human review remains required", "—", "Verify evidence completeness"])
    story.append(table(risk_rows, [.55 * inch, 1.6 * inch, 1.75 * inch, .75 * inch, 2.8 * inch], font_size=6.5))

    architecture = next((item for item in sections if item.get("id") == "architecture_debt"), {})
    story += [PageBreak(), p("Architecture and Complexity", h1), p("Measured complexity profile", h2), *bullets(architecture.get("evidence") or [], 12), p("Highest-priority modules", h2)]
    architecture_findings = [item for item in findings if item.get("category") == "architecture"][:8]
    story += bullets([f"{item.get('title')} — {item.get('location')} — {item.get('evidence')}" for item in architecture_findings], 8)

    story += [PageBreak(), p("CI/CD, Security, and Dependency Evidence", h1)]
    for section_id in ("ci_cd", "dependency_health", "secrets_review", "static_analysis"):
        section = next((item for item in sections if item.get("id") == section_id), None)
        if not section:
            continue
        block = [
            p(f"{section.get('label')} — {section.get('technical_score_display')} · {section.get('assurance_label')}", h2),
            p(section.get("summary"), body),
            *bullets(section.get("evidence") or [], 7),
        ]
        if section.get("findings"):
            block += [p("Findings", h3), *bullets(section.get("findings") or [], 5)]
        if section.get("unavailable"):
            block += [p("Evidence limitations", h3), *bullets(section.get("unavailable") or [], 5)]
        story += [KeepTogether(block), HRFlowable(width="100%", thickness=.35, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=4)]

    story += [PageBreak(), p("Technical Findings Register", h1), p("Candidate status and priority are explicit. Unverified medium-severity candidates are P2 until human validation establishes higher business impact.", body)]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        grouped.setdefault(_text(finding.get("category")) or "other", []).append(finding)
    for category, category_findings in grouped.items():
        story.append(p(category.replace("_", " ").title(), h2))
        rows = [["Priority", "Finding", "Location", "Evidence / confidence", "Action"]]
        for finding in category_findings:
            rows.append([
                finding.get("priority"),
                finding.get("title"),
                finding.get("location"),
                f"{finding.get('evidence')} · confidence={finding.get('confidence')}",
                finding.get("recommendation"),
            ])
        story += [table(rows, [.52 * inch, 1.65 * inch, 1.55 * inch, 1.65 * inch, 2.08 * inch], font_size=6.1), Spacer(1, .1 * inch), CondPageBreak(1.4 * inch)]

    story += [PageBreak(), p("Six-Month Execution Roadmap", h1)]
    for window in roadmap:
        if not isinstance(window, dict):
            continue
        story.append(p(f"{window.get('window')} — {window.get('objective')}", h2))
        roadmap_rows = [["Work package", "Owner", "Effort", "Acceptance", "Expected impact"]] + [[package.get("title"), package.get("owner_role"), package.get("effort"), "; ".join(package.get("acceptance_criteria") or []), package.get("expected_impact")] for package in window.get("work_packages") or [] if isinstance(package, dict)]
        if len(roadmap_rows) > 1:
            story += [table(roadmap_rows, [1.4 * inch, 1.05 * inch, .65 * inch, 2.5 * inch, 1.85 * inch], font_size=6.4), Spacer(1, .1 * inch)]

    story += [PageBreak(), p("Staffing and Sequencing", h1)]
    staffing_rows = [["Sequence", "Role", "Focus", "Indicative capacity"]] + [[item.get("sequence"), item.get("role"), item.get("focus"), item.get("estimated_load") or "Requires planning"] for item in staffing if isinstance(item, dict)]
    if len(staffing_rows) == 1:
        staffing_rows.append(["—", "Stakeholder decision required", "Staffing evidence unavailable", "Not committed"])
    story += [table(staffing_rows, [.65 * inch, 1.55 * inch, 3.65 * inch, 1.6 * inch]), p("Cost boundary", h2), p("Labor rates, contract structure, geographic mix, and budget ceilings remain stakeholder decisions.", body)]

    story += [PageBreak(), p("Evidence Appendix", h1), p("Bounded decision-relevant evidence is rendered here; the complete machine-readable ledger is included in JSON and CSV artifacts.", body)]
    for index, stage in enumerate(stages, 1):
        story += [CondPageBreak(2.15 * inch), p(f"A{index}. {stage['title']} — {stage['status'].upper()}", h2), p(f"Stage ID: {stage['stage_id']} · Evidence: {len(stage.get('evidence') or [])} · Findings: {len(stage.get('findings') or [])} · Limitations: {len(stage.get('unavailable') or [])}", small), p(stage["summary"], body)]
        retained = list(stage.get("evidence") or [])[:6]
        if retained:
            story += [p("Retained evidence", h3), *bullets(retained, 6)]
        if stage.get("findings"):
            story += [p("Findings", h3), *bullets(stage.get("findings") or [], 4)]
        if stage.get("unavailable"):
            story += [p("Unavailable or limited evidence", h3), *bullets(stage.get("unavailable") or [], 4)]
        story.append(HRFlowable(width="100%", thickness=.3, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=5))

    story += [PageBreak(), p("Human Review and Acceptance Gate", h1), p("The automated assessment is complete only as a draft.", body), *bullets(["Verify exact repository, run, commit, evidence-ledger, customer, and project identities.", "Triage every material, review-required, failed, timed-out, and unavailable analyzer result.", "Confirm JSON, CSV, Markdown, HTML, and PDF show the same score, band, assurance, weighting, limitation accounting, and delivery status.", "Validate business context, requirements, roadmap, staffing, effort, and cost assumptions.", "Approve or reject the exact immutable report package before delivery."], 10), p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _pdf_with_final_count(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
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
