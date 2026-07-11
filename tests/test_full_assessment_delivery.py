from __future__ import annotations

import base64
import hashlib
from uuid import uuid4

from nico import final_review_workflow as review
from nico.full_assessment_delivery import APPROVED_DELIVERY_STYLE_VERSION, build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_delivery_{suffix}",
        f"report_delivery_{suffix}",
        f"approval_delivery_{suffix}",
        f"customer_delivery_{suffix}",
        f"project_delivery_{suffix}",
    )


def _draft_pdf() -> bytes:
    return b"%PDF-1.4\nreviewed-draft-fixture\n%%EOF\n"


def _report(run_id: str, report_id: str, customer_id: str, project_id: str) -> dict:
    source_pdf = _draft_pdf()
    return {
        "status": "complete",
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "formats": {
            "markdown": "# NICO Full Assessment\n",
            "html": "<h1>NICO Full Assessment</h1>",
            "pdf": base64.b64encode(source_pdf).decode("ascii"),
            "json": {
                "status": "draft",
                "report_path": "full_run",
                "report_path_label": "Full Assessment",
                "run_id": run_id,
                "report_id": report_id,
                "repository": "BoneManTGRM/NICO",
                "client_name": "Example Client",
                "project_name": "Example Project",
                "executive_summary": "Evidence-bound technical assessment prepared for human review.",
                "maturity_signal": {"level": "Senior", "score": 91},
                "evidence_ledger": {"status": "complete", "entry_count": 7, "verified_entry_count": 7},
                "export_truth_gate": {"status": "passed"},
                "client_delivery_verdict": {
                    "status": "human_review_required",
                    "blockers": ["Final client delivery requires human review and approval."],
                },
                "sections": [
                    {
                        "id": "dependency_health",
                        "label": "Dependency / Library Ecosystem",
                        "status": "green",
                        "score": 92,
                        "summary": "Dependency evidence was attached for the exact report run.",
                        "verified_claims": ["Dependency scanner evidence was recorded."],
                        "findings": ["Continue routine dependency monitoring."],
                        "unavailable": [],
                    },
                    {
                        "id": "static_analysis",
                        "label": "Static Analysis",
                        "status": "yellow",
                        "score": 84,
                        "summary": "Static analysis evidence is useful but bounded.",
                        "verified_claims": ["Built-in static review completed."],
                        "findings": ["Review remaining medium-confidence patterns."],
                        "unavailable": ["One optional external scanner was unavailable."],
                    },
                ],
                "next_steps": ["Address remaining review-limited evidence.", "Retain the approval and artifact hashes."],
                "unavailable_data_notes": ["Unavailable evidence is not treated as passing proof."],
                "human_review_required": True,
                "client_ready": False,
            },
        },
        "export_truth_gate": {"status": "passed"},
        "client_delivery_allowed": False,
        "human_review_required": True,
    }


def _approval(run_id: str, report_id: str, approval_id: str, customer_id: str, project_id: str) -> dict:
    return {
        "approval_id": approval_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "requested_action": review.FINAL_REVIEW_ACTION,
        "status": "pending",
        "run_id": run_id,
        "report_id": report_id,
        "approver": "technical_reviewer",
        "review_decision": {
            "state": "approved",
            "actor": "technical_reviewer",
            "note": "Reviewed scorecard, evidence limits, unavailable data, and action plan.",
            "decided_at": "2026-07-11T17:00:00Z",
            "client_delivery_allowed": True,
        },
    }


def test_build_approved_delivery_artifact_is_distinct_and_hash_bound():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    approval = _approval(run_id, report_id, approval_id, customer_id, project_id)

    artifact = build_approved_delivery_artifact(report, approval, approved_at="2026-07-11T17:00:00Z")

    assert artifact["status"] == "complete"
    assert artifact["style_version"] == APPROVED_DELIVERY_STYLE_VERSION
    assert artifact["client_delivery_allowed"] is True
    assert artifact["approval_id"] == approval_id
    assert artifact["report_id"] == report_id
    assert artifact["run_id"] == run_id
    approved_pdf = base64.b64decode(artifact["pdf_base64"], validate=True)
    assert approved_pdf.startswith(b"%PDF")
    assert artifact["pdf_sha256"] == hashlib.sha256(approved_pdf).hexdigest()
    assert artifact["source_draft_pdf_sha256"] == hashlib.sha256(_draft_pdf()).hexdigest()
    assert len(artifact["approval_identity_sha256"]) == 64
    assert artifact["pdf_filename"].endswith("-approved.pdf")
    assert report["formats"]["pdf"] != artifact["pdf_base64"]


