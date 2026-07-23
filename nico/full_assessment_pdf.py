from __future__ import annotations

import base64
import html
import io
import re
from typing import Any

FULL_ASSESSMENT_PDF_STYLE_VERSION = "full-assessment-final-report-v2"


def _text(value: Any, limit: int = 1400) -> str:
    cleaned = str(value or "")
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    cleaned = re.sub(r"https?://\S+", "[link omitted]", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 16)].rstrip() + "... [truncated]"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_color(status: str) -> str:
    lowered = str(status or "").lower()
    if lowered == "green":
        return "#047857"
    if lowered == "yellow":
        return "#b45309"
    if lowered == "red":
        return "#b91c1c"
    return "#64748b"


def _safe_filename(repository: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", repository.replace("/", "-"))
    normalized = normalized.strip("-._") or "assessment"
    return f"nico-full-assessment-{normalized}.pdf"


def full_assessment_pdf_filename(result: dict[str, Any]) -> str:
    return _safe_filename(str(result.get("repository") or "assessment"))


def build_full_assessment_pdf_base64(
    result: dict[str, Any],
    *,
    report_id: str = "",
) -> tuple[str | None, str | None]:
    """Render the complete final Full Assessment PDF without changing delivery approval state."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception:
        return None, "Full Assessment PDF export is unavailable because the configured PDF renderer could not be loaded."

    try:
        buffer = io.BytesIO()
        repository = _text(result.get("repository") or "Not specified", 240)
        run_id = _text(result.get("run_id") or result.get("report_run_id") or "Not specified", 180)
        resolved_report_id = _text(report_id or result.get("report_id") or "Not specified", 180)
        client_name = _text(result.get("client_name") or "Not specified", 180)
        project_name = _text(result.get("project_name") or "Not specified", 180)
        generated_at = _text(result.get("generated_at") or "Not specified", 100)
        maturity = _dict(result.get("maturity_signal"))
        trust_level = _text(result.get("trust_level") or "Review-limited", 80)
        export_gate = _dict(result.get("export_truth_gate"))
        ledger = _dict(result.get("evidence_ledger"))
        verdict = _dict(result.get("client_delivery_verdict"))
        sections = [item for item in _list(result.get("sections")) if isinstance(item, dict)]

        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.56 * inch,
            leftMargin=0.56 * inch,
            topMargin=0.50 * inch,
            bottomMargin=0.72 * inch,
            title="NICO Full Assessment",
            author="NICO",
            subject="Evidence-bound Full Assessment final report pending human approval",
        )
        styles = getSampleStyleSheet()
        hero_brand = ParagraphStyle(
            "FullHeroBrand",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=31,
            leading=33,
            textColor=colors.white,
            alignment=1,
            spaceAfter=1,
        )
        hero_powered = ParagraphStyle(
            "FullHeroPowered",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#67e8f9"),
            alignment=1,
            spaceAfter=4,
        )
        hero_title = ParagraphStyle(
            "FullHeroTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=colors.HexColor("#e0f2fe"),
            alignment=1,
            spaceAfter=2,
        )
        hero_draft = ParagraphStyle(
            "FullHeroDraft",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#fde68a"),
            alignment=1,
            spaceAfter=0,
        )
        h2 = ParagraphStyle(
            "FullH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.4,
            leading=15,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )
        h3 = ParagraphStyle(
            "FullH3",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=11.5,
            textColor=colors.HexColor("#111827"),
            spaceBefore=4,
            spaceAfter=2,
            keepWithNext=True,
        )
        body = ParagraphStyle(
            "FullBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.25,
            leading=10.7,
            textColor=colors.HexColor("#334155"),
            spaceAfter=3,
        )
        small = ParagraphStyle(
            "FullSmall",
            parent=body,
            fontSize=7.45,
            leading=9.2,
            textColor=colors.HexColor("#475569"),
            spaceAfter=1.8,
        )
        label = ParagraphStyle(
            "FullLabel",
            parent=small,
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.3,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=1,
        )
        metric = ParagraphStyle(
            "FullMetric",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10.8,
            leading=12.5,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=0,
        )
        callout = ParagraphStyle(
            "FullCallout",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=10.7,
            textColor=colors.HexColor("#854d0e"),
            backColor=colors.HexColor("#fef3c7"),
            borderColor=colors.HexColor("#f59e0b"),
            borderWidth=0.7,
            borderPadding=7,
            spaceAfter=7,
        )
        info = ParagraphStyle(
            "FullInfo",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8.3,
            leading=10.5,
            textColor=colors.HexColor("#075985"),
            backColor=colors.HexColor("#e0f2fe"),
            borderColor=colors.HexColor("#7dd3fc"),
            borderWidth=0.7,
            borderPadding=7,
            spaceAfter=7,
        )

        def p(value: Any, style: Any, limit: int = 1400) -> Any:
            return Paragraph(html.escape(_text(value, limit)), style)

        def bullets(values: list[Any], max_items: int = 6) -> list[Any]:
            cleaned = [_text(item, 560) for item in values if _text(item, 560)]
            if not cleaned:
                return [p("No evidence returned.", small)]
            flowables: list[Any] = [p(f"- {item}", small, 600) for item in cleaned[:max_items]]
            if len(cleaned) > max_items:
                flowables.append(p(f"- {len(cleaned) - max_items} additional item(s) omitted from the PDF; Markdown and JSON retain the detailed report.", small))
            return flowables

        footer_left = "NICO Full Assessment - final report - pending human approval"
        footer_right = f"Report {resolved_report_id}" if resolved_report_id != "Not specified" else "Full Assessment"

        def draw_footer(canvas: Any, document: Any) -> None:
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#dbeafe"))
            canvas.line(document.leftMargin, 0.52 * inch, document.pagesize[0] - document.rightMargin, 0.52 * inch)
            canvas.setFont("Helvetica", 7.2)
            canvas.setFillColor(colors.HexColor("#64748b"))
            canvas.drawString(document.leftMargin, 0.33 * inch, footer_left)
            canvas.drawRightString(
                document.pagesize[0] - document.rightMargin,
                0.33 * inch,
                f"{footer_right} - Page {canvas.getPageNumber()}",
            )
            canvas.restoreState()

        hero = Table(
            [
                [p("NICO", hero_brand)],
                [p("POWERED BY REPARODYNAMICS", hero_powered)],
                [p("Full Assessment", hero_title)],
                [p("FINAL REPORT - PENDING HUMAN APPROVAL", hero_draft)],
            ],
            colWidths=[7.08 * inch],
        )
        hero.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )

        metadata = Table(
            [
                [p("Repository", label), p(repository, small), p("Run ID", label), p(run_id, small)],
                [p("Client", label), p(client_name, small), p("Project", label), p(project_name, small)],
                [p("Report ID", label), p(resolved_report_id, small), p("Generated", label), p(generated_at, small)],
                [p("Report path", label), p("Full Assessment (full_run)", small), p("Delivery", label), p("Human review required", small)],
            ],
            colWidths=[0.82 * inch, 2.58 * inch, 0.82 * inch, 2.86 * inch],
        )
        metadata.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        metric_cards = Table(
            [
                [
                    [p("MATURITY", label), p(maturity.get("level", "Unknown"), metric)],
                    [p("TECHNICAL SCORE", label), p(f"{maturity.get('score', 'N/A')}/100", metric)],
                    [p("TRUST LEVEL", label), p(trust_level, metric)],
                    [p("EXPORT GATE", label), p(str(export_gate.get("status") or "pending").replace("_", " ").upper(), metric)],
                ]
            ],
            colWidths=[1.62 * inch, 1.72 * inch, 1.72 * inch, 2.02 * inch],
        )
        metric_cards.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        score_rows = [[p("Area", label), p("Status", label), p("Score", label), p("Summary", label)]]
        for section in sections:
            score_rows.append(
                [
                    p(section.get("label") or section.get("id") or "Section", small, 100),
                    p(str(section.get("status") or "unknown").upper(), small, 40),
                    p(str(section.get("score", "N/A")), small, 20),
                    p(section.get("summary") or "No summary returned.", small, 220),
                ]
            )
        scorecard = Table(score_rows, colWidths=[1.58 * inch, 0.78 * inch, 0.50 * inch, 4.22 * inch], repeatRows=1)
        score_styles: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for row_index, section in enumerate(sections, start=1):
            score_styles.append(
                ("TEXTCOLOR", (1, row_index), (2, row_index), colors.HexColor(_status_color(str(section.get("status") or ""))))
            )
        scorecard.setStyle(TableStyle(score_styles))

        coverage = _dict(ledger.get("coverage_by_section"))
        coverage_rows = [[p("Evidence area", label), p("Verified", label), p("Missing", label), p("Complete", label)]]
        for section_id, item in coverage.items():
            if not isinstance(item, dict):
                continue
            coverage_rows.append(
                [
                    p(str(section_id).replace("_", " ").title(), small, 100),
                    p(", ".join(str(value) for value in _list(item.get("verified_required_tools"))) or "None", small, 180),
                    p(", ".join(str(value) for value in _list(item.get("missing_required_tools"))) or "None", small, 180),
                    p("YES" if item.get("complete") else "NO", small, 20),
                ]
            )
        coverage_table = Table(coverage_rows, colWidths=[1.52 * inch, 2.15 * inch, 2.15 * inch, 1.26 * inch], repeatRows=1)
        coverage_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3730a3")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        story: list[Any] = [
            hero,
            Spacer(1, 0.08 * inch),
            metadata,
            Spacer(1, 0.08 * inch),
            metric_cards,
            Spacer(1, 0.08 * inch),
            p(
                "This PDF is a review artifact. It is not approved for client delivery. Final delivery requires same-run human review and approval, and unavailable evidence is not treated as passing proof.",
                callout,
            ),
            p(
                f"Evidence ledger: status={ledger.get('status', 'missing')}, entries={ledger.get('entry_count', 0)}, verified={ledger.get('verified_entry_count', 0)}, unavailable={ledger.get('unavailable_entry_count', 0)}. Delivery verdict={verdict.get('status', 'human_review_required')}.",
                info,
            ),
            p("Executive Summary", h2),
            p(result.get("executive_summary") or "No executive summary returned.", body, 1200),
            p("Technical Scorecard", h2),
            scorecard,
            Spacer(1, 0.08 * inch),
            p("Evidence Ledger Coverage", h2),
            coverage_table,
        ]

        scorecard_data = _dict(result.get("scorecard"))
        ci_runtime = _dict(scorecard_data.get("ci_runtime_evidence"))
        complexity_runtime = _dict(scorecard_data.get("complexity_runtime_evidence"))
        if ci_runtime or complexity_runtime:
            story.append(p("Runtime Evidence Summary", h2))
            runtime_rows = [[p("Evidence", label), p("Observed state", label)]]
            if ci_runtime:
                runtime_rows.append(
                    [
                        p("CI/CD runtime", small),
                        p(
                            f"jobs={ci_runtime.get('jobs_observed', 0)}, runs={ci_runtime.get('runs_with_jobs', 0)}, success rate={ci_runtime.get('job_success_rate', 'unavailable')}, deployments={ci_runtime.get('deployments_observed', 0)}, score={ci_runtime.get('baseline_score', 'N/A')} -> {ci_runtime.get('final_score', 'N/A')}",
                            small,
                            360,
                        ),
                    ]
                )
            if complexity_runtime:
                runtime_rows.append(
                    [
                        p("Complexity runtime", small),
                        p(
                            f"files={complexity_runtime.get('files_analyzed', 0)}, functions={complexity_runtime.get('functions_measured', 0)}, average complexity={complexity_runtime.get('average_cyclomatic_complexity', 'unavailable')}, maximum={complexity_runtime.get('maximum_cyclomatic_complexity', 'unavailable')}, duplicate ratio={complexity_runtime.get('duplicate_line_ratio', 'unavailable')}, score={complexity_runtime.get('baseline_score', 'N/A')} -> {complexity_runtime.get('final_score', 'N/A')}",
                            small,
                            420,
                        ),
                    ]
                )
            runtime_table = Table(runtime_rows, colWidths=[1.55 * inch, 5.53 * inch], repeatRows=1)
            runtime_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfeff")),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(runtime_table)

        for section in sections:
            title = f"{section.get('label') or section.get('id')} - {str(section.get('status') or 'unknown').upper()} {section.get('score', 'N/A')}/100"
            story.append(KeepTogether([p(title, h2), p(section.get("summary") or "No summary returned.", body, 700)]))
            story.append(p("Evidence", h3))
            story.extend(bullets(_list(section.get("verified_claims")) or _list(section.get("evidence")), max_items=5))
            findings = _list(section.get("findings"))
            if findings:
                story.append(p("Findings", h3))
                story.extend(bullets(findings, max_items=4))
            unavailable = _list(section.get("unverified_claims")) or _list(section.get("unavailable"))
            if unavailable:
                story.append(p("Unavailable / Review-Limited", h3))
                story.extend(bullets(unavailable, max_items=4))
            story.append(Spacer(1, 0.06 * inch))

        action_items = _list(result.get("next_steps")) or _list(result.get("quick_wins"))
        if action_items:
            story.append(p("Recommended Action Plan", h2))
            story.extend(bullets(action_items, max_items=8))

        blockers = _list(verdict.get("blockers"))
        if blockers:
            story.append(p("Delivery Blockers", h2))
            story.extend(bullets(blockers, max_items=8))

        unavailable_notes = _list(result.get("unavailable_data_notes"))
        if unavailable_notes:
            story.append(p("Unavailable Data Notes", h2))
            story.extend(bullets(unavailable_notes, max_items=8))

        story.append(
            p(
                "Final statement: This Full Assessment PDF preserves evidence limits and is intended for human review. It does not establish exhaustive absence of defects, vulnerabilities, secrets, complexity, or operational risk.",
                callout,
            )
        )
        doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
        pdf_bytes = buffer.getvalue()
        if not pdf_bytes.startswith(b"%PDF"):
            return None, "Full Assessment PDF export failed integrity validation."
        return base64.b64encode(pdf_bytes).decode("ascii"), None
    except Exception:
        return None, "Full Assessment PDF export failed during professional report rendering."
