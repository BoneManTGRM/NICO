from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from functools import wraps
from typing import Any, Callable

VERSION = "nico.phase5_visible_outcome_appendix.v1"
_PATCH_MARKER = "_nico_phase5_visible_outcome_appendix_v1"
HEADING = "Verified Change Since Phase 5 Baseline"


def _outcomes(assessment: dict[str, Any]) -> dict[str, Any]:
    value = assessment.get("phase5_verified_outcomes")
    return value if isinstance(value, dict) else {}


def _rows(assessment: dict[str, Any]) -> list[dict[str, str]]:
    outcomes = _outcomes(assessment)
    rows: list[dict[str, str]] = []
    for tool, change in sorted((outcomes.get("scanner_status_changes") or {}).items()):
        if isinstance(change, dict):
            rows.append(
                {
                    "category": "scanner",
                    "item": str(tool),
                    "before": str(change.get("before") or "unknown"),
                    "after": str(change.get("after") or "unknown"),
                    "delta": "status changed",
                    "evidence": "retained exact-SHA scanner artifact",
                }
            )
    for name, change in sorted((outcomes.get("complexity_changes") or {}).items()):
        if isinstance(change, dict):
            evidence = change.get("evidence") if isinstance(change.get("evidence"), dict) else {}
            rows.append(
                {
                    "category": "complexity",
                    "item": str(name),
                    "before": str(change.get("before")),
                    "after": str(change.get("after")),
                    "delta": str(change.get("delta")),
                    "evidence": "; ".join(
                        part
                        for part in (
                            str(evidence.get("path") or ""),
                            f"line {evidence.get('line')}" if evidence.get("line") else "",
                            str(evidence.get("method") or ""),
                        )
                        if part
                    ) or "exact-SHA complexity evidence",
                }
            )
    if outcomes.get("ci_history_classification_visible") is True:
        summary = assessment.get("ci_history_classification")
        historical = summary.get("historical_reliability") if isinstance(summary, dict) else {}
        counts = historical.get("classified_counts") if isinstance(historical, dict) else {}
        rows.append(
            {
                "category": "ci_history",
                "item": "classified workflow outcomes",
                "before": "raw non-success count",
                "after": json.dumps(counts or {}, sort_keys=True, separators=(",", ":")),
                "delta": "cancellations separated from genuine failures",
                "evidence": "retained bounded workflow run history",
            }
        )
    rows.append(
        {
            "category": "code_risk",
            "item": "tls_verify_disabled",
            "before": "open in Phase 5 baseline",
            "after": "open" if outcomes.get("tls_verify_disabled_finding_open") else "not present in executable exact-SHA finding ledger",
            "delta": "configuration literals excluded; executable calls remain detectable",
            "evidence": "token-aware executable-source risk scan",
        }
    )
    for tool in outcomes.get("unobserved_baseline_scanners") or []:
        rows.append(
            {
                "category": "unobserved",
                "item": str(tool),
                "before": "baseline status retained",
                "after": "no authoritative current exact-SHA record",
                "delta": "not counted as improvement",
                "evidence": "fail-closed truth boundary",
            }
        )
    return rows


