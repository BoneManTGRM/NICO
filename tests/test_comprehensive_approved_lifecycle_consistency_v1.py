from __future__ import annotations

import base64
import hashlib
import io
import json

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_approved_lifecycle_consistency_v1 import (
    install_approved_lifecycle_consistency,
)


def _pdf_with_stale_lifecycle() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.setFont("Helvetica", 10)
    for index, line in enumerate(
        (
            "AUTOMATED DRAFT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
            "Review state: pending human approval",
            "Approval state: pending human approval",
            "Reviewer identity: pending",
            "Reviewer authorization: pending",
            "Decision: pending",
            "CLIENT DELIVERY NOT AUTHORIZED",
        )
    ):
        document.drawString(54, 720 - (index * 28), line)
    document.save()
    return buffer.getvalue()


def test_approved_report_removes_stale_lifecycle_from_all_formats():
    from nico import comprehensive_approved_report_v1 as approved

    installed = install_approved_lifecycle_consistency()
    assert installed["cross_format_fail_closed"] is True

    pdf = _pdf_with_stale_lifecycle()
    stale = """# Review

Review state: pending human approval
Approval state: pending human approval
Reviewer identity: pending
Reviewer authorization: pending
Decision: pending
CLIENT DELIVERY NOT AUTHORIZED
"""
    package = {
        "json": {
            "identity": {
                "run_id": "comprun_lifecycle_consistency",
                "repository": "owner/repository",
                "commit_sha": "a" * 40,
                "report_language": "en",
            },
            "approval_record": {
                "review_state": "pending human approval",
                "approval_state": "pending human approval",
                "reviewer_identity": "pending",
                "reviewer_authorization": "pending",
                "decision": "pending",
                "client_delivery": "not authorized",
            },
            "report_finality": "automated_draft",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "client_delivery_allowed": False,
        },
        "markdown": stale,
        "html": f"<article><pre>{stale}</pre></article>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_filename": "nico-comprehensive-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf",
    }

    result = approved.build_approved_report_package(
        package,
        reviewer="Qualified Specialist",
        reviewer_role="Cybersecurity specialist",
        decision_reason="Exact artifact and disclosed limitations reviewed.",
        decided_at="2026-09-04T16:30:00Z",
    )

    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(
            io.BytesIO(base64.b64decode(result["pdf_base64"], validate=True))
        ).pages
    )
    surfaces = {
        "json": json.dumps(result["json"], sort_keys=True),
        "markdown": result["markdown"],
        "html": result["html"],
        "pdf": pdf_text,
    }
    forbidden = (
        "pending human approval",
        "reviewer identity: pending",
        "reviewer authorization: pending",
        "decision: pending",
        "client delivery blocked",
        "client delivery not authorized",
    )
    for surface in surfaces.values():
        normalized = surface.casefold()
        assert all(token not in normalized for token in forbidden)

    record = result["json"]["approval_record"]
    assert record["review_state"] == "approved"
    assert record["approval_state"] == "approved"
    assert record["reviewer_identity"] == "Qualified Specialist"
    assert record["reviewer_authorization"] == "Cybersecurity specialist"
    assert record["decision"] == "approved"
    assert record["client_delivery"] == "certificate_controlled"
    assert result["report_finality"] == "approved_final"
    assert result["approval_status"] == "approved_final"
    assert result["client_delivery_allowed"] is False
    assert result["approved_lifecycle_consistency"]["status"] == "valid"
