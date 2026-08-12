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
PENDING_BG = colors.HexColor("#FFF4CF")
PENDING_TEXT = colors.HexColor("#8A6200")


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
    pending_style = ParagraphStyle("pending", parent=body, fontName="Helvetica-Bold", textColor=PENDING_TEXT, alignment=TA_CENTER)
    header = ParagraphStyle("header", parent=body, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)

    def header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.16 * inch, letter[0], 0.16 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.55 * inch, 0.32 * inch, "NICO Comprehensive · completion evidence · automated draft")
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
    story.extend([Spacer(1, 6), boundary, PageBreak()])

    story.extend([
        _p("Phase 2 Human Review by Exception Closure", title),
        _p("SOFTWARE REQUIREMENTS IMPLEMENTED · EMPIRICAL SPECIALIST-EFFORT MEASUREMENT PENDING", subtitle),
        _p(
            "Phase 2 software is implemented in the canonical Comprehensive review and approval architecture. This page records the engineering closure separately from the remaining real-human reviewer-time measurement. It does not fabricate reviewer activity, human disposition, approval, residual-risk acceptance, or client-delivery authorization.",
            body,
        ),
        Spacer(1, 8),
        _p("Implementation record", section),
    ])
    implementation = [
        [_p("PR", header), _p("Branch / head", header), _p("Merge SHA", header), _p("Purpose", header)],
        [_p("#1166", small), _p("phase2/full-coverage\n69669dfbccd87449930f12ceb4d276c9c3dd3d3b", small), _p("5ee3f2b1eb2faf46a7b7cc68940be89df683105f", small), _p("Six queues, filtering/search, expandable evidence, controlled group disposition, QC sampling, isolation, report truth, and one-report approval binding.", small)],
        [_p("#1170", small), _p("phase2/closure-truth-single-product-ios-readiness\n1a4ce6ec84682ec3f7e32976822592fc8023fc4c", small), _p("1520e0f32b36b09fbb3eab2a2232b8a6407229eb", small), _p("Closed stale triage wording, Comprehensive-only public routing, operator guidance, and fail-closed readiness recovery.", small)],
    ]
    implementation_table = Table(implementation, colWidths=[0.45 * inch, 2.0 * inch, 1.75 * inch, 2.7 * inch], repeatRows=1)
    implementation_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([implementation_table, Spacer(1, 8), _p("Phase 2 software definition of done", section)])

    phase2_rows = [
        ("Six canonical review queues", "PASS", "Critical/material, human technical review, new automated triage complete, stable carry-forward, quality-control sample, and human disposition completed."),
        ("Reviewer efficiency controls", "PASS", "Severity/verdict/confidence/lineage/scanner/category/disposition/attention filters, risk/confidence sorting, ID/path/package/advisory/rule/scanner search, and expandable candidate/cluster evidence."),
        ("Controlled bulk human disposition", "PASS", "Explicit authorized reviewer action; exact underlying candidate IDs remain attributable and non-bulk-reviewable conditions fail closed."),
        ("Quality-control sampling", "PASS", "Configurable deterministic or risk-weighted sampling remains separate from disposition and approval; unsampled candidates are not implicitly approved."),
        ("Stale-review and tenancy protection", "PASS", "Review work is bound to canonical source evidence and exact scope; changed evidence and cross-run/project/client drift fail closed."),
        ("Report and approval truth", "PASS", "Raw observation, automated triage, human disposition, confirmed material finding, final human approval, and client-delivery authorization remain separate concepts across supported artifacts."),
        ("One product / one client report", "PASS", "NICO Comprehensive remains the sole public assessment identity and approved delivery contains one client PDF."),
        ("Required current-head production checks", "PASS", "The preceding exact-current-head page binds Vercel, Railway, Mobile Restart, iOS WebKit, and Two-Service production acceptance to this immutable commit."),
        ("Two-specialist <=4 hour efficiency target", "PENDING", "not_yet_measured. Issue #1169 requires real authorized specialist sessions. CI and synthetic fixtures may not fabricate this result."),
    ]
    phase2_data = [[_p("Requirement", header), _p("Status", header), _p("Evidence / boundary", header)]]
    for requirement, state, evidence in phase2_rows:
        phase2_data.append([_p(requirement, small), _p(state, pass_style if state == "PASS" else pending_style), _p(evidence, small)])
    phase2_table = Table(phase2_data, colWidths=[2.35 * inch, 0.65 * inch, 3.9 * inch], repeatRows=1)
    phase2_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (1, 1), (1, -2), PASS_BG),
        ("BACKGROUND", (1, -1), (1, -1), PENDING_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([phase2_table, Spacer(1, 8), _p("Reviewer workflow before vs after", section)])
    workflow_rows = [
        [_p("Before", header), _p("After", header)],
        [
            _p(f"A reviewer could face {report['coverage_total']} scanner candidates with limited completion evidence for the exception workflow.", small),
            _p(f"Current evidence is projected into {report['work_units']} review work units: {report['individual']} individual-attention candidate(s), {report['grouped']} grouped-review eligible candidate(s), {report['clusters']} grouped cluster(s), and a QC pool of {report['qc_pool']} candidate(s). Full underlying evidence remains auditable.", small),
        ],
        [
            _p("Report wording could leave technical-triage completion and authorized human disposition insufficiently explicit in completion evidence.", small),
            _p("The report now states technical triage separately from human disposition and keeps final approval and client delivery as separate protected human-controlled states.", small),
        ],
    ]
    workflow_table = Table(workflow_rows, colWidths=[3.45 * inch, 3.45 * inch], repeatRows=1)
    workflow_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.4, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([workflow_table, Spacer(1, 8), _p("Remaining manual reviewer responsibilities", section)])
    for line in [
        "Review genuine exceptions, ambiguity, material/high-impact findings, conflicting or changed evidence, and human-only evidence.",
        "Explicitly disposition candidates or eligible homogeneous groups, perform required independent QC, and resolve proof gaps or escalations.",
        "Record residual risk and ownership where applicable, then separately approve or reject the exact immutable package.",
        "Authorize client delivery only after all protected delivery gates pass.",
        "Complete the real two-specialist timing study tracked in issue #1169; retain the measured result even if it exceeds the engineering target.",
    ]:
        story.extend([_p(f"• {line}", body), Spacer(1, 2)])
    phase2_boundary = Table([[_p("PHASE 2 SOFTWARE COMPLETE · EMPIRICAL REVIEWER-TIME MEASUREMENT PENDING · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", boundary_style)]], colWidths=[6.9 * inch])
    phase2_boundary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 1, GOLD), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.extend([Spacer(1, 5), phase2_boundary])
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def merge_pdf(source: Path, appendix: Path, output: Path) -> int:
    writer = PdfWriter()
    for path in (source, appendix):
        for page in PdfReader(str(path)).pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": "NICO Comprehensive - Phase 2 Software Complete - Automated Draft", "/Producer": SCHEMA})
    with output.open("wb") as stream:
        writer.write(stream)
    return len(writer.pages)