def outcome_csv(assessment: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=("category", "item", "before", "after", "delta", "evidence"),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(_rows(assessment))
    return buffer.getvalue()


def _markdown_section(assessment: dict[str, Any]) -> str:
    outcomes = _outcomes(assessment)
    if not outcomes:
        return ""
    lines = ["", f"## {HEADING}", ""]
    lines.append(f"Baseline commit: `{outcomes.get('baseline_commit_sha') or 'unavailable'}`")
    lines.append(f"Current exact commit: `{outcomes.get('current_commit_sha') or 'unavailable'}`")
    lines.extend(
        [
            "",
            "| Category | Item | Before | After | Delta | Evidence |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in _rows(assessment):
        values = [str(row[key]).replace("|", "\\|") for key in ("category", "item", "before", "after", "delta", "evidence")]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            f"Truth rule: {outcomes.get('truth_rule') or 'Only retained evidence may change an outcome.'}",
            "Scores are not increased by this comparison section. Unchanged and unobserved risks remain visible.",
            "",
        ]
    )
    return "\n".join(lines)


def _html_section(assessment: dict[str, Any]) -> str:
    outcomes = _outcomes(assessment)
    if not outcomes:
        return ""
    rows = []
    for row in _rows(assessment):
        cells = "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in ("category", "item", "before", "after", "delta", "evidence"))
        rows.append(f"<tr>{cells}</tr>")
    return (
        f'<section id="phase5-verified-outcomes"><h2>{HEADING}</h2>'
        f"<p>Baseline commit: <code>{html.escape(str(outcomes.get('baseline_commit_sha') or 'unavailable'))}</code><br>"
        f"Current exact commit: <code>{html.escape(str(outcomes.get('current_commit_sha') or 'unavailable'))}</code></p>"
        "<table><thead><tr><th>Category</th><th>Item</th><th>Before</th><th>After</th><th>Delta</th><th>Evidence</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<p><strong>Truth rule:</strong> {html.escape(str(outcomes.get('truth_rule') or 'Only retained evidence may change an outcome.'))}</p>"
        "<p>Scores are not increased by this comparison section. Unchanged and unobserved risks remain visible.</p></section>"
    )


def _appendix_pdf(assessment: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("P5-Title", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    body = ParagraphStyle("P5-Body", parent=styles["BodyText"], fontSize=8, leading=10.5, textColor=colors.HexColor("#334155"))
    small = ParagraphStyle("P5-Small", parent=body, fontSize=6.2, leading=7.8)
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.45 * inch, leftMargin=.45 * inch, topMargin=.45 * inch, bottomMargin=.5 * inch, invariant=1)
    outcomes = _outcomes(assessment)
    story: list[Any] = [Paragraph(HEADING, title)]
    story.append(Paragraph(html.escape(f"Baseline commit: {outcomes.get('baseline_commit_sha') or 'unavailable'}"), body))
    story.append(Paragraph(html.escape(f"Current exact commit: {outcomes.get('current_commit_sha') or 'unavailable'}"), body))
    story.append(Spacer(1, .12 * inch))
    table_rows: list[list[Any]] = [["Category", "Item", "Before", "After", "Delta", "Evidence"]]
    for row in _rows(assessment):
        table_rows.append([Paragraph(html.escape(str(row[key])), small) for key in ("category", "item", "before", "after", "delta", "evidence")])
    table = LongTable(table_rows, colWidths=[.72 * inch, 1.05 * inch, 1.1 * inch, 1.4 * inch, 1.35 * inch, 1.65 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, Spacer(1, .12 * inch), Paragraph(html.escape(str(outcomes.get("truth_rule") or "Only retained evidence may change an outcome.")), body), Paragraph("Scores are not increased by this comparison section. Unchanged and unobserved risks remain visible.", body), PageBreak()])
    doc.build(story)
    return buffer.getvalue()


def _append_pdf(original: bytes, assessment: dict[str, Any]) -> tuple[bytes, int]:
    from pypdf import PdfReader, PdfWriter

    base_reader = PdfReader(io.BytesIO(original))
    appendix_reader = PdfReader(io.BytesIO(_appendix_pdf(assessment)))
    writer = PdfWriter()
    for page in base_reader.pages:
        writer.add_page(page)
    for page in appendix_reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), len(writer.pages)


def install_phase5_visible_outcome_appendix_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_markdown: Callable[..., str] = report._build_markdown
    current_html: Callable[..., str] = report._build_html
    current_pdf: Callable[..., tuple[bytes, int]] = report.comprehensive_pdf_with_final_count
    current_build: Callable[..., dict[str, Any]] = report.build_comprehensive_report_package
    if getattr(current_build, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current_markdown)
    def markdown(*args: Any, **kwargs: Any) -> str:
        assessment = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs.get("assessment", {})
        return current_markdown(*args, **kwargs) + _markdown_section(assessment if isinstance(assessment, dict) else {})

    @wraps(current_html)
    def rendered_html(*args: Any, **kwargs: Any) -> str:
        assessment = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs.get("assessment", {})
        original = current_html(*args, **kwargs)
        section = _html_section(assessment if isinstance(assessment, dict) else {})
        return original.replace("</body>", section + "\n</body>") if section and "</body>" in original else original + section

    @wraps(current_pdf)
    def pdf_with_outcomes(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
        roadmap: list[dict[str, Any]],
        staffing: list[dict[str, Any]],
        limitations: dict[str, int],
        generated_at: str,
    ) -> tuple[bytes, int]:
        pdf_bytes, _count = current_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
        if not _outcomes(assessment):
            return pdf_bytes, _count
        return _append_pdf(pdf_bytes, assessment)

    @wraps(current_build)
    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current_build(*args, **kwargs)
        assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
        outcomes = _outcomes(assessment)
        csv_text = outcome_csv(assessment)
        package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
        package["phase5_verified_outcomes"] = outcomes
        package["phase5_verified_outcomes_json"] = json.dumps(outcomes, sort_keys=True, separators=(",", ":"), default=str)
        package["phase5_verified_outcomes_csv"] = csv_text
        package["phase5_verified_outcomes_csv_sha256"] = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        package["phase5_outcomes_visible_in_markdown_html_pdf"] = bool(outcomes)
        result["report_package"] = package
        return result

    setattr(markdown, _PATCH_MARKER, True)
    setattr(rendered_html, _PATCH_MARKER, True)
    setattr(pdf_with_outcomes, _PATCH_MARKER, True)
    setattr(build, _PATCH_MARKER, True)
    report._build_markdown = markdown
    report._build_html = rendered_html
    report.comprehensive_pdf_with_final_count = pdf_with_outcomes
    report.build_comprehensive_report_package = build
    return {
        "status": "installed",
        "version": VERSION,
        "markdown_outcome_section": True,
        "html_outcome_section": True,
        "pdf_outcome_appendix": True,
        "json_outcome_payload": True,
        "csv_outcome_export": True,
        "scores_changed_by_appendix": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "HEADING", "outcome_csv", "install_phase5_visible_outcome_appendix_v1"]
