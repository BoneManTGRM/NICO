from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico.mid_approval_api import (
    MidApprovalDecisionRequest,
    MidApprovalRequest,
    MidReviewDispositionRequest,
    mid_approval_decision_response,
    mid_approval_request_response,
    mid_approved_report_pdf_response,
    mid_review_disposition_response,
)
from nico.mid_assessment_approval import (
    MID_APPROVAL_VERSION,
    get_mid_approved_report,
    request_mid_approval,
    transition_mid_approval,
    validate_mid_approval,
)
from nico.mid_assessment_runs import persist_mid_assessment_run
from nico.mid_optional_evidence import submit_mid_optional_evidence
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_approval_{uuid4().hex[:12]}"


def _section(section_id: str) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": 90,
        "status": "green",
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": [f"Direct evidence for {section_id}."],
        "findings": [],
        "unavailable": [],
    }


def _create_run(run_id: str) -> dict:
    result = {
        "status": "complete",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_approval",
        "project_id": "project_approval",
        "generated_at": "2026-07-11T22:30:00Z",
        "repository_snapshot": {
            "status": "attached",
            "snapshot_id": f"snapshot_{run_id}",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "repository_evidence": {
            "status": "attached",
            "snapshot_commit_sha": "a" * 40,
            "file_evidence": {"files_profiled": 25},
            "dependency_evidence": {"manifest_paths": ["requirements.txt"], "dependency_entries": 8},
            "workflow_evidence": {
                "workflow_file_count": 2,
                "workflow_configuration_snapshot_sha": "a" * 40,
                "jobs_observed": 5,
                "deployments_observed": 1,
            },
            "activity_evidence": {"commits_returned": 12, "pull_requests_returned": 4},
        },
        "complexity_evidence": {"status": "attached", "files_analyzed": 20, "snapshot_commit_sha": "a" * 40},
        "scanner_evidence": {
            "status": "attached",
            "scan_id": f"scan_{run_id}",
            "snapshot_match": True,
            "tools_run": ["pip-audit", "gitleaks", "semgrep"],
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
        },
        "assessment": {
            "status": "draft",
            "sections": [
                _section("code_audit"),
                _section("dependency_health"),
                _section("secrets_review"),
                _section("static_analysis"),
                _section("ci_cd"),
                _section("architecture_debt"),
                _section("velocity_complexity"),
            ],
            "evidence_ledger": {"status": "available", "entry_count": 15, "verified_entry_count": 15, "unavailable_entry_count": 0},
        },
        "reports": {"pdf_base64": ""},
    }
    persist_mid_assessment_run(
        result,
        {
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_approval",
            "project_id": "project_approval",
            "client_name": "Example Client",
            "project_name": "Example Project",
            "authorized": True,
            "authorization_confirmed": True,
            "mode": "mid",
            "build_reports": False,
            "create_final_review_request": False,
        },
    )
    return result


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")


def _request(run_id: str) -> dict:
    return request_mid_approval(run_id, "customer_approval", "project_approval", admin_token="test-admin-token")


def test_request_requires_admin_scope_and_completed_exact_mid_run():
    run_id = _run_id()
    _create_run(run_id)

    unauthorized = request_mid_approval(run_id, "customer_approval", "project_approval", admin_token="wrong")
    wrong_scope = request_mid_approval(run_id, "wrong", "project_approval", admin_token="test-admin-token")

    assert unauthorized["status"] == "blocked"
    assert unauthorized["admin_write"]["configured"] is True
    assert wrong_scope["status"] == "not_found"
    assert "snapshot" not in repr(wrong_scope).lower()


def test_request_creates_hash_bound_pending_approval_and_is_idempotent():
    run_id = _run_id()
    _create_run(run_id)

    first = _request(run_id)
    second = _request(run_id)
    approval = first["approval"]

    assert first["status"] == "requested"
    assert first["idempotent_reuse"] is False
    assert second["idempotent_reuse"] is True
    assert approval["approval_version"] == MID_APPROVAL_VERSION
    assert approval["status"] == "pending"
    assert approval["run_id"] == run_id
    assert approval["snapshot_commit_sha"] == "a" * 40
    assert len(approval["draft_pdf_sha256"]) == 64
    assert len(approval["truth_sha256"]) == 64
    assert len(approval["review_packet_sha256"]) == 64
    assert approval["exception_item_count"] >= 5
    assert approval["validation"]["ready_for_approval"] is True
    assert approval["client_delivery_allowed"] is False


def test_approval_requires_every_current_exception_and_substantive_review_note():
    run_id = _run_id()
    _create_run(run_id)
    requested = _request(run_id)["approval"]

    missing = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Reviewer",
        note="Reviewed all available technical evidence.",
        reviewed_item_ids=requested["exception_item_ids"][:-1],
        admin_token="test-admin-token",
    )
    short_note = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Reviewer",
        note="short",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )

    assert missing["status"] == "blocked"
    assert missing["missing_reviewed_item_ids"]
    assert short_note["status"] == "blocked"
    assert "substantive" in short_note["error"]


