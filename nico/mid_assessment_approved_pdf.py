from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from nico.mid_assessment_report import MID_REPORT_PATH, MID_REPORT_TYPE

APPROVED_REPORT_VERSION = "mid-assessment-approved-v1"
APPROVED_LABEL = "HUMAN REVIEWED — APPROVED"
PAGE_WIDTH, PAGE_HEIGHT = LETTER
LEFT = 54
RIGHT = 54
TOP = 58
BOTTOM = 52
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "mid-assessment"))
    return cleaned.strip("-._") or "mid-assessment"


def _decode_draft_pdf(report: dict[str, Any]) -> bytes:
    formats = _dict(report.get("formats"))
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        return b""
    return pdf if pdf.startswith(b"%PDF") else b""


def approved_source_identity(report: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    decision = _dict(approval.get("review_decision"))
    return {
        "approved_report_version": APPROVED_REPORT_VERSION,
        "report_type": MID_REPORT_TYPE,
        "report_path": MID_REPORT_PATH,
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "source_draft_report_id": report.get("report_id") or "",
        "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
        "source_identity_sha256": report.get("source_identity_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_id": approval.get("approval_id") or "",
        "approval_version": approval.get("approval_version") or "",
        "approved_by": decision.get("actor") or "",
        "approved_at": decision.get("decided_at") or "",
        "approval_note_sha256": hashlib.sha256(str(decision.get("note") or "").encode("utf-8")).hexdigest(),
        "reviewed_item_ids": sorted(str(item) for item in _list(decision.get("reviewed_item_ids")) if str(item)),
    }


def _approved_report_id(identity: dict[str, Any]) -> str:
    return f"mid_approved_report_{_canonical_hash(identity)[:24]}"


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = str(text or "").replace("\n", " ").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_pdf(report: dict[str, Any], approval: dict[str, Any], identity: dict[str, Any]) -> bytes:
    payload = _dict(_dict(report.get("formats")).get("json"))
    sections = [item for item in _list(payload.get("sections")) if isinstance(item, dict)]
    coverage = _dict(payload.get("evidence_coverage"))
    decision = _dict(approval.get("review_decision"))
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=LETTER, pageCompression=1, invariant=1)
    page_number = 0
    y = PAGE_HEIGHT - TOP

    def page_header() -> None:
        nonlocal page_number, y
        page_number += 1
        canvas.setFillColorRGB(0.02, 0.42, 0.24)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(LEFT, PAGE_HEIGHT - 28, APPROVED_LABEL)
        canvas.setFillColorRGB(0.15, 0.18, 0.21)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_WIDTH - RIGHT, 24, f"NICO Mid Assessment · Approved · Page {page_number}")
        canvas.setStrokeColorRGB(0.78, 0.83, 0.80)
        canvas.line(LEFT, PAGE_HEIGHT - 36, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 36)
        canvas.line(LEFT, 36, PAGE_WIDTH - RIGHT, 36)
        y = PAGE_HEIGHT - TOP

    def new_page() -> None:
        canvas.showPage()
        page_header()

    def ensure(height: float) -> None:
        if y - height < BOTTOM:
            new_page()

    def paragraph(text: Any, *, font: str = "Helvetica", size: float = 9.2, leading: float = 12, before: float = 0, after: float = 4) -> None:
        nonlocal y
        lines = _wrap(str(text or ""), font, size, CONTENT_WIDTH)
        ensure(before + len(lines) * leading + after)
        y -= before
        canvas.setFont(font, size)
        canvas.setFillColorRGB(0.12, 0.15, 0.18)
        for line in lines:
            canvas.drawString(LEFT, y, line)
            y -= leading
        y -= after

    def heading(text: str, level: int = 2) -> None:
        nonlocal y
        size = 18 if level == 1 else 13 if level == 2 else 10.5
        leading = size + 4
        ensure(leading + 8)
        y -= 5
        canvas.setFillColorRGB(0.03, 0.28, 0.18)
        canvas.setFont("Helvetica-Bold", size)
        for line in _wrap(text, "Helvetica-Bold", size, CONTENT_WIDTH):
            canvas.drawString(LEFT, y, line)
            y -= leading
        y -= 3

    def bullet(text: str) -> None:
        nonlocal y
        lines = _wrap(text, "Helvetica", 8.8, CONTENT_WIDTH - 16)
        ensure(len(lines) * 11 + 3)
        canvas.setFont("Helvetica", 8.8)
        canvas.setFillColorRGB(0.12, 0.15, 0.18)
        canvas.drawString(LEFT + 2, y, "•")
        for line in lines:
            canvas.drawString(LEFT + 14, y, line)
            y -= 11
        y -= 2

    page_header()
    heading("NICO MID ASSESSMENT", 1)
    paragraph("Human-reviewed approved technical assessment", font="Helvetica-Bold", size=11, leading=14)
    paragraph(f"Repository: {report.get('repository') or ''}")
    paragraph(f"Mid run: {report.get('run_id') or ''}")
    paragraph(f"Snapshot commit: {report.get('snapshot_commit_sha') or ''}", size=8.2)
    paragraph(f"Source draft report: {report.get('report_id') or ''}", size=8.2)
    paragraph(f"Review packet: {report.get('review_packet_id') or ''}", size=8.2)
    heading("Human approval certificate")
    bullet(f"Approval ID: {approval.get('approval_id') or ''}")
    bullet(f"Approved by: {decision.get('actor') or ''}")
    bullet(f"Approved at: {decision.get('decided_at') or ''}")
    bullet(f"Reviewed exception items: {len(_list(decision.get('reviewed_item_ids')))}")
    paragraph("Approval note", font="Helvetica-Bold", before=3, after=2)
    paragraph(decision.get("note") or "No note recorded.")
    heading("Automated evidence coverage")
    paragraph(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)} explicit evidence units)", font="Helvetica-Bold", size=12)
    paragraph(coverage.get("method") or "Coverage was calculated from explicit evidence units.")
    heading("Assessment sections")
    for section in sections:
        heading(str(section.get("label") or section.get("id") or "Section"), 3)
        score = "Not scored" if section.get("score") is None else f"{section.get('score')}/100"
        paragraph(f"Truth status: {section.get('truth_status') or 'Unavailable'} · Score: {score}", font="Helvetica-Bold")
        paragraph(section.get("summary") or "No supported conclusion was available.")
        evidence = _text_list(section.get("evidence"))
        if evidence:
            paragraph("Evidence", font="Helvetica-Bold", before=2, after=2)
            for item in evidence[:12]:
                bullet(item)
        limitations = _text_list(section.get("unavailable")) + _text_list(section.get("missing_evidence_sources")) + _text_list(section.get("failed_evidence_tools"))
        if limitations:
            paragraph("Limitations / unavailable evidence", font="Helvetica-Bold", before=2, after=2)
            for item in limitations[:12]:
                bullet(item)
    heading("Approval and delivery boundary")
    bullet("This PDF is a separate approved artifact. The source draft remains unchanged and retained for audit.")
    bullet("Approval does not itself create a client link or record a client delivery receipt.")
    bullet("Secure delivery remains disabled until the approved artifact passes the dedicated delivery-readiness workflow.")
    bullet("Unsupported claims permitted: 0.")
    heading("Integrity identity")
    paragraph(f"Approved source identity SHA-256: {_canonical_hash(identity)}", size=8)
    paragraph(f"Source draft PDF SHA-256: {identity['source_draft_pdf_sha256']}", size=8)
    paragraph(f"Review packet SHA-256: {identity['review_packet_sha256']}", size=8)
    paragraph(f"Snapshot commit SHA: {identity['snapshot_commit_sha']}", size=8)
    canvas.save()
    return buffer.getvalue()


