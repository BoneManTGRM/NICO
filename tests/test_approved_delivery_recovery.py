from __future__ import annotations

import base64
from uuid import uuid4

from nico.approved_delivery_recovery import approved_delivery_status, attach_verified_approved_delivery
from nico.approved_delivery_verification import verify_approved_delivery_artifact
from nico.full_assessment_delivery import build_approved_delivery_artifact
from nico.storage import STORE


def _identity() -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:10]
    return (
        f"fullrun_recovery_{suffix}",
        f"report_recovery_{suffix}",
        f"approval_recovery_{suffix}",
        f"customer_recovery_{suffix}",
        f"project_recovery_{suffix}",
    )


def _source_pdf() -> bytes:
    return b"%PDF-1.4\nrecovery-source-draft\n%%EOF\n"


def _approved_records() -> tuple[dict, dict]:
    run_id, report_id, approval_id, customer_id, project_id = _identity()
    report = {
        "status": "complete",
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "formats": {
            "pdf": base64.b64encode(_source_pdf()).decode("ascii"),
            "json": {
                "status": "draft",
                "report_path": "full_run",
                "run_id": run_id,
                "report_id": report_id,
                "customer_id": customer_id,
                "project_id": project_id,
                "repository": "BoneManTGRM/NICO",
                "executive_summary": "Recovery verification fixture.",
                "maturity_signal": {"level": "Senior", "score": 91},
                "evidence_ledger": {"status": "complete"},
                "client_delivery_verdict": {"status": "human_review_required", "blockers": []},
                "sections": [],
                "unavailable_data_notes": [],
            },
        },
    }
    approved_at = "2026-07-11T18:00:00Z"
    candidate = {
        "approval_id": approval_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "requested_action": "final_report_approval",
        "status": "pending",
        "run_id": run_id,
        "report_id": report_id,
        "approver": "technical_reviewer",
        "review_decision": {
            "state": "approved",
            "actor": "technical_reviewer",
            "note": "Reviewed exact draft.",
            "decided_at": approved_at,
            "client_delivery_allowed": True,
        },
    }
    artifact = build_approved_delivery_artifact(report, candidate, approved_at=approved_at)
    assert artifact["status"] == "complete"
    report["approved_delivery"] = artifact
    report["delivery_status"] = "approved"
    report["client_delivery_allowed"] = True
    approval = {
        **candidate,
        "status": "approved",
        "approved_delivery": {
            "status": artifact["status"],
            "pdf_sha256": artifact["pdf_sha256"],
            "source_draft_pdf_sha256": artifact["source_draft_pdf_sha256"],
            "approval_identity_sha256": artifact["approval_identity_sha256"],
        },
    }
    return report, approval


def _store(report: dict, approval: dict) -> None:
    STORE.put("reports", report["report_id"], report)
    STORE.put("approvals", approval["approval_id"], approval)


def test_verify_approved_delivery_recomputes_all_hashes_and_bindings():
    report, approval = _approved_records()

    verification = verify_approved_delivery_artifact(report, approval)

    assert verification["status"] == "verified"
    assert verification["verified"] is True
    assert all(item["passed"] for item in verification["checks"])
    assert verification["computed"]["pdf_sha256"] == report["approved_delivery"]["pdf_sha256"]
    assert verification["computed"]["source_draft_pdf_sha256"] == report["approved_delivery"]["source_draft_pdf_sha256"]
    assert verification["computed"]["approval_identity_sha256"] == report["approved_delivery"]["approval_identity_sha256"]


def test_verify_approved_delivery_blocks_tampered_approved_pdf():
    report, approval = _approved_records()
    report["approved_delivery"]["pdf_base64"] = base64.b64encode(b"%PDF-1.4\ntampered\n%%EOF\n").decode("ascii")

    verification = verify_approved_delivery_artifact(report, approval)

    assert verification["status"] == "blocked"
    assert verification["verified"] is False
    assert "approved PDF SHA-256" in " ".join(verification["blockers"])