def test_approval_creates_separate_integrity_bound_pdf_and_preserves_draft():
    run_id = _run_id()
    _create_run(run_id)
    requested = _request(run_id)["approval"]
    draft_before = deepcopy(STORE.get("reports", requested["draft_report_id"]))

    result = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Senior Technical Reviewer",
        note="Reviewed every exception, limitation, and unavailable evidence source; approval is evidence-bound.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )
    approval = result["approval"]
    approved = get_mid_approved_report(run_id, "customer_approval", "project_approval", admin_token="test-admin-token")
    approved_pdf = base64.b64decode(approved["formats"]["pdf"], validate=True)
    draft_after = STORE.get("reports", requested["draft_report_id"])

    assert result["status"] == "approved"
    assert approval["approved"] is True
    assert approval["approved_report"]["report_id"].startswith("mid_approved_report_")
    assert approved["record_type"] == "mid_approved_report"
    assert approved["report_id"] != requested["draft_report_id"]
    assert approved["source_draft_report_id"] == requested["draft_report_id"]
    assert approved["source_draft_pdf_sha256"] == requested["draft_pdf_sha256"]
    assert approved["review_packet_sha256"] == requested["review_packet_sha256"]
    assert approved_pdf.startswith(b"%PDF")
    assert hashlib.sha256(approved_pdf).hexdigest() == approved["pdf_sha256"]
    assert approved["approved"] is True
    assert approved["delivery_eligible"] is True
    assert approved["client_delivery_allowed"] is False
    assert draft_after["pdf_sha256"] == draft_before["pdf_sha256"]
    assert draft_after["formats"]["pdf"] == draft_before["formats"]["pdf"]
    assert draft_after["draft_status"] == "human_review_required"


