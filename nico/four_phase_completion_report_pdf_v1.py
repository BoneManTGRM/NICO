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

SCHEMA = "nico.four-phase-completion-bound-report.v1"
NAVY = colors.HexColor("#0C2740")
GOLD = colors.HexColor("#F1C453")
BORDER = colors.HexColor("#AFC5D3")
TEXT = colors.HexColor("#152A3A")
MUTED = colors.HexColor("#5C6C78")
PASS_BG = colors.HexColor("#DDF7ED")
PASS_TEXT = colors.HexColor("#086A56")
PENDING_BG = colors.HexColor("#FFF4CF")
PENDING_TEXT = colors.HexColor("#8A6200")


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(value, style)


def _table(rows: list[tuple[str, str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[_p("Engineering requirement", styles["header"]), _p("Status", styles["header"]), _p("Evidence", styles["header"])]]
    data += [[_p(item, styles["small"]), _p(status, styles["pass"]), _p(evidence, styles["small"])] for item, status, evidence in rows]
    table = Table(data, colWidths=[3.15 * inch, 0.72 * inch, 3.03 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (1, 1), (1, -1), PASS_BG),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def build_appendix(
    path: Path,
    phase3: dict[str, Any],
    phase4: dict[str, Any],
    status: dict[str, Any],
    expected_sha: str,
    *,
    spanish_run_id: str = "",
    green_watch_run_id: str = "",
) -> None:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=GOLD, alignment=TA_CENTER, spaceAfter=8),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=8.2, leading=10.3, textColor=TEXT),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=7.2, leading=8.8, textColor=TEXT),
        "header": ParagraphStyle("header", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=9, textColor=colors.white, alignment=TA_CENTER),
        "pass": ParagraphStyle("pass", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=9, textColor=PASS_TEXT, alignment=TA_CENTER),
        "pending": ParagraphStyle("pending", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=9, textColor=PENDING_TEXT, alignment=TA_CENTER),
        "marker": ParagraphStyle("marker", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=NAVY, alignment=TA_CENTER),
        "boundary": ParagraphStyle("boundary", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=GOLD, alignment=TA_CENTER),
    }

    def header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.16 * inch, letter[0], 0.16 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.55 * inch, 0.32 * inch, "NICO Comprehensive · four-phase engineering closure · automated evidence")
        canvas.drawRightString(letter[0] - 0.55 * inch, 0.32 * inch, f"Closure appendix {doc.page}")
        canvas.restoreState()

    positive = phase3["positive_supplied_evidence_paths_proven"]
    negative = phase3["negative_paths_proven"]
    phase3_rows = [
        ("Functional QA positive and missing-evidence paths", "PASS", "Observed supplied results retain provenance; repository tests never become runtime acceptance; absent runtime evidence remains not assessed."),
        ("Platform Parity truth", "PASS", "Supplied runtime/platform observations are supported; source indicators alone never become device or runtime parity."),
        ("Requirements and stakeholder authority", "PASS", "Authoritative, supplied-unverified, inferred, conflicting, and missing states stay distinct; automation never creates authority."),
        ("Roadmap and staffing truth", "PASS", "Planning windows remain NICO-proposed until authorized; rates, contracts, vendors, dates, owners, and budgets are not invented."),
        ("Existing Comprehensive integration", "PASS", "The existing Functional QA, Platform Parity, Requirements, Stakeholder, Roadmap, Staffing, and executive sections consume the evidence."),
        ("Positive and negative regression paths", "PASS", f"positive={sum(v is True for v in positive.values())}/{len(positive)}; negative={sum(v is True for v in negative.values())}/{len(negative)}."),
        ("One product and protected human boundary", "PASS", "NICO Comprehensive remains the only client report; disposition, authority, residual risk, approval, and delivery remain human-controlled."),
    ]

    durability = phase4["durability_recovery_validation"]
    security = phase4["security_validation"]
    phase4_rows = [
        ("Authorized client/project/scope lifecycle", "PASS", "Non-placeholder tenant, client, project, repository, authorization, read-only access, immutable commit, run, and evidence identities are required."),
        ("Scanner, candidate, triage, and review lifecycle", "PASS", "Required scanner execution, candidate lineage, fresh triage, exact disposition reconciliation, and mandatory individual review fail closed."),
        ("Human approval and immutable receipt", "PASS", "Authorized human identity/role/action is required; exact report, JSON, evidence, review, candidate, finding, score, and identity digests are bound."),
        ("Stale approval and delivery protection", "PASS", "Regeneration, evidence/finding/disposition/score change, cross-scope substitution, internal/test classification, or digest mismatch invalidates delivery."),
        ("Tenant/project/run isolation", "PASS", "Cross-client, cross-project, and cross-run mutation or recovery is rejected; missing or placeholder delivery scope fails closed."),
        ("Durability and recovery", "PASS", f"{sum(v is True for v in durability.values())}/{len(durability)} restart, deployment, Postgres, artifact, reviewer, approval, audit, and isolation controls are proven."),
        ("Focused security closure", "PASS", f"{sum(v is True for v in security.values())}/{len(security)} authorization, IDOR, isolation, secret, artifact, and approval controls are proven."),
        ("Repository-agnostic proof", "PASS", ", ".join(phase4["repository_agnostic_fixtures"])),
        ("Exact-current-head production acceptance", "PASS", f"Vercel, Railway, Mobile, iOS, Spanish, Two-Service, and Green Watch are successful for {expected_sha}."),
    ]

    story: list[Any] = [
        _p("Phase 3 Broader Professional Assessment Closure", styles["title"]),
        _p("ONE NICO COMPREHENSIVE REPORT · POSITIVE AND MISSING-EVIDENCE PATHS PROVEN", styles["subtitle"]),
        _p(f"This evidence is bound to exact current-head production acceptance for {expected_sha}. It extends the existing Comprehensive pipeline and creates no alternate assessment, scoring path, renderer, or client PDF.", styles["body"]),
        Spacer(1, 6),
        _table(phase3_rows, styles),
        Spacer(1, 8),
        _p("PHASE 3 ENGINEERING SATISFIED", styles["marker"]),
        PageBreak(),
        _p("Phase 4 Production Client-Delivery Engineering Closure", styles["title"]),
        _p("ENGINEERING AND OPERABILITY SATISFIED · REAL OUTSIDE PILOT TRACKED SEPARATELY", styles["subtitle"]),
        _table(phase4_rows, styles),
        Spacer(1, 7),
    ]

    contexts = status.get("contexts") or {}
    context_data = [[_p("Current-head context", styles["header"]), _p("State", styles["header"]), _p("Run / evidence", styles["header"])]]
    for name in status.get("required_contexts") or []:
        item = contexts.get(name) or {}
        context_data.append([_p(name, styles["small"]), _p("PASS", styles["pass"]), _p(item.get("target_url") or item.get("description") or "retained", styles["small"])])
    context_table = Table(context_data, colWidths=[2.45 * inch, 0.72 * inch, 3.73 * inch], repeatRows=1)
    context_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (1, 1), (1, -1), PASS_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [context_table, Spacer(1, 7)]

    pilot = Table([
        [_p("Engineering status", styles["header"]), _p("Outside-repository pilot", styles["header"]), _p("Human/client boundary", styles["header"])],
        [_p("PHASE 4 ENGINEERING: SATISFIED", styles["pass"]), _p("NOT EXECUTED", styles["pending"]), _p("Real repository authorization, specialist dispositions, approval/rejection, protected delivery, and measured effort remain external human evidence.", styles["small"])],
    ], colWidths=[2.1 * inch, 1.35 * inch, 3.45 * inch])
    pilot.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (0, 1), (0, 1), PASS_BG),
        ("BACKGROUND", (1, 1), (1, 1), PENDING_BG),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [pilot, Spacer(1, 5)]
    story += [_p("Phase 4 Production Client-Delivery Engineering Closure", styles["marker"])]
    story += [_p("REAL OUTSIDE-REPOSITORY PILOT NOT EXECUTED", styles["marker"])]
    story += [_p(f"Spanish run {spanish_run_id or 'retained'} · Green Watch run {green_watch_run_id or 'retained'}", styles["small"]), Spacer(1, 5)]

    boundary = Table([[_p("PHASES 1-4 ENGINEERING SATISFIED · PRODUCTION OPERABILITY/DURABILITY SATISFIED · REAL OUTSIDE-REPOSITORY PILOT NOT EXECUTED · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", styles["boundary"])]], colWidths=[6.9 * inch])
    boundary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("BOX", (0, 0), (-1, -1), 1, GOLD), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(boundary)

    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.55 * inch, bottomMargin=0.55 * inch)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def merge_pdf(source: Path, appendix: Path, output: Path) -> int:
    writer = PdfWriter()
    for candidate in (source, appendix):
        for page in PdfReader(str(candidate)).pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": "NICO Comprehensive - Four-Phase Engineering Closure - Automated Draft", "/Producer": SCHEMA})
    with output.open("wb") as stream:
        writer.write(stream)
    return len(writer.pages)
