from __future__ import annotations

import base64
import hashlib
import io

from reportlab.pdfgen import canvas

from nico import full_assessment_delivery
from nico.full_assessment_delivery_digest_binding_v1 import (
    install_full_assessment_delivery_digest_binding_v1,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(40, 780, "Reviewed NICO automated draft")
    document.showPage()
    document.save()
    return buffer.getvalue()


def _report() -> dict:
    pdf = _pdf()
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    return {
        "run_id": "comprun_delivery_digest",
        "report_id": "report_delivery_digest",
        "draft_artifact_identity": {
            "artifact_schema": "nico.comprehensive-draft-artifact-identity.v1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "3c4352ae1873c547dd01406da833d2faedb5039b",
            "run_id": "comprun_delivery_digest",
            "pdf_sha256": pdf_sha,
            "canonical_json_sha256": "a" * 64,
            "evidence_manifest_sha256": "b" * 64,
            "manifest_id": "NICO-MANIFEST-DELIVERY",
            "report_finality": "automated_draft",
        },
        "formats": {
            "pdf": base64.b64encode(pdf).decode("ascii"),
            "json": {
                "report_path": "full_run",
                "repository": "BoneManTGRM/NICO",
                "run_id": "comprun_delivery_digest",
                "report_id": "report_delivery_digest",
                "maturity_signal": {"level": "Strong", "score": 93},
                "evidence_ledger": {"status": "complete"},
                "sections": [],
                "client_delivery_verdict": {"blockers": []},
                "unavailable_data_notes": [],
            },
        },
    }


def _approval() -> dict:
    return {
        "run_id": "comprun_delivery_digest",
        "report_id": "report_delivery_digest",
        "approval_id": "approval_delivery_digest",
        "approver": "Authorized Reviewer",
        "reviewer_role": "Technical Reviewer",
        "reviewer_authorized": True,
        "review_decision": {
            "actor": "Authorized Reviewer",
            "note": "Approved exact evidence-bound artifact.",
        },
    }


def test_approved_delivery_retains_all_three_source_digests() -> None:
    install_full_assessment_delivery_digest_binding_v1()
    report = _report()
    result = full_assessment_delivery.build_approved_delivery_artifact(
        report,
        _approval(),
        approved_at="2026-08-04T01:00:00Z",
    )
    identity = report["draft_artifact_identity"]

    assert result["status"] == "complete"
    assert result["client_delivery_allowed"] is True
    assert result["source_draft_pdf_sha256"] == identity["pdf_sha256"]
    assert result["source_draft_json_sha256"] == identity["canonical_json_sha256"]
    assert result["source_evidence_manifest_sha256"] == identity[
        "evidence_manifest_sha256"
    ]
    assert result["source_artifact_manifest_id"] == identity["manifest_id"]
    assert result["approved_digests"] == {
        "pdf_sha256": identity["pdf_sha256"],
        "canonical_json_sha256": identity["canonical_json_sha256"],
        "evidence_manifest_sha256": identity["evidence_manifest_sha256"],
    }
    assert result["exact_artifact_identity_verified"] is True
    assert result["regeneration_invalidates_approval"] is True
    assert base64.b64decode(result["pdf_base64"]).startswith(b"%PDF")


def test_digest_mismatch_blocks_approved_delivery() -> None:
    install_full_assessment_delivery_digest_binding_v1()
    approval = _approval()
    approval["approved_json_sha256"] = "c" * 64

    result = full_assessment_delivery.build_approved_delivery_artifact(
        _report(),
        approval,
        approved_at="2026-08-04T01:00:00Z",
    )

    assert result["status"] == "blocked"
    assert result["client_delivery_allowed"] is False
    assert "canonical_json_sha256" in result["error"]


def test_missing_detached_manifest_identity_blocks_delivery() -> None:
    install_full_assessment_delivery_digest_binding_v1()
    report = _report()
    report["draft_artifact_identity"].pop("evidence_manifest_sha256")

    result = full_assessment_delivery.build_approved_delivery_artifact(
        report,
        _approval(),
        approved_at="2026-08-04T01:00:00Z",
    )

    assert result["status"] == "blocked"
    assert result["client_delivery_allowed"] is False
    assert "evidence_manifest_sha256" in result["error"]
