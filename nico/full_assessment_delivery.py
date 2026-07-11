from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from typing import Any

APPROVED_DELIVERY_STYLE_VERSION = "full-assessment-approved-delivery-v1"


def _text(value: Any, limit: int = 1400) -> str:
    cleaned = str(value or "")
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-").replace("\u2022", "-")
    cleaned = re.sub(r"https?://\S+", "[link omitted]", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 16)].rstrip() + "... [truncated]"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_filename(repository: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", repository.replace("/", "-"))
    normalized = normalized.strip("-._") or "assessment"
    return f"nico-full-assessment-{normalized}-approved.pdf"


def _decode_pdf(value: Any) -> bytes:
    encoded = str(value or "").strip()
    if not encoded:
        raise ValueError("The reviewed draft PDF is missing.")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("The reviewed draft PDF is not valid base64.") from exc
    if not decoded.startswith(b"%PDF"):
        raise ValueError("The reviewed draft PDF failed PDF integrity validation.")
    return decoded


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _sha256(canonical)


def _status_color(status: str) -> str:
    lowered = str(status or "").lower()
    if lowered == "green":
        return "#047857"
    if lowered == "yellow":
        return "#b45309"
    if lowered == "red":
        return "#b91c1c"
    return "#64748b"


def _render_approved_pdf(
    assessment: dict[str, Any],
    approval: dict[str, Any],
    *,
    approved_at: str,
    source_draft_pdf_sha256: str,
    approval_identity_sha256: str,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError("Approved Full Assessment PDF export is unavailable because the configured PDF renderer could not be loaded.") from exc

    buffer = io.BytesIO()
    repository = _text(assessment.get("repository") or "Not specified", 240)
    run_id = _text(approval.get("run_id") or assessment.get("run_id") or "Not specified", 180)
    report_id = _text(approval.get("report_id") or assessment.get("report_id") or "Not specified", 180)
    approval_id = _text(approval.get("approval_id") or "Not specified", 180)
    approver = _text(approval.get("approver") or approval.get("review_decision", {}).get("actor") or "Not specified", 180)
    approval_note = _text(approval.get("review_decision", {}).get("note") or "Approved after human review.", 700)
    client_name = _text(assessment.get("client_name") or "Not specified", 180)
    project_name = _text(assessment.get("project_name") or "Not specified", 180)
    maturity = _dict(assessment.get("maturity_signal"))
    ledger = _dict(assessment.get("evidence_ledger"))
    sections = [item for item in _list(assessment.get("sections")) if isinstance(item, dict)]
    verdict = _dict(assessment.get("client_delivery_verdict"))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.56 * inch,
        leftMargin=0.56 * inch,
        topMargin=0.50 * inch,
        bottomMargin=0.72 * inch,
        title="NICO Full Assessment - Approved Client Delivery",
        author="NICO",
        subject="Human-approved, evidence-bound Full Assessment client delivery artifact",
    )
    styles = getSampleStyleSheet()
    hero_brand = ParagraphStyle("ApprovedHeroBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=30, leading=32, textColor=colors.white, alignment=1, spaceAfter=1)
    hero_powered = ParagraphStyle("ApprovedHeroPowered", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#a7f3d0"), alignment=1, spaceAfter=4)
    hero_title = ParagraphStyle("ApprovedHeroTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=colors.HexColor("#ecfdf5"), alignment=1, spaceAfter=2)
    hero_status = ParagraphStyle("ApprovedHeroStatus", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#fde68a"), alignment=1)
    h2 = ParagraphStyle("ApprovedH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.4, leading=15, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=4, keepWithNext=True)
    h3 = ParagraphStyle("ApprovedH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.5, leading=11.5, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=2, keepWithNext=True)
    body = ParagraphStyle("ApprovedBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.25, leading=10.7, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("ApprovedSmall", parent=body, fontSize=7.45, leading=9.2, textColor=colors.HexColor("#475569"), spaceAfter=1.8)
    label = ParagraphStyle("ApprovedLabel", parent=small, fontName="Helvetica-Bold", fontSize=7, leading=8.3, textColor=colors.HexColor("#64748b"), spaceAfter=1)
    metric = ParagraphStyle("ApprovedMetric", parent=body, fontName="Helvetica-Bold", fontSize=10.8, leading=12.5, textColor=colors.HexColor("#0f172a"))
    approved_callout = ParagraphStyle("ApprovedCallout", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=10.8, textColor=colors.HexColor("#065f46"), backColor=colors.HexColor("#d1fae5"), borderColor=colors.HexColor("#10b981"), borderWidth=0.8, borderPadding=7, spaceAfter=7)
    disclosure = ParagraphStyle("ApprovedDisclosure", parent=body, fontName="Helvetica-Bold", fontSize=8.2, leading=10.5, textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=7)

    def p(value: Any, style: Any, limit: int = 1400) -> Any:
        return Paragraph(html.escape(_text(value, limit)), style)

    def bullets(values: list[Any], max_items: int = 6) -> list[Any]:
        cleaned = [_text(item, 560) for item in values if _text(item, 560)]
        if not cleaned:
            return [p("No item returned.", small)]
        output = [p(f"- {item}", small, 600) for item in cleaned[:max_items]]
        if len(cleaned) > max_items:
            output.append(p(f"- {len(cleaned) - max_items} additional item(s) remain available in the stored report package.", small))
        return output

    footer_left = "NICO Full Assessment - approved client delivery - evidence limitations preserved"
    footer_right = f"Approval {approval_id}"

    def draw_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d1fae5"))
        canvas.line(document.leftMargin, 0.52 * inch, document.pagesize[0] - document.rightMargin, 0.52 * inch)
        canvas.setFont("Helvetica", 7.1)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.33 * inch, footer_left)
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.33 * inch, f"{footer_right} - Page {canvas.getPageNumber()}")
        canvas.restoreState()

    hero = Table(
        [[p("NICO", hero_brand)], [p("POWERED BY REPARODYNAMICS", hero_powered)], [p("Full Assessment", hero_title)], [p("APPROVED FOR CLIENT DELIVERY", hero_status)]],
        colWidths=[7.08 * inch],
    )
    hero.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#064e3b")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))

    metadata = Table(
        [
            [p("Repository", label), p(repository, small), p("Run ID", label), p(run_id, small)],
            [p("Client", label), p(client_name, small), p("Project", label), p(project_name, small)],
            [p("Report ID", label), p(report_id, small), p("Approval ID", label), p(approval_id, small)],
            [p("Approved by", label), p(approver, small), p("Approved at", label), p(approved_at, small)],
        ],
        colWidths=[0.82 * inch, 2.58 * inch, 0.82 * inch, 2.86 * inch],
    )
    metadata.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))

    metrics = Table(
        [[
            [p("MATURITY", label), p(maturity.get("level", "Unknown"), metric)],
            [p("TECHNICAL SCORE", label), p(f"{maturity.get('score', 'N/A')}/100", metric)],
            [p("EVIDENCE LEDGER", label), p(str(ledger.get("status") or "missing").replace("_", " ").upper(), metric)],
            [p("DELIVERY", label), p("APPROVED", metric)],
        ]],
        colWidths=[1.62 * inch, 1.72 * inch, 1.72 * inch, 2.02 * inch],
    )
    metrics.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")), ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))

    score_rows = [[p("Area", label), p("Status", label), p("Score", label), p("Summary", label)]]
    for section in sections:
        score_rows.append([p(section.get("label") or section.get("id") or "Section", small, 100), p(str(section.get("status") or "unknown").upper(), small, 40), p(str(section.get("score", "N/A")), small, 20), p(section.get("summary") or "No summary returned.", small, 220)])
    scorecard = Table(score_rows, colWidths=[1.58 * inch, 0.78 * inch, 0.50 * inch, 4.22 * inch], repeatRows=1)
    score_styles: list[tuple[Any, ...]] = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d1fae5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#065f46")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for row_index, section in enumerate(sections, start=1):
        score_styles.append(("TEXTCOLOR", (1, row_index), (2, row_index), colors.HexColor(_status_color(str(section.get("status") or "")))))
    scorecard.setStyle(TableStyle(score_styles))

    story: list[Any] = [
        hero,
        Spacer(1, 0.08 * inch),
        metadata,
        Spacer(1, 0.08 * inch),
        metrics,
        Spacer(1, 0.08 * inch),
        p(f"Human approval recorded. Reviewer: {approver}. Decision note: {approval_note}", approved_callout, 900),
        p("This approval authorizes delivery of this specific artifact. It does not claim exhaustive absence of defects, vulnerabilities, secrets, complexity, or operational risk. All findings, unavailable evidence, confidence limits, and remediation recommendations remain part of the assessment.", disclosure, 900),
        p("Approval Integrity", h2),
        p(f"Source draft PDF SHA-256: {source_draft_pdf_sha256}", small, 180),
        p(f"Approval identity SHA-256: {approval_identity_sha256}", small, 180),
        p("Executive Summary", h2),
        p(assessment.get("executive_summary") or "No executive summary returned.", body, 1200),
        p("Technical Scorecard", h2),
        scorecard,
    ]

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

    action_items = _list(assessment.get("next_steps")) or _list(assessment.get("quick_wins"))
    if action_items:
        story.append(p("Recommended Action Plan", h2))
        story.extend(bullets(action_items, max_items=8))

    blockers = _list(verdict.get("blockers"))
    if blockers:
        story.append(p("Delivery Disclosures and Original Review Blockers", h2))
        story.extend(bullets(blockers, max_items=8))

    unavailable_notes = _list(assessment.get("unavailable_data_notes"))
    if unavailable_notes:
        story.append(p("Unavailable Data Notes", h2))
        story.extend(bullets(unavailable_notes, max_items=8))

    story.append(p("Final statement: This approved Full Assessment is evidence-bound to the exact reviewed report and draft PDF identified above. Approval authorizes client delivery while preserving every disclosed evidence limitation and remediation requirement.", approved_callout, 900))
    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    pdf_bytes = buffer.getvalue()
    if not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("Approved Full Assessment PDF failed integrity validation.")
    return pdf_bytes


def build_approved_delivery_artifact(
    report: dict[str, Any],
    approval: dict[str, Any],
    *,
    approved_at: str,
) -> dict[str, Any]:
    """Build a distinct client-delivery PDF bound to the exact approved draft."""

    if not isinstance(report, dict) or not report:
        return {"status": "blocked", "error": "The exact report package is unavailable."}
    formats = report.get("formats") if isinstance(report.get("formats"), dict) else {}
    assessment = formats.get("json") if isinstance(formats.get("json"), dict) else {}
    if str(assessment.get("report_path") or "") != "full_run":
        return {"status": "blocked", "error": "Approved delivery is limited to Full Assessment report packages."}

    try:
        source_pdf = _decode_pdf(formats.get("pdf"))
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    run_id = str(approval.get("run_id") or "")
    report_id = str(approval.get("report_id") or "")
    approval_id = str(approval.get("approval_id") or "")
    approver = str(approval.get("approver") or approval.get("review_decision", {}).get("actor") or "").strip()
    if not run_id or str(report.get("run_id") or "") != run_id:
        return {"status": "blocked", "error": "The approval run ID does not match the report package."}
    if not report_id or str(report.get("report_id") or "") != report_id:
        return {"status": "blocked", "error": "The approval report ID does not match the report package."}
    if not approval_id or not approver:
        return {"status": "blocked", "error": "Approval ID and human reviewer identity are required for client delivery."}

    source_hash = _sha256(source_pdf)
    identity_payload = {
        "approval_id": approval_id,
        "approved_at": approved_at,
        "approver": approver,
        "report_id": report_id,
        "run_id": run_id,
        "source_draft_pdf_sha256": source_hash,
        "style_version": APPROVED_DELIVERY_STYLE_VERSION,
    }
    approval_hash = _identity_hash(identity_payload)
    try:
        approved_pdf = _render_approved_pdf(
            assessment,
            approval,
            approved_at=approved_at,
            source_draft_pdf_sha256=source_hash,
            approval_identity_sha256=approval_hash,
        )
    except Exception as exc:
        return {"status": "blocked", "error": str(exc) or "Approved Full Assessment PDF rendering failed."}

    approved_pdf_hash = _sha256(approved_pdf)
    return {
        "status": "complete",
        "artifact_type": "approved_full_assessment_pdf",
        "style_version": APPROVED_DELIVERY_STYLE_VERSION,
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "approver": approver,
        "approved_at": approved_at,
        "client_delivery_allowed": True,
        "human_review_completed": True,
        "pdf_base64": base64.b64encode(approved_pdf).decode("ascii"),
        "pdf_filename": _safe_filename(str(assessment.get("repository") or "assessment")),
        "pdf_sha256": approved_pdf_hash,
        "source_draft_pdf_sha256": source_hash,
        "approval_identity_sha256": approval_hash,
        "identity": identity_payload,
        "disclosure": "Approval authorizes delivery of this exact artifact while preserving all findings, unavailable evidence, confidence limits, and remediation requirements.",
    }