def test_terminal_decision_is_idempotent_and_cannot_be_reversed():
    run_id = _run_id()
    _create_run(run_id)
    requested = _request(run_id)["approval"]
    args = dict(
        approval_id=requested["approval_id"],
        state="approved",
        actor="Reviewer",
        note="Reviewed all exception items and approved the exact snapshot-bound artifact.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )
    first = transition_mid_approval(**args)
    same = transition_mid_approval(**args)
    reverse = transition_mid_approval(
        requested["approval_id"], "rejected", actor="Reviewer", note="Attempted reversal.", admin_token="test-admin-token"
    )

    assert first["status"] == "approved"
    assert same["status"] == "approved"
    assert same["idempotent_reuse"] is True
    assert reverse["status"] == "blocked"
    assert "cannot be reversed" in reverse["error"]


def test_optional_evidence_change_after_request_invalidates_approval():
    run_id = _run_id()
    result = _create_run(run_id)
    requested = _request(run_id)["approval"]
    token = result["optional_evidence_submission"]["token"]
    submitted = submit_mid_optional_evidence(
        run_id,
        {"token": token, "application_url": "https://staging.example.com"},
    )
    stored = STORE.get("approvals", requested["approval_id"])
    validation = validate_mid_approval(stored)
    decision = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Reviewer",
        note="Attempting approval after external evidence changed.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )

    assert submitted["status"] == "submitted"
    assert validation["ready_for_approval"] is False
    assert any(check["id"] == "truth_model" and not check["passed"] for check in validation["checks"])
    assert decision["status"] == "blocked"
    assert "exact-state validation" in decision["error"]


def test_draft_pdf_tamper_invalidates_approval():
    run_id = _run_id()
    _create_run(run_id)
    requested = _request(run_id)["approval"]
    report = STORE.get("reports", requested["draft_report_id"])
    report["formats"]["pdf"] = base64.b64encode(b"%PDF-tampered").decode("ascii")
    STORE.put("reports", requested["draft_report_id"], report)

    validation = validate_mid_approval(STORE.get("approvals", requested["approval_id"]))

    assert validation["ready_for_approval"] is False
    assert any(check["id"] == "draft_pdf" and not check["passed"] for check in validation["checks"])


def test_needs_more_evidence_can_return_to_approval_but_rejection_is_terminal():
    run_id = _run_id()
    _create_run(run_id)
    requested = _request(run_id)["approval"]
    needs = transition_mid_approval(
        requested["approval_id"], "needs_more_evidence", actor="Reviewer", note="Need direct QA evidence.", admin_token="test-admin-token"
    )
    approved = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Reviewer",
        note="Reviewed all current exceptions after requesting additional evidence.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )

    assert needs["status"] == "needs_more_evidence"
    assert approved["status"] == "approved"


def test_api_returns_metadata_and_hash_bound_no_store_approved_pdf():
    run_id = _run_id()
    _create_run(run_id)
    requested_response = mid_approval_request_response(
        run_id,
        MidApprovalRequest(customer_id="customer_approval", project_id="project_approval"),
        x_nico_admin_token="test-admin-token",
    )
    requested = requested_response["approval"]
    accepted_item_ids = []
    for item_id in requested["exception_item_ids"]:
        disposition = mid_review_disposition_response(
            requested["approval_id"],
            item_id,
            MidReviewDispositionRequest(
                decision="accepted",
                actor="Reviewer",
                note=f"Reviewed the exact evidence and limitation for {item_id}; accepted as represented.",
            ),
            x_nico_admin_token="test-admin-token",
        )
        assert disposition["status"] == "recorded"
        accepted_item_ids = disposition["review_dispositions"]["accepted_item_ids"]
    decided = mid_approval_decision_response(
        requested["approval_id"],
        "approved",
        MidApprovalDecisionRequest(
            actor="Reviewer",
            note="Reviewed every current exception and approved the exact artifact.",
            reviewed_item_ids=accepted_item_ids,
        ),
        x_nico_admin_token="test-admin-token",
    )
    response = mid_approved_report_pdf_response(
        run_id,
        customer_id="customer_approval",
        project_id="project_approval",
        x_nico_admin_token="test-admin-token",
    )

    assert decided["status"] == "approved"
    assert decided["approval"]["review_disposition_set_sha256"]
    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert response.headers["x-nico-approval-id"] == requested["approval_id"]
    assert response.headers["x-nico-report-path"] == "mid_run"
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert hashlib.sha256(response.body).hexdigest() == response.headers["x-nico-pdf-sha256"]


def test_api_uses_generic_auth_and_scope_errors():
    run_id = _run_id()
    _create_run(run_id)

    with pytest.raises(HTTPException) as unauthorized:
        mid_approval_request_response(
            run_id,
            MidApprovalRequest(customer_id="customer_approval", project_id="project_approval"),
            x_nico_admin_token="wrong",
        )
    with pytest.raises(HTTPException) as missing:
        mid_approval_request_response(
            run_id,
            MidApprovalRequest(customer_id="wrong", project_id="project_approval"),
            x_nico_admin_token="test-admin-token",
        )

    assert unauthorized.value.status_code == 403
    assert missing.value.status_code == 404
    assert missing.value.detail["message"] == "Mid approval request was unavailable."
