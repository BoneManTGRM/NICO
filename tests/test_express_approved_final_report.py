from __future__ import annotations

import base64
import io
from uuid import uuid4

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.express_approved_final_report import (
    build_express_approved_final_report,
    express_approval_readiness,
)
from nico.storage import STORE


def _pdf() -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    page.drawString(72, 720, "NICO Express final report content")
    page.save()
    return buffer.getvalue()


def _fixture() -> tuple[str, str, str, str]:
    suffix = uuid4().hex[:12]
    run_id = f"express_run_{suffix}"
    approval_id = f"approval_{suffix}"
    customer_id = f"customer_{suffix}"
    project_id = f"project_{suffix}"
    source = _pdf()
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "complete",
            "customer_id": customer_id,
            "project_id": project_id,
            "payload": {
                "run_id": run_id,
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "reports": {
                    "report_id": f"report_{suffix}",
                    "pdf_filename": "nico-express-final-report.pdf",
                    "pdf_base64": base64.b64encode(source).decode("ascii"),
                },
                "evidence_artifact_bundle": {"bundle_hash": "b" * 64},
            },
        },
    )
    STORE.put(
        "approvals",
        approval_id,
        {
            "approval_id": approval_id,
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "requested_action": "client_acceptance_signoff",
            "status": "approved",
            "approver": "Authorized Reviewer",
            "updated_at": "2026-07-23T20:00:00Z",
        },
    )
    return run_id, approval_id, customer_id, project_id


def test_express_approval_readiness_requires_exact_pdf_commit_and_bundle_hash() -> None:
    run_id, approval_id, customer_id, project_id = _fixture()
    approval = STORE.get("approvals", approval_id)

    readiness = express_approval_readiness(approval or {})

    assert readiness["ready"] is True
    assert readiness["run_id"] == run_id
    assert readiness["commit_sha"] == "a" * 40
    assert readiness["evidence_bundle_hash"] == "b" * 64
    assert len(readiness["source_report_sha256"]) == 64


def test_approved_express_pdf_preserves_report_and_appends_certificate() -> None:
    _run_id, approval_id, _customer_id, _project_id = _fixture()
    approval = STORE.get("approvals", approval_id)

    artifact = build_express_approved_final_report(approval or {}, note="Reviewed exact findings and disclosures.")

    assert artifact["status"] == "approved"
    assert artifact["client_delivery_allowed"] is True
    assert artifact["pdf_filename"].endswith("-APPROVED.pdf")
    assert len(artifact["pdf_sha256"]) == 64
    assert len(artifact["source_final_report_sha256"]) == 64
    assert artifact["approval_certificate"]["reviewer"] == "Authorized Reviewer"
    assert artifact["approval_certificate"]["note"] == "Reviewed exact findings and disclosures."

    decoded = base64.b64decode(artifact["pdf_base64"])
    pages = PdfReader(io.BytesIO(decoded)).pages
    assert len(pages) == 2
    first = pages[0].extract_text() or ""
    certificate = pages[1].extract_text() or ""
    assert "NICO Express final report content" in first
    assert "Approved Final Report" in certificate
    assert "Authorized Reviewer" in certificate
    assert "CLIENT DELIVERY AUTHORIZED" in certificate

    stored = STORE.get("approvals", approval_id) or {}
    assert stored["approved_delivery"]["pdf_sha256"] == artifact["pdf_sha256"]
    assert stored["client_delivery_allowed"] is True


def test_approval_artifact_blocks_when_final_pdf_is_missing() -> None:
    suffix = uuid4().hex[:12]
    run_id = f"express_missing_{suffix}"
    approval_id = f"approval_missing_{suffix}"
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "express",
            "status": "complete",
            "customer_id": "customer_missing",
            "project_id": "project_missing",
            "payload": {
                "run_id": run_id,
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "a" * 40,
                "reports": {"report_id": "report_missing", "pdf_base64": ""},
                "evidence_artifact_bundle": {"bundle_hash": "b" * 64},
            },
        },
    )
    approval = {
        "approval_id": approval_id,
        "run_id": run_id,
        "customer_id": "customer_missing",
        "project_id": "project_missing",
        "status": "approved",
    }

    artifact = build_express_approved_final_report(approval)

    assert artifact["status"] == "blocked"
    assert artifact["readiness"]["ready"] is False
    assert any("PDF" in item for item in artifact["readiness"]["blockers"])
