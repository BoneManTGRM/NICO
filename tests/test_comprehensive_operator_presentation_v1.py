"""Lifecycle correction preserves a real retained decision, never creates one."""
import base64
import hashlib
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_operator_presentation_v1 import _render_source, lifecycle_text, render_operator_presentation
from nico import comprehensive_operator_approval_v1 as approval
from nico.comprehensive_review_decision_v1 import report_package_from_record
from tests.test_comprehensive_operator_approval_v1 import service, current, payload


@pytest.mark.parametrize("spanish", [False, True])
def test_blue_cover_approval_changes_without_changing_delivery_or_pending_findings(spanish):
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    lines = (["Postura ejecutiva", "REVISIÓN HUMANA", "Pendiente", "ENTREGA AL CLIENTE", "Bloqueada",
              "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"]
             if spanish else ["Executive posture", "HUMAN REVIEW", "Pending", "CLIENT DELIVERY", "Blocked",
                              "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"])
    lines += ["Finding evidence: pending human disposition", "QC 0/9", "Score 93/100"]
    for i, line in enumerate(lines):
        c.drawString(30, 750 - i * 25, line)
    c.save()
    source = stream.getvalue()
    result, changes = _render_source(source)
    text = PdfReader(io.BytesIO(result)).pages[0].extract_text()
    assert ("APROBACIÓN OPERADOR\nAprobado" if spanish else "OPERATOR APPROVAL\nApproved") in text
    assert ("ENTREGA AL CLIENTE\nBloqueada" if spanish else "CLIENT DELIVERY\nBlocked") in text
    assert ("BORRADOR AUTOMATIZADO" if spanish else "AUTOMATED DRAFT") not in text
    assert "Finding evidence: pending human disposition" in text
    assert "QC 0/9" in text and "Score 93/100" in text
    assert changes
    assert _render_source(source)[0] == result


def test_old_approval_renders_corrected_export_without_mutating_receipt_or_source(service):
    before = current(service)
    stored = approval.approve_operator_report(service, before["identity"]["run_id"], payload(before))
    original = deepcopy(stored)
    retained = approval.validated_operator_edition(stored)
    result = render_operator_presentation(stored, retained)
    assert stored == original == current(service)
    assert result["review"] == retained["review"]
    assert result["source_review_artifact_identity"] == retained["source_review_artifact_identity"]
    assert result["rendering_derivation"]["new_human_approval"] is False
    assert result["rendering_derivation"]["authoritative_approval_manifest_sha256"] == retained["accepted_edition_manifest_sha256"]
    assert result["rendering_derivation"]["original_approved_pdf_sha256"] == retained["reports"]["pdf_sha256"]
    pdf = base64.b64decode(result["reports"]["pdf_base64"])
    assert hashlib.sha256(pdf).hexdigest() == result["artifact_digests"]["pdf"]["sha256"]
    assert result["reports"]["pdf_sha256"] != retained["reports"]["pdf_sha256"]
    manifest = dict(result)
    digest = manifest.pop("accepted_edition_manifest_sha256")
    assert digest == canonical_sha256(manifest)
    pages = PdfReader(io.BytesIO(pdf)).pages
    text = "\n".join(p.extract_text() for p in pages)
    assert "AUTOMATED DRAFT" not in text
    assert "OPERATOR APPROVAL\nApproved" in text
    assert "CLIENT DELIVERY\nBlocked" in text
    assert result["review"]["review_disclosure"]["specialist_review_completed"] is False
    assert result["review"]["client_delivery_allowed"] is False
    assert render_operator_presentation(stored, retained) == result
    assert approval.presented_operator_identity(stored, retained)["artifact_digests"]["pdf"] == result["artifact_digests"]["pdf"]
    # The correction audit accounts for every changed text fragment, and preserves
    # all technical text between them. No arbitrary Pending -> Approved replacement.
    source = PdfReader(io.BytesIO(base64.b64decode(report_package_from_record(before)["pdf_base64"])))
    assert len(pages) > len(source.pages)
    for change in result["rendering_derivation"]["lifecycle_text_changes"]:
        assert change["before"] != change["after"]
    damaged = deepcopy(stored)
    damaged["review_work_ledger"] = {"changed": True}
    assert approval.project_operator_approval({}, damaged, include_reports=True)["operator_approval_status"].startswith("invalidated")


def test_approval_table_keeps_specialist_risk_pending():
    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    lines = ["Human Review and Exact-Artifact Approval", "Reviewer identity", "Pending",
             "Decision", "pending", "Residual-risk acceptance", "Pending", "Client delivery: Blocked"]
    for i, line in enumerate(lines):
        c.drawString(30, 750-i*25, line)
    c.save()
    result, _ = _render_source(stream.getvalue())
    text = PdfReader(io.BytesIO(result)).pages[0].extract_text()
    assert "Reviewer identity\nSee certificate" in text
    assert "Decision\nApproved" in text
    assert "Specialist risk acceptance\nPending" in text
    assert "Client delivery: Blocked" in text


def test_pending_evidence_and_quoted_status_text_are_not_approval_labels():
    for text in ["Pending", "finding review pending", "QC required", "AUTOMATED DRAFT",
                 "PENDING HUMAN APPROVAL", "Score effect: authorized human disposition remains pending",
                 "BLOCKED - missing scanner evidence"]:
        assert lifecycle_text(text) == text
