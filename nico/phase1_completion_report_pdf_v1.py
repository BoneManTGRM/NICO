from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from nico.phase1_completion_report_contract_v1 import SCHEMA, dod_rows

NAVY = colors.HexColor("#0C2740")
GOLD = colors.HexColor("#F1C453")
PALE_BLUE = colors.HexColor("#EAF4FA")
BORDER = colors.HexColor("#AFC5D3")
TEXT = colors.HexColor("#152A3A")
MUTED = colors.HexColor("#5C6C78")
PASS_BG = colors.HexColor("#DDF7ED")
PASS_TEXT = colors.HexColor("#086A56")


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(escaped, style)


def build_appendix(
    path: Path,
    report: dict[str, Any],
    acceptance: dict[str, Any],
    audit: dict[str, Any],
    status: dict[str, Any],
    workflow_run_id: str,
    mobile_run_id: str,
    ios_run_id: str,
    artifact_id: str,
    artifact_name: str,
    artifact_digest: str,
    acceptance_completed_at: str,
) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12)
    subtitle = ParagraphStyle("subtitle", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=GOLD, alignment=TA_CENTER, spaceAfter=12)
    section = ParagraphStyle("section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY, spaceBefore=5, spaceAfter=7)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=TEXT)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=9.5)
    pass_style = ParagraphStyle("pass", parent=body, fontName="Helvetica-Bold", textColor=PASS_TEXT, alignment=TA_CENTER)
    header = ParagraphStyle("header", parent=body, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)

    def header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.16 * inch, letter[0], 0.16 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.55 * inch, 0.32 * inch, "NICO Comprehensive · Phase 1 completion evidence · automated draft")
        canvas.drawRightString(letter[0] - 0.55 * inch, 0.32 * inch, f"Completion appendix {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch)
    story: list[Any] = [
        _p("Phase 1 Definition-of-Done Closure", title),
        _p("ONE NICO COMPREHENSIVE REPORT · PHASE 1 COMPLETE · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", subtitle),
        _p(
            f"This appendix binds successful post-render production evidence to the existing NICO Comprehensive report for immutable commit {acceptance['expected_deployed_sha']}. It does not create another assessment product, alternate client report, human disposition, approval, or delivery authorization.",
            body,
        ),
        Spacer(1, 9),
    ]
    data = [[_p("Definition of Done", header), _p("Status", header), _p("Evidence", header)]]
    for item, result, evidence in dod_rows(report):
        data.append([_p(item, small), _p(result, pass_style), _p(evidence, small)])
    table = Table(data, colWidths=[3.42 * inch, 0.62 * inch, 2.86 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (1, 1), (1, -1), PASS_BG), ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([table, Spacer(1, 10), _p("Canonical Phase 1 workload", section)])
    metrics = [
        ("Total candidates / triage coverage", f"{report['coverage_done']}/{report['coverage_total']}"),
        ("Verdicts", f"not_actionable={report['not_actionable']}; needs_review={report['needs_review']}; confirmed={report['confirmed']}"),
        ("Review-by-exception", f"individual={report['individual']}; grouped={report['grouped']}; clusters={report['clusters']}; work units={report['work_units']}"),
        ("Structured audit", f"status={audit['status']}; candidates={audit['candidate_count']}; cluster errors={audit['cluster_integrity_error_count']}; score effect={audit['score_effect']}"),
    ]
    meta = Table([[_p(k, small), _p(v, small)] for k, v in metrics], colWidths=[2.35 * inch, 4.55 * inch])
    meta.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), PALE_BLUE), ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    complete = ParagraphStyle("complete", parent=title, fontSize=18, textColor=PASS_TEXT, spaceAfter=0)
    story.extend([meta, Spacer(1, 10), _p("PHASE 1 COMPLETE", complete), PageBreak()])

    story.extend([_p("Exact Current-Head Verification", title), _p("DETACHED POST-RENDER EVIDENCE BOUND TO THE SAME IMMUTABLE COMMIT", subtitle)])
    contexts = status.get("contexts") or {}
    status_rows = [[_p("Required context", header), _p("State", header), _p("Evidence", header)]]
    for name in status.get("required_contexts") or []:
        item = contexts.get(name) or {}
        state = "PASS" if item.get("state") == "success" else str(item.get("state", "unknown")).upper()
        status_rows.append([_p(name, small), _p(state, pass_style), _p(item.get("description") or item.get("target_url") or "Retained in status snapshot", small)])
    status_table = Table(status_rows, colWidths=[2.55 * inch, 0.7 * inch, 3.65 * inch], repeatRows=1)
    status_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("BACKGROUND", (1, 1), (1, -1), PASS_BG), ("GRID", (0, 0), (-1, -1), 0.45, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([status_table, Spacer(1, 10), _p("Immutable acceptance record", section)])
    rows = [
        ("Commit SHA", acceptance["expected_deployed_sha"]),
        ("Unified Production Acceptance run", workflow_run_id or "Recorded in detached evidence"),
        ("Mobile Restart proof run", mobile_run_id or "Recorded in detached evidence"),
        ("iOS WebKit proof run", ios_run_id or "Recorded in detached evidence"),
        ("Deployed Comprehensive passes", f"{acceptance['passes_completed']}/{acceptance['passes_required']} passed"),
        ("Acceptance artifact", artifact_name or "Recorded in detached evidence"),
        ("Artifact ID / digest", f"{artifact_id or 'recorded'} · {artifact_digest or 'recorded'}"),
        ("Acceptance completed", acceptance_completed_at or "Recorded in detached evidence"),
        ("Candidate-register digest parity", audit["candidate_register_sha256_observed"]),
    ]
    accept_table = Table([[_p(k, small), _p(v, small)] for k, v in rows], colWidths=[2.25 * inch, 4.65 * inch])
    accept_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), PALE_BLUE), ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([accept_table, Spacer(1, 10), _p("Truth and authorization boundary", section)])
    for line in [
        "This appendix records automated exact-current-head verification. It is not a human finding disposition, risk acceptance, or client-delivery authorization.",
        "Human approval remains pending. Client delivery remains blocked. Only an authorized reviewer may approve the exact immutable report package.",
        "Any change to the commit, evidence, scores, findings, candidates, or report artifacts creates a new draft and requires new acceptance evidence.",
        "The detached manifest records the final PDF SHA-256 because a PDF cannot truthfully embed its own final byte digest without changing that digest.",
    ]:
        story.extend([_p(f"• {line}", body), Spacer(1, 3)])
    boundary_style = ParagraphStyle("boundary", parent=body, fontName="Helvetica-Bold", textColor=GOLD, alignment=TA_CENTER)
    boundary = Table([[_p("HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", boundary_style)]], colWidths=[6.9 * inch])
    boundary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 1, GOLD), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.extend([Spacer(1, 6), boundary])
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def merge_pdf(source: Path, appendix: Path, output: Path) -> int:
    writer = PdfWriter()
    for path in (source, appendix):
        for page in PdfReader(str(path)).pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": "NICO Comprehensive - Phase 1 Complete - Automated Draft", "/Producer": SCHEMA})
    with output.open("wb") as stream:
        writer.write(stream)
    return len(writer.pages)