def test_build_approved_delivery_blocks_mismatched_report_identity():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    approval = _approval(run_id, "different_report", approval_id, customer_id, project_id)

    artifact = build_approved_delivery_artifact(report, approval, approved_at="2026-07-11T17:00:00Z")

    assert artifact["status"] == "blocked"
    assert "report ID does not match" in artifact["error"]


def test_build_approved_delivery_blocks_invalid_source_pdf():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    report["formats"]["pdf"] = base64.b64encode(b"not-a-pdf").decode("ascii")
    approval = _approval(run_id, report_id, approval_id, customer_id, project_id)

    artifact = build_approved_delivery_artifact(report, approval, approved_at="2026-07-11T17:00:00Z")

    assert artifact["status"] == "blocked"
    assert "PDF integrity validation" in artifact["error"]


def test_approval_transition_persists_approved_artifact_without_replacing_draft():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    source_draft = report["formats"]["pdf"]
    approval = _approval(run_id, report_id, approval_id, customer_id, project_id)
    approval["status"] = "pending"
    approval["approver"] = ""
    approval.pop("review_decision", None)
    STORE.put("reports", report_id, report)
    STORE.put("approvals", approval_id, approval)

    result = review.transition_final_review(
        approval_id,
        "approved",
        actor="technical_reviewer",
        note="Reviewed exact draft and approved delivery.",
    )

    assert result["status"] == "ok"
    assert result["approval"]["status"] == "approved"
    assert result["approved_delivery"]["status"] == "complete"
    assert result["approved_delivery"]["client_delivery_allowed"] is True
    stored = STORE.get("reports", report_id)
    assert stored["formats"]["pdf"] == source_draft
    assert stored["approved_delivery"]["pdf_base64"] == result["approved_delivery"]["pdf_base64"]
    assert stored["delivery_status"] == "approved"
    assert stored["client_delivery_allowed"] is True
    assert result["approval"]["approved_delivery"]["pdf_sha256"] == result["approved_delivery"]["pdf_sha256"]


def test_approval_transition_does_not_mark_approved_when_delivery_rendering_fails(monkeypatch):
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    approval = _approval(run_id, report_id, approval_id, customer_id, project_id)
    approval["status"] = "pending"
    approval["approver"] = ""
    approval.pop("review_decision", None)
    STORE.put("reports", report_id, report)
    STORE.put("approvals", approval_id, approval)
    monkeypatch.setattr(
        review,
        "build_approved_delivery_artifact",
        lambda report_value, approval_value, approved_at: {"status": "blocked", "error": "renderer unavailable"},
    )

    result = review.transition_final_review(
        approval_id,
        "approved",
        actor="technical_reviewer",
        note="Attempted approval.",
    )

    assert result["status"] == "blocked"
    assert "renderer unavailable" in result["error"]
    assert STORE.get("approvals", approval_id)["status"] == "pending"
    assert "approved_delivery" not in STORE.get("reports", report_id)


def test_repeated_approved_transition_reuses_same_immutable_artifact():
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = _report(run_id, report_id, customer_id, project_id)
    approval = _approval(run_id, report_id, approval_id, customer_id, project_id)
    approval["status"] = "pending"
    approval["approver"] = ""
    approval.pop("review_decision", None)
    STORE.put("reports", report_id, report)
    STORE.put("approvals", approval_id, approval)

    first = review.transition_final_review(
        approval_id,
        "approved",
        actor="technical_reviewer",
        note="Approved after review.",
    )
    repeated = review.transition_final_review(
        approval_id,
        "approved",
        actor="technical_reviewer",
        note="Repeated click.",
    )

    assert first["status"] == "ok"
    assert repeated["status"] == "ok"
    assert repeated["idempotent_reuse"] is True
    assert repeated["approved_delivery"]["pdf_sha256"] == first["approved_delivery"]["pdf_sha256"]
    assert repeated["approved_delivery"]["approval_identity_sha256"] == first["approved_delivery"]["approval_identity_sha256"]
