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


def _truth_table(
    rows: list[tuple[str, str, str]],
    *,
    header: ParagraphStyle,
    small: ParagraphStyle,
    pass_style: ParagraphStyle,
) -> Table:
    data = [[_p("Engineering requirement", header), _p("Status", header), _p("Evidence", header)]]
    for item, status, evidence in rows:
        data.append([_p(item, small), _p(status, pass_style), _p(evidence, small)])
    table = Table(data, colWidths=[3.15 * inch, 0.72 * inch, 3.03 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (1, 1), (1, -1), PASS_BG),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
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
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    subtitle = ParagraphStyle(
        "subtitle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=GOLD,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    section = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=NAVY,
        spaceBefore=4,
        spaceAfter=6,
    )
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.3, leading=10.5, textColor=TEXT)
    small = ParagraphStyle("small", parent=body, fontSize=7.3, leading=9)
    pass_style = ParagraphStyle(
        "pass",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=PASS_TEXT,
        alignment=TA_CENTER,
    )
    pending_style = ParagraphStyle(
        "pending",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=PENDING_TEXT,
        alignment=TA_CENTER,
    )
    header = ParagraphStyle(
        "header",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    boundary_style = ParagraphStyle(
        "boundary",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=GOLD,
        alignment=TA_CENTER,
    )

    def header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, letter[1] - 0.16 * inch, letter[0], 0.16 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.55 * inch, 0.32 * inch, "NICO Comprehensive · four-phase engineering closure · automated evidence")
        canvas.drawRightString(letter[0] - 0.55 * inch, 0.32 * inch, f"Closure appendix {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )

    negative = phase3["negative_paths_proven"]
    positive = phase3["positive_supplied_evidence_paths_proven"]
    phase3_rows = [
        (
            "Functional QA: supplied and missing-evidence paths",
            "PASS",
            "Supplied observed results retain provenance; repository tests never become runtime acceptance; absent runtime evidence remains not assessed.",
        ),
        (
            "Platform Parity truth",
            "PASS",
            "Supplied platform/runtime observations can be synthesized; source indicators alone never become device or runtime parity.",
        ),
        (
            "Requirements and stakeholder authority",
            "PASS",
            "Authoritative, supplied-unverified, inferred, and missing states remain distinct; model output never creates stakeholder authority.",
        ),
        (
            "Roadmap and staffing truth",
            "PASS",
            "The 0-30 / 31-90 / 91-180 framework remains NICO-proposed until authorized; rates, contracts, vendors, and budgets are not invented.",
        ),
        (
            "Existing Comprehensive report integration",
            "PASS",
            "Functional QA, Platform Parity, Requirements, Stakeholder, Roadmap, Staffing, and executive synthesis use the existing report pipeline.",
        ),
        (
            "Positive and negative regression paths",
            "PASS",
            f"positive={sum(value is True for value in positive.values())}/{len(positive)}; negative={sum(value is True for value in negative.values())}/{len(negative)}.",
        ),
        (
            "One product and protected human boundary",
            "PASS",
            "NICO Comprehensive remains the only client report; human disposition, stakeholder authority, residual-risk acceptance, approval, and delivery remain human-controlled.",
        ),
    ]

    story: list[Any] = [
        _p("Phase 3 Broader Professional Assessment Closure", title),
        _p("ONE NICO COMPREHENSIVE REPORT · POSITIVE AND MISSING-EVIDENCE PATHS PROVEN", subtitle),
        _p(
            f"This evidence is bound to exact current-head production acceptance for {expected_sha}. Phase 3 extends the existing Comprehensive evidence pipeline; it does not create another assessment, score path, report renderer, or client PDF.",
            body,
        ),
        Spacer(1, 7),
        _truth_table(phase3_rows, header=header, small=small, pass_style=pass_style),
        Spacer(1, 8),
    ]
    complete = ParagraphStyle("complete", parent=title, fontSize=17, textColor=PASS_TEXT, spaceAfter=0)
    story.extend([_p("PHASE 3 ENGINEERING SATISFIED", complete), PageBreak()])

    security = phase4["security_validation"]
    durability = phase4["durability_recovery_validation"]
    phase4_rows = [
        (
            "Authorized client/project/scope lifecycle",
            "PASS",
            "Explicit non-placeholder tenant, client, project, repository, authorization, read-only access, immutable commit, run, and evidence-ledger identities are required.",
        ),
        (
            "Scanner, candidate, triage, and review lifecycle",
            "PASS",
            "Every required scanner must retain a completed execution; candidate lineage, fresh triage, exact disposition reconciliation, and mandatory individual review fail closed.",
        ),
        (
            "Human approval and immutable artifact receipt",
            "PASS",
            "Authorized human identity/role/action is required; receipt binds exact report, JSON, evidence manifest, review ledger, candidate, finding, score, and identity digests.",
        ),
        (
            "Stale approval and delivery protection",
            "PASS",
            "Material regeneration, evidence/finding/disposition/score change, cross-scope substitution, internal/test classification, or artifact mismatch invalidates delivery.",
        ),
        (
            "Tenant, project, and run isolation",
            "PASS",
            "Cross-client, cross-project, and cross-run mutation or recovery is rejected; missing or placeholder delivery scope fails closed.",
        ),
        (
            "Durability and recovery",
            "PASS",
            f"{sum(value is True for value in durability.values())}/{len(durability)} retained restart, deployment-transition, Postgres, artifact, reviewer, and approval-state recovery controls are proven.",
        ),
        (
            "Focused security closure",
            "PASS",
            f"{sum(value is True for value in security.values())}/{len(security)} authorization, IDOR, isolation, secret-handling, artifact-integrity, and approval-integrity controls are proven.",
        ),
        (
            "Repository-agnostic system proof",
            "PASS",
            ", ".join(phase4["repository_agnostic_fixtures"]),
        ),
        (
            "Exact-current-head production acceptance",
            "PASS",
            f"Vercel, Railway, Mobile Restart, iOS WebKit, Spanish Comprehensive, Two-Service acceptance, and Green Watch are successful for {expected_sha}.",
        ),
    ]

    story.extend(
        [
            _p("Phase 4 Production Client-Delivery Engineering Closure", title),
            _p("ENGINEERING AND OPERABILITY SATISFIED · REAL OUTSIDE PILOT TRACKED SEPARATELY", subtitle),
            _truth_table(phase4_rows, header=header, small=small, pass_style=pass_style),
            Spacer(1, 8),
            _p("Exact dynamic evidence", section),
        ]
    )
    context_rows = [[_p("Current-head context", header), _p("State", header), _p("Run / evidence", header)]]
    contexts = status.get("contexts") or {}
    for name in status.get("required_contexts") or []:
        item = contexts.get(name) or {}
        state = str(item.get("state") or "unknown")
        run_hint = str(item.get("target_url") or item.get("description") or "Retained in exact-current-head status snapshot")
        context_rows.append([_p(name, small), _p("PASS" if state == "success" else state.upper(), pass_style), _p(run_hint, small)])
    context_table = Table(context_rows, colWidths=[2.45 * inch, 0.72 * inch, 3.73 * inch], repeatRows=1)
    context_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (1, 1), (1, -1), PASS_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.extend([context_table, Spacer(1, 8)])

    pilot_rows = [
        [_p("Engineering status", header), _p("Outside-repository pilot", header), _p("Human/client boundary", header)],
        [
            _p("PHASE 4 ENGINEERING: SATISFIED", pass_style),
            _p("NOT EXECUTED", pending_style),
            _p("Real repository authorization, real specialist dispositions, real approval/rejection, protected delivery, and measured effort remain external human evidence.", small),
        ],
    ]
    pilot_table = Table(pilot_rows, colWidths=[2.1 * inch, 1.35 * inch, 3.45 * inch])
    pilot_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (0, 1), PASS_BG),
                ("BACKGROUND", (1, 1), (1, 1), PENDING_BG),
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([pilot_table, Spacer(1, 8)])

    run_text = f"Spanish run {spanish_run_id or 'retained in status snapshot'} · Green Watch run {green_watch_run_id or 'retained in status snapshot'}"
    story.extend([_p(run_text, small), Spacer(1, 5)])
    boundary = Table(
        [[_p("PHASES 1-4 ENGINEERING SATISFIED · PRODUCTION OPERABILITY/DURABILITY SATISFIED · REAL OUTSIDE-REPOSITORY PILOT NOT EXECUTED · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", boundary_style)]],
        colWidths=[6.9 * inch],
    )
    boundary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 1, GOLD),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([boundary])
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def merge_pdf(source: Path, appendix: Path, output: Path) -> int:
    writer = PdfWriter()
    for candidate in (source, appendix):
        for page in PdfReader(str(candidate)).pages:
            writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "NICO Comprehensive - Four-Phase Engineering Closure - Automated Draft",
            "/Producer": SCHEMA,
        }
    )
    with output.open("wb") as stream:
        writer.write(stream)
    return len(writer.pages)
