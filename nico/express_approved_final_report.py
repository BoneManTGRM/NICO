from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.storage import STORE, utc_now

VERSION = "nico.express_approved_final_report.v2"


def _assessment_for_run(run_id: str, customer_id: str, project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for row in STORE.list("assessment_runs", customer_id=customer_id or None, project_id=project_id or None):
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        candidate = response or payload
        candidates = {
            str(row.get("id") or ""),
            str(row.get("run_id") or ""),
            str(candidate.get("run_id") or ""),
        }
        if run_id in candidates:
            return row, candidate
    return {}, {}


def _valid_pdf(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("The exact Express final PDF is missing or invalid.") from exc
    if not data.startswith(b"%PDF"):
        raise ValueError("The exact Express final PDF does not begin with a valid PDF header.")
    return data


def _wrap_line(value: str, maximum: int = 92) -> list[str]:
    words = " ".join(str(value or "").split()).split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > maximum:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _certificate_pdf(certificate: dict[str, Any]) -> bytes:
    """Render immutable source identity.

    The final approved-PDF SHA is deliberately not printed inside the PDF because a
    document cannot contain its own final digest without changing that digest. The
    final digest is retained in the approval record and delivery manifest after the
    certificate page has been appended.
    """

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    page.setFillColorRGB(0.02, 0.04, 0.10)
    page.rect(0, 0, width, height, fill=1, stroke=0)
    page.setFillColorRGB(0.22, 0.83, 0.93)
    page.setFont("Helvetica-Bold", 13)
    page.drawString(54, height - 64, "NICO / APPROVAL CERTIFICATE")
    page.setFillColorRGB(1, 1, 1)
    page.setFont("Helvetica-Bold", 28)
    page.drawString(54, height - 112, "Approved Final Report")
    page.setFont("Helvetica", 11)
    page.setFillColorRGB(0.76, 0.82, 0.91)
    page.drawString(54, height - 137, "This certificate is appended to the unchanged evidence-bound Express final report.")

    fields = [
        ("Approval ID", certificate.get("approval_id")),
        ("Reviewer", certificate.get("reviewer")),
        ("Approved at", certificate.get("approved_at")),
        ("Run ID", certificate.get("run_id")),
        ("Report ID", certificate.get("report_id")),
        ("Repository", certificate.get("repository")),
        ("Immutable commit", certificate.get("commit_sha")),
        ("Original report SHA-256", certificate.get("source_report_sha256")),
        ("Evidence bundle SHA-256", certificate.get("evidence_bundle_hash")),
    ]
    y = height - 185
    for label, value in fields:
        page.setFillColorRGB(0.49, 0.83, 0.98)
        page.setFont("Helvetica-Bold", 9)
        page.drawString(54, y, str(label).upper())
        page.setFillColorRGB(0.95, 0.97, 1)
        page.setFont("Helvetica", 10)
        lines = _wrap_line(str(value or "Unavailable"), 88)
        for line in lines:
            y -= 15
            page.drawString(54, y, line)
        y -= 13

    page.setFillColorRGB(0.49, 0.83, 0.98)
    page.setFont("Helvetica-Bold", 9)
    page.drawString(54, y, "REVIEW NOTE")
    page.setFillColorRGB(0.95, 0.97, 1)
    page.setFont("Helvetica", 10)
    for line in _wrap_line(str(certificate.get("note") or "Approved after review of the exact final report and evidence package."), 88):
        y -= 15
        page.drawString(54, y, line)

    page.setFillColorRGB(0.98, 0.45, 0.55)
    page.setFont("Helvetica-Bold", 10)
    page.drawString(54, 66, "CLIENT DELIVERY AUTHORIZED FOR THIS EXACT APPROVED PACKAGE")
    page.setFillColorRGB(0.62, 0.70, 0.82)
    page.setFont("Helvetica", 8)
    page.drawString(54, 45, f"Certificate version: {VERSION}")
    page.save()
    return buffer.getvalue()


def _append_certificate(source_pdf: bytes, certificate_pdf: bytes) -> bytes:
    writer = PdfWriter()
    for source_page in PdfReader(io.BytesIO(source_pdf)).pages:
        writer.add_page(source_page)
    for certificate_page in PdfReader(io.BytesIO(certificate_pdf)).pages:
        writer.add_page(certificate_page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def express_approval_readiness(approval: dict[str, Any]) -> dict[str, Any]:
    run_id = str(approval.get("run_id") or "")
    customer_id = str(approval.get("customer_id") or "default_customer")
    project_id = str(approval.get("project_id") or "default_project")
    _row, assessment = _assessment_for_run(run_id, customer_id, project_id)
    reports = assessment.get("reports") if isinstance(assessment.get("reports"), dict) else {}
    encoded = str(reports.get("pdf_base64") or "")
    blockers: list[str] = []
    try:
        source_pdf = _valid_pdf(encoded)
    except ValueError as exc:
        source_pdf = b""
        blockers.append(str(exc))
    evidence_bundle = assessment.get("evidence_artifact_bundle") if isinstance(assessment.get("evidence_artifact_bundle"), dict) else {}
    if not evidence_bundle.get("bundle_hash"):
        blockers.append("The exact Express evidence-bundle hash is missing.")
    repository_snapshot = assessment.get("repository_snapshot") if isinstance(assessment.get("repository_snapshot"), dict) else {}
    commit_sha = str(assessment.get("commit_sha") or repository_snapshot.get("commit_sha") or "")
    if not commit_sha:
        blockers.append("The immutable commit SHA is missing from the Express final report package.")
    return {
        "status": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "blockers": blockers,
        "run_id": run_id,
        "report_id": str(reports.get("report_id") or approval.get("report_id") or ""),
        "repository": str(assessment.get("repository") or ""),
        "commit_sha": commit_sha,
        "evidence_bundle_hash": str(evidence_bundle.get("bundle_hash") or ""),
        "source_pdf": source_pdf,
        "source_report_sha256": hashlib.sha256(source_pdf).hexdigest() if source_pdf else "",
        "pdf_filename": str(reports.get("pdf_filename") or "nico-express-final-report.pdf"),
    }


def build_express_approved_final_report(approval: dict[str, Any], note: str = "") -> dict[str, Any]:
    readiness = express_approval_readiness(approval)
    if not readiness["ready"]:
        return {"status": "blocked", "error": "Express approved final report could not be created.", "readiness": readiness}

    certificate = {
        "version": VERSION,
        "approval_id": str(approval.get("approval_id") or ""),
        "reviewer": str(approval.get("approver") or approval.get("actor") or "human_reviewer"),
        "approved_at": str(approval.get("decided_at") or approval.get("updated_at") or utc_now()),
        "run_id": readiness["run_id"],
        "report_id": readiness["report_id"],
        "repository": readiness["repository"],
        "commit_sha": readiness["commit_sha"],
        "source_report_sha256": readiness["source_report_sha256"],
        "evidence_bundle_hash": readiness["evidence_bundle_hash"],
        "note": str(note or approval.get("note") or "Approved after review of the exact final report and evidence package."),
        "client_delivery_allowed": True,
        "approved_report_sha256_location": "approval record and delivery manifest",
    }
    approved_pdf = _append_certificate(readiness["source_pdf"], _certificate_pdf(certificate))
    approved_sha = hashlib.sha256(approved_pdf).hexdigest()
    certificate["approved_report_sha256"] = approved_sha

    artifact = {
        "status": "approved",
        "artifact_type": "express_approved_final_report",
        "style_version": VERSION,
        "run_id": readiness["run_id"],
        "report_id": readiness["report_id"],
        "approval_id": certificate["approval_id"],
        "approver": certificate["reviewer"],
        "approved_at": certificate["approved_at"],
        "repository": readiness["repository"],
        "commit_sha": readiness["commit_sha"],
        "client_delivery_allowed": True,
        "pdf_filename": readiness["pdf_filename"].replace(".pdf", "-APPROVED.pdf"),
        "pdf_sha256": approved_sha,
        "source_final_report_sha256": readiness["source_report_sha256"],
        "evidence_bundle_hash": readiness["evidence_bundle_hash"],
        "approval_certificate": certificate,
        "pdf_base64": base64.b64encode(approved_pdf).decode("ascii"),
        "disclosure": "The original Express final report pages are unchanged; one approval certificate page is appended. The final approved-PDF hash is retained outside the PDF to avoid a self-referential digest.",
    }
    updated = deepcopy(approval)
    updated["approved_delivery"] = artifact
    updated["client_delivery_allowed"] = True
    STORE.put("approvals", str(approval.get("approval_id") or ""), updated)
    STORE.audit(
        "express_approved_final_report.created",
        {
            "approval_id": artifact["approval_id"],
            "run_id": artifact["run_id"],
            "pdf_sha256": artifact["pdf_sha256"],
            "source_final_report_sha256": artifact["source_final_report_sha256"],
        },
        customer_id=str(approval.get("customer_id") or "default_customer"),
        project_id=str(approval.get("project_id") or "default_project"),
    )
    return artifact


__all__ = [
    "VERSION",
    "build_express_approved_final_report",
    "express_approval_readiness",
]
