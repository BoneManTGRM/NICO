from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

import nico.mid_approval_api as approval_api
import nico.mid_assessment_approval as approval_service
import nico.mid_delivery_access as delivery_service
from nico.api import production as production_api
from nico.mid_assessment_runs import persist_mid_assessment_run
from nico.mid_review_dispositions import submit_mid_review_disposition
from nico.mid_review_enforcement import MID_APPROVAL_ENFORCED_VERSION, MID_REVIEW_ENFORCEMENT_VERSION
from nico.storage import STORE


CUSTOMER_ID = "customer_enforced_review"
PROJECT_ID = "project_enforced_review"
REPOSITORY = "BoneManTGRM/NICO"
SNAPSHOT_SHA = "a" * 40
ACKNOWLEDGEMENT = "I acknowledge receipt of this NICO Mid Assessment and all disclosed evidence limitations."


def _run_id(prefix: str = "enforced") -> str:
    return f"midrun_{prefix}_{uuid4().hex[:12]}"


def _section(section_id: str, score: int = 90) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green",
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": [f"Direct exact-snapshot evidence for {section_id}."],
        "findings": [],
        "unavailable": [],
    }


def _create_run(run_id: str) -> dict:
    result = {
        "status": "complete",
        "run_id": run_id,
        "repository": REPOSITORY,
        "customer_id": CUSTOMER_ID,
        "project_id": PROJECT_ID,
        "generated_at": "2026-07-12T16:15:00Z",
        "assessment_type": "mid",
        "service_tier": "mid",
        "mode": "mid",
        "unified_run": True,
        "repository_snapshot": {
            "status": "attached",
            "snapshot_id": f"snapshot_{run_id}",
            "commit_sha": SNAPSHOT_SHA,
            "tree_sha": "b" * 40,
        },
        "repository_evidence": {
            "status": "attached",
            "snapshot_commit_sha": SNAPSHOT_SHA,
            "file_evidence": {"files_profiled": 31},
            "dependency_evidence": {
                "manifest_paths": ["requirements.txt", "apps/web/package.json"],
                "dependency_entries": 42,
            },
            "workflow_evidence": {
                "workflow_file_count": 5,
                "workflow_configuration_snapshot_sha": SNAPSHOT_SHA,
                "jobs_observed": 12,
                "deployments_observed": 2,
            },
            "activity_evidence": {"commits_returned": 40, "pull_requests_returned": 18},
        },
        "complexity_evidence": {
            "status": "attached",
            "files_analyzed": 27,
            "lines_of_code": 4801,
            "function_like_units": 211,
            "snapshot_commit_sha": SNAPSHOT_SHA,
        },
        "scanner_evidence": {
            "status": "attached",
            "scan_id": f"scan_{run_id}",
            "snapshot_match": True,
            "tools_run": ["osv-scanner", "pip-audit", "npm-audit", "gitleaks", "trufflehog", "bandit", "semgrep"],
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
        },
        "assessment": {
            "status": "draft",
            "assessment_type": "mid",
            "service_tier": "mid",
            "sections": [
                _section("code_audit"),
                _section("dependency_health"),
                _section("secrets_review"),
                _section("static_analysis"),
                _section("ci_cd"),
                _section("architecture_debt"),
                _section("velocity_complexity"),
            ],
            "evidence_ledger": {
                "status": "available",
                "ledger_id": f"ledger_{run_id}",
                "run_id": run_id,
                "snapshot_commit_sha": SNAPSHOT_SHA,
                "entry_count": 22,
                "verified_entry_count": 22,
                "unavailable_entry_count": 0,
            },
        },
        "reports": {"pdf_base64": ""},
    }
    persist_mid_assessment_run(
        result,
        {
            "run_id": run_id,
            "repository": REPOSITORY,
            "customer_id": CUSTOMER_ID,
            "project_id": PROJECT_ID,
            "client_name": "Enforced Review Client",
            "project_name": "Enforced Review Project",
            "authorized_by": "repository_owner",
            "authorization_scope": "repository assessment only",
            "authorized": True,
            "authorization_confirmed": True,
            "mode": "mid",
            "run_scanners": True,
            "build_reports": False,
            "create_final_review_request": False,
        },
    )
    return result