def test_verify_approved_delivery_blocks_changed_approval_time():
    report, approval = _approved_records()
    approval["review_decision"]["decided_at"] = "2026-07-11T18:01:00Z"

    verification = verify_approved_delivery_artifact(report, approval)

    assert verification["verified"] is False
    assert "approval time" in " ".join(verification["blockers"])


def test_recovery_returns_pdf_only_when_requested_and_verified():
    report, approval = _approved_records()
    _store(report, approval)

    metadata_only = approved_delivery_status(
        report["run_id"],
        customer_id=report["customer_id"],
        project_id=report["project_id"],
        include_pdf=False,
    )
    with_pdf = approved_delivery_status(
        report["report_id"],
        customer_id=report["customer_id"],
        project_id=report["project_id"],
        include_pdf=True,
    )

    assert metadata_only["status"] == "verified"
    assert metadata_only["client_ready"] is True
    assert "pdf_base64" not in metadata_only["approved_delivery"]
    assert with_pdf["verified"] is True
    assert with_pdf["approved_delivery"]["pdf_base64"] == report["approved_delivery"]["pdf_base64"]


def test_recovery_blocks_wrong_customer_or_project_scope():
    report, approval = _approved_records()
    _store(report, approval)

    result = approved_delivery_status(
        report["run_id"],
        customer_id="different_customer",
        project_id=report["project_id"],
        include_pdf=True,
    )

    assert result["status"] == "blocked"
    assert result["verified"] is False
    assert "scope does not match" in result["error"]
    assert "approved_delivery" not in result


def test_recovery_never_returns_tampered_pdf_bytes():
    report, approval = _approved_records()
    report["approved_delivery"]["pdf_base64"] = base64.b64encode(b"%PDF-1.4\ntampered\n%%EOF\n").decode("ascii")
    _store(report, approval)

    result = approved_delivery_status(
        report["run_id"],
        customer_id=report["customer_id"],
        project_id=report["project_id"],
        include_pdf=True,
    )

    assert result["status"] == "blocked"
    assert result["client_delivery_allowed"] is False
    assert "pdf_base64" not in result["approved_delivery"]
    assert result["verification"]["verified"] is False


def test_full_assessment_response_truth_changes_only_after_verified_recovery():
    report, approval = _approved_records()
    _store(report, approval)
    result = {
        "status": "complete",
        "run_id": report["run_id"],
        "customer_id": report["customer_id"],
        "project_id": report["project_id"],
        "human_review_required": True,
        "client_ready": False,
        "reports": {"report_id": report["report_id"], "client_delivery_allowed": False},
    }

    attached = attach_verified_approved_delivery(result, include_pdf=True)

    assert attached["approved_delivery_recovery"]["verified"] is True
    assert attached["client_ready"] is True
    assert attached["human_review_required"] is False
    assert attached["delivery_verdict"] == "approved"
    assert attached["reports"]["client_delivery_allowed"] is True
    assert attached["approved_delivery"]["pdf_base64"] == report["approved_delivery"]["pdf_base64"]


def test_full_assessment_response_remains_review_blocked_when_recovery_fails():
    report, approval = _approved_records()
    report["approved_delivery"]["approval_identity_sha256"] = "0" * 64
    _store(report, approval)
    result = {
        "status": "complete",
        "run_id": report["run_id"],
        "customer_id": report["customer_id"],
        "project_id": report["project_id"],
        "human_review_required": True,
        "client_ready": False,
        "reports": {"report_id": report["report_id"], "client_delivery_allowed": False},
    }

    attached = attach_verified_approved_delivery(result, include_pdf=True)

    assert attached["approved_delivery_recovery"]["verified"] is False
    assert attached["client_ready"] is False
    assert attached["human_review_required"] is True
    assert attached["reports"]["client_delivery_allowed"] is False
    assert "approved_delivery" not in attached