def build_mid_approved_report(report: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    """Render a separate approved PDF after an exact Mid approval decision."""

    if report.get("record_type") != "mid_assessment_report" or report.get("report_path") != MID_REPORT_PATH:
        return {"status": "blocked", "error": "A valid Mid draft report is required."}
    draft_pdf = _decode_draft_pdf(report)
    if not draft_pdf or hashlib.sha256(draft_pdf).hexdigest() != str(report.get("pdf_sha256") or ""):
        return {"status": "blocked", "error": "The Mid draft PDF failed integrity verification."}
    decision = _dict(approval.get("review_decision"))
    if approval.get("status") != "approved" or decision.get("state") != "approved":
        return {"status": "blocked", "error": "An approved Mid review decision is required."}
    identity = approved_source_identity(report, approval)
    required = [
        "run_id",
        "snapshot_id",
        "snapshot_commit_sha",
        "source_draft_report_id",
        "source_draft_pdf_sha256",
        "source_identity_sha256",
        "review_packet_id",
        "review_packet_sha256",
        "approval_id",
        "approved_by",
        "approved_at",
    ]
    if any(not str(identity.get(key) or "") for key in required):
        return {"status": "blocked", "error": "The approval identity is incomplete."}
    try:
        approved_pdf = _render_pdf(report, approval, identity)
    except Exception as exc:
        return {"status": "blocked", "error": f"Approved Mid PDF rendering failed: {type(exc).__name__}."}
    if not approved_pdf.startswith(b"%PDF"):
        return {"status": "blocked", "error": "Approved Mid PDF rendering did not produce a valid PDF."}
    approved_hash = hashlib.sha256(approved_pdf).hexdigest()
    approved_id = _approved_report_id(identity)
    return {
        "record_type": "mid_approved_report",
        "status": "complete",
        "approval_status": "approved",
        "report_version": APPROVED_REPORT_VERSION,
        "report_type": MID_REPORT_TYPE,
        "report_path": MID_REPORT_PATH,
        "report_id": approved_id,
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "source_draft_report_id": report.get("report_id") or "",
        "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_id": approval.get("approval_id") or "",
        "approved_by": decision.get("actor") or "",
        "approved_at": decision.get("decided_at") or "",
        "approval_identity": identity,
        "approval_identity_sha256": _canonical_hash(identity),
        "pdf_sha256": approved_hash,
        "pdf_filename": f"nico-mid-assessment-{_safe_filename(report.get('repository') or 'repository')}-{_safe_filename(report.get('run_id') or '')}-APPROVED.pdf",
        "formats": {
            "json": {
                "status": "approved",
                "title": "NICO MID ASSESSMENT",
                "approval_label": APPROVED_LABEL,
                "approval_identity": identity,
                "approval_identity_sha256": _canonical_hash(identity),
                "source_draft_report_id": report.get("report_id") or "",
                "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
                "review_packet_id": report.get("review_packet_id") or "",
                "review_packet_sha256": report.get("review_packet_sha256") or "",
                "approved_by": decision.get("actor") or "",
                "approved_at": decision.get("decided_at") or "",
                "reviewed_item_ids": identity["reviewed_item_ids"],
                "human_review_required": False,
                "approved": True,
                "delivery_eligible": True,
                "client_delivery_allowed": False,
                "unsupported_claims_permitted": 0,
                "delivery_note": "A secure delivery grant has not been created. Client delivery remains disabled until the dedicated Mid delivery workflow verifies this approved artifact.",
            },
            "pdf": base64.b64encode(approved_pdf).decode("ascii"),
        },
        "human_review_required": False,
        "approved": True,
        "delivery_eligible": True,
        "client_delivery_allowed": False,
        "delivery_status": "not_configured",
        "unsupported_claims_permitted": 0,
    }