@pytest.fixture(autouse=True)
def secure_test_environment(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("NICO_DISABLE_POSTGRES", "true")


def _production_request(run_id: str) -> dict:
    return approval_api.request_mid_approval(
        run_id,
        CUSTOMER_ID,
        PROJECT_ID,
        admin_token="test-admin-token",
    )


def _record_all_dispositions(approval: dict) -> dict:
    latest = {}
    for item_id in approval["exception_item_ids"]:
        latest = submit_mid_review_disposition(
            approval["approval_id"],
            item_id,
            decision="accepted",
            actor="Senior Technical Reviewer",
            note=f"Reviewed the exact evidence and limitation for {item_id}; accepted as represented.",
            admin_token="test-admin-token",
        )
        assert latest["status"] == "recorded"
    return latest


def test_production_api_creates_v3_approval_and_blocks_checkbox_only_bypass():
    run_id = _run_id()
    _create_run(run_id)

    requested = _production_request(run_id)["approval"]
    bypass = approval_api.transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Reviewer",
        note="Attempted to approve by acknowledging IDs without item-level decisions.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )

    assert requested["approval_version"] == MID_APPROVAL_ENFORCED_VERSION
    assert requested["review_disposition_required"] is True
    assert requested["review_disposition_policy_version"] == MID_REVIEW_ENFORCEMENT_VERSION
    assert requested["validation"]["ready_for_approval"] is False
    assert requested["review_dispositions"]["pending_item_count"] == requested["exception_item_count"]
    assert bypass["status"] == "blocked"
    assert "item-level disposition" in bypass["error"]


def test_complete_disposition_set_is_bound_to_approval_pdf_json_grant_and_receipt():
    run_id = _run_id()
    _create_run(run_id)
    requested = _production_request(run_id)["approval"]
    completed = _record_all_dispositions(requested)["review_dispositions"]

    decision = approval_api.transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Senior Technical Reviewer",
        note="Reviewed every current exception and approved the exact disposition-bound artifact.",
        reviewed_item_ids=completed["accepted_item_ids"],
        admin_token="test-admin-token",
    )
    approval = decision["approval"]
    report = STORE.get("reports", approval["approved_report"]["report_id"])
    report_json = report["formats"]["json"]
    report_pdf = base64.b64decode(report["formats"]["pdf"], validate=True)
    disposition_hash = completed["disposition_set_sha256"]

    assert decision["status"] == "approved"
    assert approval["review_disposition_set_sha256"] == disposition_hash
    assert approval["review_decision"]["review_disposition_set_sha256"] == disposition_hash
    assert approval["approved_report"]["review_disposition_set_sha256"] == disposition_hash
    assert approval["validation"]["ready_for_approval"] is True
    assert report["review_disposition_set_sha256"] == disposition_hash
    assert report_json["review_disposition_set_sha256"] == disposition_hash
    assert len(report_json["review_dispositions"]) == requested["exception_item_count"]
    assert all(item["decision"] == "accepted" for item in report_json["review_dispositions"])
    assert report_pdf.startswith(b"%PDF")
    assert hashlib.sha256(report_pdf).hexdigest() == report["pdf_sha256"]

    created = delivery_service.create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": CUSTOMER_ID,
            "project_id": PROJECT_ID,
            "recipient_label": "Enforced Review Client",
            "created_by": "Senior Technical Reviewer",
            "expires_in_hours": 24,
            "max_downloads": 1,
        },
        admin_token="test-admin-token",
    )
    inspected = delivery_service.inspect_mid_delivery_access(created["token"])
    redeemed = delivery_service.redeem_mid_delivery_access(
        created["token"],
        recipient_name="Client Reviewer",
        acknowledged=True,
        acknowledgement_text=ACKNOWLEDGEMENT,
    )

    assert created["status"] == "created"
    assert created["access"]["review_disposition_set_sha256"] == disposition_hash
    assert inspected["delivery"]["review_disposition_set_sha256"] == disposition_hash
    assert redeemed["status"] == "downloaded"
    assert redeemed["review_disposition_set_sha256"] == disposition_hash
    assert redeemed["receipt"]["review_disposition_set_sha256"] == disposition_hash
    assert redeemed["receipt"]["approval_record_identity_sha256"] == approval["approval_identity_sha256"]
    stored_receipt = delivery_service._MEMORY_RECEIPTS[redeemed["receipt"]["receipt_id"]]
    core = {key: value for key, value in stored_receipt.items() if key != "receipt_sha256"}
    assert stored_receipt["receipt_sha256"] == hashlib.sha256(
        __import__("json").dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


def test_tampered_item_decision_invalidates_approval_and_future_delivery_grants():
    run_id = _run_id()
    _create_run(run_id)
    requested = _production_request(run_id)["approval"]
    completed = _record_all_dispositions(requested)["review_dispositions"]
    decision = approval_api.transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Senior Technical Reviewer",
        note="Approved after reviewing every exact item-level disposition.",
        reviewed_item_ids=completed["accepted_item_ids"],
        admin_token="test-admin-token",
    )
    assert decision["status"] == "approved"

    stored = STORE.get("approvals", requested["approval_id"])
    tampered = deepcopy(stored)
    first_id = requested["exception_item_ids"][0]
    tampered["review_item_dispositions"][first_id]["note"] = "Tampered after approval."
    STORE.put("approvals", requested["approval_id"], tampered)

    validation = approval_service.validate_mid_approval(tampered)
    grant = delivery_service.create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": CUSTOMER_ID,
            "project_id": PROJECT_ID,
            "recipient_label": "Client",
            "created_by": "Reviewer",
        },
        admin_token="test-admin-token",
    )

    assert validation["ready_for_approval"] is False
    assert validation["review_dispositions"]["stale_item_count"] >= 1
    assert grant["status"] == "blocked"
    assert "review-disposition integrity" in grant["error"]


def test_legacy_v2_service_approval_remains_supported_without_v3_dispositions():
    run_id = _run_id("legacy")
    _create_run(run_id)

    requested = approval_service.request_mid_approval(
        run_id,
        CUSTOMER_ID,
        PROJECT_ID,
        admin_token="test-admin-token",
    )["approval"]
    decision = approval_service.transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Legacy Reviewer",
        note="Approved through the retained version-two compatibility path.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )

    assert production_api.ASSESSMENT_MID_REVIEW_ENFORCEMENT["compatibility_installed"] is True
    assert requested["approval_version"] == "mid-report-approval-v2"
    assert requested.get("review_disposition_required") is not True
    assert decision["status"] == "approved"
    assert decision["approval"]["approved"] is True
