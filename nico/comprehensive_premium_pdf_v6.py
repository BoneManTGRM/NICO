from __future__ import annotations

import html
import io
from typing import Any, Iterable


def _text(value: Any, limit: int = 5000) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


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
    title = ParagraphStyle("P6-Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=31, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"), spaceAfter=14)
    subtitle = ParagraphStyle("P6-Subtitle", parent=styles["BodyText"], fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=5)
    h1 = ParagraphStyle("P6-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceBefore=7, spaceAfter=9)
    h2 = ParagraphStyle("P6-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=7, spaceAfter=5)
    h3 = ParagraphStyle("P6-H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.2, leading=13, textColor=colors.HexColor("#0f172a"), spaceBefore=5, spaceAfter=3)
    body = ParagraphStyle("P6-Body", parent=styles["BodyText"], fontSize=9, leading=12.8, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("P6-Small", parent=body, fontSize=7.2, leading=9.5, textColor=colors.HexColor("#475569"))
    warning = ParagraphStyle("P6-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=8, spaceBefore=7, spaceAfter=9)

    class PremiumDoc(SimpleDocTemplate):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._outline = 0

        def afterFlowable(self, flowable: Any) -> None:
            if isinstance(flowable, Paragraph) and flowable.style.name in {"P6-H1", "P6-H2"}:
                self._outline += 1
                key = f"heading-{self._outline}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(flowable.getPlainText(), key, level=0 if flowable.style.name == "P6-H1" else 1, closed=False)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    def bullets(values: Iterable[Any], limit: int = 12) -> list[Paragraph]:
        return [p(f"• {_text(item, 900)}", small) for item in list(values)[:limit] if _text(item)]

    def table(rows: list[list[Any]], widths: list[float], header: bool = True, font_size: float = 6.8) -> LongTable:
        converted = [[p(cell, small) for cell in row] for row in rows]
        result = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT", splitByRow=1)
        commands: list[tuple[Any, ...]] = [
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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
        canvas.drawString(.55 * inch, .36 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 44)} · DRAFT")
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def score_chart(sections: list[dict[str, Any]]) -> Drawing:
        drawing = Drawing(500, max(60, 26 * len(sections) + 15))
        for index, section in enumerate(sections):
            y = drawing.height - 22 - index * 26
            score = section.get("score_value")
            drawing.add(String(0, y + 3, _text(section.get("label"), 31), fontName="Helvetica", fontSize=7.1, fillColor=colors.HexColor("#334155")))
            drawing.add(Rect(155, y, 285, 11, fillColor=colors.HexColor("#e2e8f0"), strokeColor=None))
            if isinstance(score, int):
                fill = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}.get(section.get("score_tone"), "#64748b")
                drawing.add(Rect(155, y, 2.85 * score, 11, fillColor=colors.HexColor(fill), strokeColor=None))
                label = str(score)
            else:
                drawing.add(Rect(155, y, 285, 11, fillColor=colors.HexColor("#f1f5f9"), strokeColor=None))
                label = "N/S"
            drawing.add(String(448, y + 2, label, fontName="Helvetica-Bold", fontSize=7.7, fillColor=colors.HexColor("#0f172a")))
        return drawing

    doc = PremiumDoc(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, title="NICO Comprehensive Technical Assessment", author="NICO", invariant=1)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    detailed = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    executive = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    weights = [item for item in assessment.get("scoring_weights") or [] if isinstance(item, dict)]

    story: list[Any] = [
        Spacer(1, .85 * inch),
        p("NICO", ParagraphStyle("P6-Brand", parent=title, fontSize=18, textColor=colors.HexColor("#0284c7"))),
        p("Comprehensive Technical Assessment", title),
        p(identity.get("repository"), subtitle),
        Spacer(1, .22 * inch),
        p(f"Immutable commit: {_text(identity.get('commit_sha'))}", subtitle),
        p(f"Run ID: {_text(identity.get('run_id'))}", subtitle),
        p(f"Generated: {generated_at}", subtitle),
        Spacer(1, .3 * inch),
        p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning),
        PageBreak(),
        p("Executive Decision Brief", h1),
        p(
            f"NICO assessed {_text(identity.get('repository'))} at immutable commit {_text(identity.get('commit_sha'))}. "
            + (f"Weighted technical maturity is {maturity.get('score_band_label')} ({score}/100). " if isinstance(score, int) else "Technical maturity is not scored. ")
            + f"{limitations.get('individual_limitation_records', 0)} distinct evidence limitation record(s) remain. Technical score, evidence assurance, and client-delivery authorization are independent; an authorized human must approve the exact package.",
            body,
        ),
        p("Decision dashboard", h2),
        table([
            ["Dimension", "Result", "Decision meaning"],
            ["Technical maturity", f"{maturity.get('score_band_label')} · {score}/100" if isinstance(score, int) else "NOT SCORED", "Weighted engineering health using scored controls only"],
            ["Evidence readiness", maturity.get("evidence_readiness_score") or "Pending", "Completeness and reliability of required evidence"],
            ["Human review", "REQUIRED", "Findings and assumptions require disposition"],
            ["Client delivery", "NOT AUTHORIZED", "Exact-package approval required"],
        ], [1.35 * inch, 1.55 * inch, 4.55 * inch]),
        Spacer(1, .1 * inch),
        p("Package identity", h2),
        table([
            ["Run ID", identity.get("run_id")],
            ["Commit", identity.get("commit_sha")],
            ["Evidence ledger", identity.get("evidence_ledger_id")],
            ["Final PDF pages", final_page_count if final_page_count is not None else "Calculated after rendering"],
        ], [1.3 * inch, 6.15 * inch], header=False),
        PageBreak(),
        p("Technical Scorecard and Weighting", h1),
        score_chart(sections),
        Spacer(1, .1 * inch),
    ]

    score_rows = [["Control", "Weight", "Score", "Contribution", "Assurance"]]
    for row in weights:
        score_rows.append([
            row.get("control"),
            f"{row.get('weight_percent')}%",
            f"{row.get('technical_score')}/100" if row.get("included") else "NOT SCORED",
            row.get("weighted_contribution") if row.get("included") else "Excluded",
            row.get("assurance") or "Pending",
        ])
    story += [table(score_rows, [2.1 * inch, .75 * inch, 1 * inch, 1.05 * inch, 1.5 * inch]), p("Scoring rule", h2), p("Controls with incomplete required evidence are excluded from the technical maturity calculation rather than treated as zero. Remaining control weights are normalized across scored controls. Evidence assurance remains visible and independent.", body)]

    story += [PageBreak(), p("Executive Risk Register", h1)]
    risk_rows = [["Priority", "Consolidated risk", "Business impact", "Confidence", "Recommended action"]]
    for item in executive:
        risk_rows.append([item.get("priority"), item.get("title"), item.get("impact"), item.get("confidence"), item.get("recommendation")])
    if len(risk_rows) == 1:
        risk_rows.append(["—", "No consolidated technical risk retained", "Human review remains required", "—", "Verify evidence completeness"])
    story += [table(risk_rows, [.55 * inch, 1.55 * inch, 1.65 * inch, .75 * inch, 2.95 * inch], font_size=6.4)]

    architecture = next((item for item in sections if item.get("id") == "architecture_debt"), {})
    story += [PageBreak(), p("Architecture and Complexity", h1), p("Measured profile", h2), *bullets(architecture.get("evidence") or [], 12), p("Priority hotspots", h2), *bullets(architecture.get("findings") or [], 8)]

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
            block += [p("Findings", h3), *bullets(section.get("findings") or [], 6)]
        if section.get("unavailable"):
            block += [p("Evidence limitations", h3), *bullets(section.get("unavailable") or [], 6)]
        story += [CondPageBreak(2.15 * inch), KeepTogether(block), HRFlowable(width="100%", thickness=.4, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=4)]

    story += [PageBreak(), p("Detailed Findings Register", h1), p("The executive register consolidates themes. The records below retain unique exact-location evidence for technical review.", body)]
    for finding in detailed:
        story += [
            CondPageBreak(2.35 * inch),
            p(f"{finding.get('priority')} · {finding.get('title')}", h2),
            table([
                ["Category", finding.get("category")],
                ["Location", finding.get("location")],
                ["Evidence", finding.get("evidence")],
                ["Impact", finding.get("impact")],
                ["Owner / effort", f"{finding.get('owner_role')} · {finding.get('effort')}"],
                ["Recommendation", finding.get("recommendation")],
                ["Acceptance", finding.get("acceptance_criteria")],
            ], [1.15 * inch, 6.3 * inch], header=False, font_size=6.8),
            Spacer(1, .08 * inch),
        ]
    if not detailed:
        story.append(p("No structured technical finding was retained; human review remains required.", warning))

    story += [PageBreak(), p("Six-Month Execution Roadmap", h1)]
    for window in roadmap:
        if not isinstance(window, dict):
            continue
        story.append(p(f"{window.get('window')} — {window.get('objective')}", h2))
        rows = [["Work package", "Owner", "Effort", "Acceptance", "Expected impact"]]
        for package in window.get("work_packages") or []:
            if not isinstance(package, dict):
                continue
            rows.append([package.get("title"), package.get("owner_role"), package.get("effort"), "; ".join(package.get("acceptance_criteria") or []), package.get("expected_impact")])
        if len(rows) > 1:
            story += [table(rows, [1.4 * inch, 1.05 * inch, .65 * inch, 2.5 * inch, 1.85 * inch], font_size=6.3), Spacer(1, .1 * inch)]

    story += [PageBreak(), p("Staffing and Sequencing", h1)]
    staffing_rows = [["Sequence", "Role", "Focus", "Indicative capacity"]]
    for item in staffing:
        if isinstance(item, dict):
            staffing_rows.append([item.get("sequence"), item.get("role"), item.get("focus"), item.get("estimated_load") or "Requires planning"])
    if len(staffing_rows) == 1:
        staffing_rows.append(["—", "Stakeholder decision required", "Staffing evidence unavailable", "Not committed"])
    story += [table(staffing_rows, [.65 * inch, 1.55 * inch, 3.65 * inch, 1.6 * inch]), p("Cost boundary", h2), p("Labor rates, contract structure, geographic mix, and budget ceilings remain stakeholder decisions.", body)]

    story += [PageBreak(), p("Evidence Appendix", h1), p("Bounded decision-relevant evidence is rendered here; the complete machine-readable ledger is included in JSON and CSV artifacts.", body)]
    for index, stage in enumerate(stages, 1):
        story += [
            CondPageBreak(2.5 * inch),
            p(f"A{index}. {stage.get('title')} — {_text(stage.get('status')).upper()}", h2),
            p(f"Stage ID: {stage.get('stage_id')}", small),
            p(stage.get("summary"), body),
            p(f"Evidence records: {len(stage.get('evidence') or [])} · Findings: {len(stage.get('findings') or [])} · Limitations: {len(stage.get('unavailable') or [])}", small),
            *bullets(stage.get("evidence") or [], 8),
        ]
        if stage.get("findings"):
            story += [p("Findings", h3), *bullets(stage.get("findings") or [], 5)]
        if stage.get("unavailable"):
            story += [p("Unavailable or limited evidence", h3), *bullets(stage.get("unavailable") or [], 5)]
        story.append(HRFlowable(width="100%", thickness=.35, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=5))

    story += [PageBreak(), p("Human Review and Acceptance Gate", h1), p("The automated assessment is complete only as a draft.", body), *bullets([
        "Verify exact repository, run, commit, evidence-ledger, customer, and project identities.",
        "Triage every material, review-required, failed, timed-out, and unavailable analyzer result.",
        "Confirm JSON, CSV, Markdown, HTML, and PDF show the same score, band, assurance, limitation accounting, and delivery status.",
        "Validate business context, requirements, roadmap, staffing, effort, and cost assumptions.",
        "Approve or reject the exact immutable report package before delivery.",
    ], 10), p("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", warning)]

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
