from __future__ import annotations

import html
import io
from typing import Any, Iterable


def _text(value: Any, limit: int = 5000) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


class _PdfStoryBuilder:
    def __init__(self, context: dict[str, Any]) -> None:
        self.c = context

    def cover_and_scorecard(self) -> list[Any]:
        c = self.c
        p, table, bullets, score_chart = c["p"], c["table"], c["bullets"], c["score_chart"]
        Spacer, PageBreak, ParagraphStyle = c["Spacer"], c["PageBreak"], c["ParagraphStyle"]
        colors, inch = c["colors"], c["inch"]
        identity, assessment, limitations = c["identity"], c["assessment"], c["limitations"]
        maturity, score_value, adjusted = c["maturity"], c["score_value"], c["adjusted"]
        postures, executive, sections, weights = c["postures"], c["executive"], c["sections"], c["weights"]
        story = [Spacer(1, .85 * inch), p("NICO", ParagraphStyle("P6-Brand", parent=c["title"], fontSize=18, textColor=colors.HexColor("#0284c7"))),
            p("Comprehensive Technical Assessment", c["title"]), p(identity.get("repository"), c["subtitle"]), Spacer(1, .22 * inch),
            p(f"Immutable commit: {_text(identity.get('commit_sha'))}", c["subtitle"]), p(f"Run ID: {_text(identity.get('run_id'))}", c["subtitle"]),
            p(f"Generated: {c['generated_at']}", c["subtitle"]), Spacer(1, .3 * inch),
            p(f"{assessment.get('delivery_status') or 'HUMAN REVIEW REQUIRED'} · CLIENT-READY RELEASE REQUIRES INTERNAL EXACT-PACKAGE APPROVAL", c["warning"]),
            PageBreak(), p("Executive Decision Brief", c["h1"]),
            p(f"NICO assessed {_text(identity.get('repository'))} at immutable commit {_text(identity.get('commit_sha'))}. "
              + (f"Weighted technical maturity is {maturity.get('score_band_label')} ({score_value}/100). " if isinstance(score_value, int) else "Technical maturity is not scored. ")
              + (f"Evidence-Adjusted readiness is {int(adjusted)}/100. " if isinstance(adjusted, (int, float)) else "Evidence-Adjusted readiness is not scored. ")
              + f"{limitations.get('individual_limitation_records', 0)} distinct evidence limitation record(s) remain. Technical score, evidence assurance, and client-delivery authorization are independent; an authorized internal reviewer must approve the exact package before client release.", c["body"]),
            p("Decision dashboard", c["h2"]),
            table([["Dimension", "Result", "Decision meaning / condition"],
                ["Technical maturity", f"{maturity.get('score_band_label')} · {score_value}/100" if isinstance(score_value, int) else "NOT SCORED", "Weighted engineering health using scored controls only"],
                ["Evidence-Adjusted", f"{int(adjusted)}/100" if isinstance(adjusted, (int, float)) else "NOT SCORED", "Evidence completeness constrains the technical signal"],
                ["Operate", (postures.get("operate") or {}).get("status") or "Conditional", "; ".join((postures.get("operate") or {}).get("conditions") or [])],
                ["Release", (postures.get("release") or {}).get("status") or "Conditional", "; ".join((postures.get("release") or {}).get("conditions") or [])],
                ["Client delivery", assessment.get("delivery_status") or "Human Review Required", (postures.get("client_delivery") or {}).get("required_next_action") or "Internal exact-package approval required"]], [1.35 * inch, 1.55 * inch, 4.55 * inch]),
            p("Top priority decisions", c["h2"]), *bullets([f"{item.get('title')} [{item.get('finding_id') or item.get('id')}]" for item in executive[:3]] or ["Complete exact-package human review."], 3),
            p("Package identity", c["h2"]), table([["Run ID", identity.get("run_id")], ["Commit", identity.get("commit_sha")], ["Evidence ledger", identity.get("evidence_ledger_id")], ["Final PDF pages", c["final_page_count"] if c["final_page_count"] is not None else "Calculated after rendering"]], [1.3 * inch, 6.15 * inch], header=False),
            PageBreak(), p("Technical Scorecard and Weighting", c["h1"]), score_chart(sections), Spacer(1, .1 * inch)]
        rows = [["Control", "Weight", "Score", "Contribution", "Assurance"]]
        rows.extend([row.get("control"), f"{row.get('weight_percent')}%", f"{row.get('technical_score')}/100" if row.get("included") else "NOT SCORED", row.get("weighted_contribution") if row.get("included") else "Excluded", row.get("assurance") or "Pending"] for row in weights)
        story.extend([table(rows, [2.1 * inch, .75 * inch, 1 * inch, 1.05 * inch, 1.5 * inch]), p("Scoring rule", c["h2"]), p("Controls with incomplete required evidence are excluded from the technical maturity calculation rather than treated as zero. Remaining control weights are normalized across scored controls. Evidence assurance remains visible and independent.", c["body"])])
        return story

    def evidence_and_verified_change(self) -> list[Any]:
        c = self.c
        p, table, bullets, PageBreak = c["p"], c["table"], c["bullets"], c["PageBreak"]
        health, sections = c["health"], c["sections"]
        story = [PageBreak(), p("Evidence Health Summary", c["h1"]), p(health.get("confidence_effect") or "Evidence remains review-gated.", c["body"]),
            p("Completed scanners", c["h2"]), *bullets(health.get("completed_scanners") or ["No structured scanner completion record retained"], 30)]
        rows = [["Scanner", "Status", "Required", "Affected categories", "Confidence impact", "Remediation"]]
        rows.extend([item.get("scanner"), item.get("status"), item.get("required"), ", ".join(item.get("affected_categories") or []), item.get("confidence_impact"), item.get("remediation")] for item in health.get("incomplete_scanners") or [] if isinstance(item, dict))
        if len(rows) == 1:
            rows.append(["—", "No incomplete structured record", "—", "—", "—", "Continue monitoring"])
        story.extend([p("Incomplete scanner records", c["h2"]), table(rows, [1.05 * c["inch"], .7 * c["inch"], .55 * c["inch"], 1.4 * c["inch"], 1.35 * c["inch"], 2.35 * c["inch"]], font_size=5.8)])
        return story

    def risk_architecture_and_controls(self) -> list[Any]:
        c = self.c
        p, table, bullets = c["p"], c["table"], c["bullets"]
        PageBreak, CondPageBreak, KeepTogether, HRFlowable = c["PageBreak"], c["CondPageBreak"], c["KeepTogether"], c["HRFlowable"]
        colors, inch = c["colors"], c["inch"]
        executive, sections = c["executive"], c["sections"]
        rows = [["Priority", "Risk ID", "Risk", "Business impact", "Confidence", "Recommended action", "Effort", "Cost of inaction", "Residual risk", "Evidence locations"]]
        rows.extend([item.get("priority"), item.get("finding_id") or item.get("id"), item.get("title"), item.get("business_impact") or item.get("impact"), item.get("confidence"), item.get("recommendation"), item.get("effort"), item.get("cost_of_inaction") or "Not quantified", item.get("residual_risk") or "Requires review", item.get("location")] for item in executive)
        if len(rows) == 1:
            rows.append(["—", "—", "No consolidated technical risk retained", "Human review remains required", "—", "Verify evidence completeness", "—", "Not quantified", "Unknown", "—"])
        story = [PageBreak(), p("Executive Risk Register", c["h1"]), table(rows, [.32 * inch, .62 * inch, .8 * inch, .8 * inch, .42 * inch, 1.08 * inch, .38 * inch, .82 * inch, .82 * inch, .72 * inch], font_size=4.5)]
        architecture = next((item for item in sections if item.get("id") == "architecture_debt"), {})
        story.extend([PageBreak(), p("Architecture and Complexity", c["h1"]), p("Measured profile", c["h2"]), *bullets(architecture.get("evidence") or [], 12), p("Priority hotspots", c["h2"]), *bullets(architecture.get("findings") or [], 8),
            PageBreak(), p("CI/CD, Security, and Dependency Evidence", c["h1"])])
        for section_id in ("ci_cd", "dependency_health", "secrets_review", "static_analysis"):
            section = next((item for item in sections if item.get("id") == section_id), None)
            if not section:
                continue
            block = [p(f"{section.get('label')} — {section.get('technical_score_display')} · {section.get('assurance_label')}", c["h2"]), p(section.get("summary"), c["body"]), *bullets(section.get("evidence") or [], 7)]
            if section.get("findings"):
                block.extend([p("Findings", c["h3"]), *bullets(section.get("findings") or [], 6)])
            if section.get("unavailable"):
                block.extend([p("Evidence limitations", c["h3"]), *bullets(section.get("unavailable") or [], 6)])
            story.extend([CondPageBreak(2.15 * inch), KeepTogether(block), HRFlowable(width="100%", thickness=.4, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=4)])
        return story

    def detailed_findings(self) -> list[Any]:
        c = self.c
        p, table, PageBreak, CondPageBreak, Spacer = c["p"], c["table"], c["PageBreak"], c["CondPageBreak"], c["Spacer"]
        story = [PageBreak(), p("Detailed Findings Register", c["h1"]), p("Each record separates observed evidence, interpretation, business inference, and recommendation. Stable IDs connect evidence to acceptance criteria, roadmap work, backlog exports, and repeat-run comparison.", c["body"])]
        for finding in c["detailed"]:
            acceptance = finding.get("acceptance_criteria") or []
            if isinstance(acceptance, list):
                acceptance = "; ".join(_text(item, 900) for item in acceptance)
            story.extend([CondPageBreak(3.25 * c["inch"]), p(f"{finding.get('priority')} · {finding.get('title')} · {finding.get('finding_id') or finding.get('id')}", c["h2"]),
                table([["Category / status", f"{finding.get('category')} · {finding.get('status') or 'open'}"], ["Location", finding.get("location")], ["Layer 1 — Evidence / fact", finding.get("fact") or finding.get("evidence")], ["Layer 2 — Interpretation", finding.get("interpretation") or finding.get("title")], ["Layer 3 — Business inference", finding.get("business_impact") or finding.get("impact")], ["Layer 4 — Recommendation", finding.get("recommendation")], ["Owner / effort", f"{finding.get('owner_role')} · {finding.get('effort')}"], ["Cost of inaction", finding.get("cost_of_inaction") or "Not quantified"], ["Residual risk", finding.get("residual_risk") or "Requires review"], ["Acceptance criteria", acceptance], ["Roadmap / backlog", f"{', '.join(finding.get('roadmap_mappings') or []) or 'Not mapped'} · {finding.get('backlog_issue_mapping') or 'Not mapped'}"]], [1.45 * c["inch"], 6.0 * c["inch"]], header=False, font_size=6.5), Spacer(1, .08 * c["inch"])])
        if not c["detailed"]:
            story.append(p("No structured technical finding was retained; human review remains required.", c["warning"]))
        return story

    def roadmap_and_staffing(self) -> list[Any]:
        c = self.c
        p, table, PageBreak, Spacer = c["p"], c["table"], c["PageBreak"], c["Spacer"]
        inch = c["inch"]
        story = [PageBreak(), p("Six-Month Execution Roadmap", c["h1"])]
        for window in c["roadmap"]:
            if not isinstance(window, dict):
                continue
            story.append(p(f"{window.get('window')} — {window.get('objective')}", c["h2"]))
            rows = [["ID / work package", "Class", "Related risks", "Owner", "Effort", "Acceptance", "Expected impact", "Residual risk"]]
            rows.extend([f"{package.get('work_package_id') or ''} {package.get('title')}", package.get("classification"), ", ".join(package.get("related_finding_ids") or []), package.get("owner_role"), package.get("effort") or package.get("effort_range"), "; ".join(package.get("acceptance_criteria") or []), package.get("expected_impact"), package.get("residual_risk")] for package in window.get("work_packages") or [] if isinstance(package, dict))
            if len(rows) > 1:
                story.extend([table(rows, [1.05 * inch, .48 * inch, .72 * inch, .72 * inch, .48 * inch, 1.45 * inch, 1.35 * inch, 1.15 * inch], font_size=4.9), Spacer(1, .1 * inch)])
        rows = [["Sequence", "Role", "Focus", "Indicative capacity"]]
        rows.extend([item.get("sequence"), item.get("role"), item.get("focus"), item.get("estimated_load") or "Requires planning"] for item in c["staffing"] if isinstance(item, dict))
        if len(rows) == 1:
            rows.append(["—", "Stakeholder decision required", "Staffing evidence unavailable", "Not committed"])
        story.extend([PageBreak(), p("Staffing and Sequencing", c["h1"]), table(rows, [.65 * inch, 1.55 * inch, 3.65 * inch, 1.6 * inch]), p("Cost boundary", c["h2"]), p("Labor rates, contract structure, geographic mix, and budget ceilings remain stakeholder decisions. NICO must not invent monetary exposure without client inputs or disclosed assumptions.", c["body"])])
        return story

    def scope_and_assumptions(self) -> list[Any]:
        c = self.c
        p, table, PageBreak = c["p"], c["table"], c["PageBreak"]
        inch, assessment = c["inch"], c["assessment"]
        story = [PageBreak(), p("How to Use This Report", c["h1"]), *[p(f"{index}. {item}", c["body"]) for index, item in enumerate(assessment.get("how_to_use_report") or ["Complete exact-package human review before delivery."], start=1)], p("Scope Boundary and Unassessed Risk", c["h1"])]
        rows = [["Area", "Boundary"]]
        rows.extend([item.get("area"), item.get("boundary")] for item in assessment.get("scope_boundaries") or [] if isinstance(item, dict))
        if len(rows) == 1:
            rows.append(["Unassessed domains", "Must not be interpreted as healthy"])
        story.extend([table(rows, [1.8 * inch, 5.65 * inch], font_size=6.5), p("Assumption Register", c["h1"])])
        assumptions = [["ID", "Category", "Assumption", "Source / confidence", "Sensitivity", "Consequence if wrong"]]
        assumptions.extend([item.get("assumption_id"), item.get("category"), item.get("description"), f"{item.get('source')} · {item.get('confidence')}", item.get("sensitivity"), item.get("consequence_if_wrong")] for item in assessment.get("assumption_register") or [] if isinstance(item, dict))
        if len(assumptions) == 1:
            assumptions.append(["—", "—", "No structured assumption retained", "—", "—", "Human validation required"])
        story.append(table(assumptions, [.55 * inch, .72 * inch, 1.75 * inch, 1.1 * inch, 1.55 * inch, 1.8 * inch], font_size=5.2))
        return story

    def appendix_and_review(self) -> list[Any]:
        c = self.c
        p, bullets = c["p"], c["bullets"]
        PageBreak, CondPageBreak, HRFlowable = c["PageBreak"], c["CondPageBreak"], c["HRFlowable"]
        colors, inch = c["colors"], c["inch"]
        story = [PageBreak(), p("Evidence Appendix", c["h1"]), p("Bounded decision-relevant evidence is rendered here; the complete machine-readable ledger is included in JSON and CSV artifacts.", c["body"])]
        for index, stage in enumerate(c["stages"], 1):
            stage_id = str(stage.get("stage_id") or "")
            client_literal_stage = (
                stage_id == "client_evidence_summary"
                or stage_id.startswith("client_human_evidence_")
            )
            story.extend([CondPageBreak(2.5 * inch), p(f"A{index}. {stage.get('title')} — {_text(stage.get('status')).upper()}", c["h2"]), p(f"Stage ID: {stage.get('stage_id')}", c["small"]), p(stage.get("summary"), c["body"]), p(f"Evidence records: {len(stage.get('evidence') or [])} · Findings: {len(stage.get('findings') or [])} · Limitations: {len(stage.get('unavailable') or [])}", c["small"]), *bullets(stage.get("evidence") or [], 8, client_literal=client_literal_stage)])
            if stage.get("findings"):
                story.extend([p("Findings", c["h3"]), *bullets(stage.get("findings") or [], 5)])
            if stage.get("unavailable"):
                story.extend([p("Unavailable or limited evidence", c["h3"]), *bullets(stage.get("unavailable") or [], 5)])
            story.append(HRFlowable(width="100%", thickness=.35, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=5))
        story.extend([PageBreak(), p("Human Review and Acceptance Gate", c["h1"]), p("The automated draft assessment is complete and pending human approval until the readiness and human-approval conditions are satisfied.", c["body"]), *bullets(["Verify exact repository, run, commit, evidence-ledger, customer, and project identities.", "Triage every material, review-required, failed, timed-out, and unavailable analyzer result.", "Confirm JSON, CSV, Markdown, HTML, and PDF show the same technical score, Evidence-Adjusted score, assurance, limitation accounting, and delivery status.", "Disposition every P1 against its binary acceptance criteria and residual-risk statement.", "Validate business context, assumptions, roadmap, staffing, effort, and any financial scenario inputs.", "Approve or reject the exact immutable report package before delivery."], 10), p(f"{c['assessment'].get('delivery_status') or 'HUMAN REVIEW REQUIRED'} · CLIENT-READY RELEASE REQUIRES INTERNAL EXACT-PACKAGE APPROVAL", c["warning"])])
        return story

    def build(self) -> list[Any]:
        story = self.cover_and_scorecard()
        story.extend(self.evidence_and_verified_change())
        story.extend(self.risk_architecture_and_controls())
        story.extend(self.detailed_findings())
        story.extend(self.roadmap_and_staffing())
        story.extend(self.scope_and_assumptions())
        story.extend(self.appendix_and_review())
        return story


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
    from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY

    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import CondPageBreak, HRFlowable, KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("P6-Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=31, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"), spaceAfter=14)
    subtitle = ParagraphStyle("P6-Subtitle", parent=styles["BodyText"], fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=5)
    h1 = ParagraphStyle("P6-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceBefore=7, spaceAfter=9, keepWithNext=1)
    h2 = ParagraphStyle("P6-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=7, spaceAfter=5, keepWithNext=1)
    h3 = ParagraphStyle("P6-H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.2, leading=13, textColor=colors.HexColor("#0f172a"), spaceBefore=5, spaceAfter=3, keepWithNext=1)
    body = ParagraphStyle("P6-Body", parent=styles["BodyText"], fontSize=9, leading=12.8, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("P6-Small", parent=body, fontSize=7.2, leading=9.5, textColor=colors.HexColor("#475569"), allowWidows=0)
    table_header = ParagraphStyle("P6-TableHeader", parent=small, fontName="Helvetica-Bold", textColor=colors.white)
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

    def p(
        value: Any,
        style: ParagraphStyle = body,
        *,
        client_literal: bool = False,
    ) -> Paragraph:
        if client_literal:
            from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

            return Paragraph(reportlab_literal_markup(value, 5000), style)
        return Paragraph(html.escape(_text(value)), style)
    def bullets(
        values: Iterable[Any],
        limit: int = 12,
        *,
        client_literal: bool = False,
    ) -> list[Paragraph]:
        if client_literal:
            return [
                p(f"- {item}", small, client_literal=True)
                for item in list(values)[:limit]
                if str(item or "").strip()
            ]
        return [p(f"- {_text(item, 900)}", small) for item in list(values)[:limit] if _text(item)]
    def table(rows: list[list[Any]], widths: list[float], header: bool = True, font_size: float = 6.8) -> LongTable:
        cell_style = ParagraphStyle(f"P6-Cell-{font_size}", parent=small, fontSize=font_size, leading=max(font_size + 1.8, 6.5), textColor=colors.HexColor("#475569"))
        header_style = ParagraphStyle(f"P6-Header-{font_size}", parent=table_header, fontSize=max(4.6, font_size), leading=max(font_size + 1.8, 6.5))
        converted = [[p(cell, header_style if header and row_index == 0 else cell_style) for cell in row] for row_index, row in enumerate(rows)]
        result = LongTable(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT", splitByRow=1)
        commands = [("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])]
        if header:
            commands.extend([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6)])
        result.setStyle(TableStyle(commands))
        return result
    language = _text(
        identity.get("report_language")
        or identity.get("language")
        or identity.get("locale"),
        16,
    ).casefold()
    approval_boundary = ES_BOUNDARY if language.startswith("es") else EN_BOUNDARY

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica-Bold", 5.2)
        canvas.drawCentredString(4.25 * inch, .43 * inch, approval_boundary)
        canvas.setFont("Helvetica", 6.2)
        canvas.drawString(
            .55 * inch,
            .25 * inch,
            f"NICO Comprehensive · {_text(identity.get('run_id'), 32)} · "
            f"{_text(identity.get('commit_sha'), 12)}",
        )
        canvas.drawRightString(7.95 * inch, .25 * inch, f"Page {doc.page}")
        canvas.restoreState()
    def score_chart(section_values: list[dict[str, Any]]) -> Drawing:
        drawing = Drawing(500, max(60, 26 * len(section_values) + 15))
        for index, section in enumerate(section_values):
            y = drawing.height - 22 - index * 26
            value = section.get("score_value")
            drawing.add(String(0, y + 3, _text(section.get("label"), 31), fontName="Helvetica", fontSize=7.1, fillColor=colors.HexColor("#334155")))
            drawing.add(Rect(155, y, 285, 11, fillColor=colors.HexColor("#e2e8f0"), strokeColor=None))
            if isinstance(value, int):
                fill = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}.get(section.get("score_tone"), "#64748b")
                drawing.add(Rect(155, y, 2.85 * value, 11, fillColor=colors.HexColor(fill), strokeColor=None)); label = str(value)
            else:
                drawing.add(Rect(155, y, 285, 11, fillColor=colors.HexColor("#f1f5f9"), strokeColor=None)); label = "N/S"
            drawing.add(String(448, y + 2, label, fontName="Helvetica-Bold", fontSize=7.7, fillColor=colors.HexColor("#0f172a")))
        return drawing

    doc = PremiumDoc(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, title="NICO Comprehensive Technical Assessment", author="NICO", invariant=1)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    context = locals() | {
        "score_value": maturity.get("presented_score", maturity.get("score")),
        "adjusted": assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score")),
        "detailed": [item for item in (assessment.get("decision_grade_findings_register") or assessment.get("findings_register") or []) if isinstance(item, dict)],
        "executive": [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)][:7],
        "weights": [item for item in assessment.get("scoring_weights") or [] if isinstance(item, dict)],
        "health": assessment.get("evidence_health_summary") if isinstance(assessment.get("evidence_health_summary"), dict) else {},
        "postures": assessment.get("decision_postures") if isinstance(assessment.get("decision_postures"), dict) else {},
    }
    story = _PdfStoryBuilder(context).build()
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
