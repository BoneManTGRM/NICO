from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest

import nico.mid_delivery_access as delivery_store
from nico.mid_assessment_approval import get_mid_approved_report, request_mid_approval, transition_mid_approval
from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import load_mid_assessment_run, persist_mid_assessment_run
from nico.mid_delivery_access import (
    create_mid_delivery_access,
    inspect_mid_delivery_access,
    list_mid_delivery_receipts,
    redeem_mid_delivery_access,
)
from nico.mid_review_by_exception import build_mid_review_packet
from nico.mid_truth_status import ALLOWED_SECTION_STATUSES
from nico.storage import STORE

CUSTOMER_ID = "customer_mid_e2e"
PROJECT_ID = "project_mid_e2e"
REPOSITORY = "BoneManTGRM/NICO"
SNAPSHOT_SHA = "a" * 40
ACKNOWLEDGEMENT = "I acknowledge receipt of this NICO Mid Assessment and the disclosed evidence limitations."


def _run_id() -> str:
    return f"midrun_e2e_{uuid4().hex[:12]}"


def _technical_section(section_id: str, *, score: int = 90, finding: str = "") -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green",
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": [f"Snapshot-bound evidence for {section_id} at {SNAPSHOT_SHA}."],
        "findings": [finding] if finding else [],
        "unavailable": [],
    }


def _persist_single_mid_run(run_id: str) -> dict:
    result = {
        "status": "complete",
        "run_id": run_id,
        "repository": REPOSITORY,
        "customer_id": CUSTOMER_ID,
        "project_id": PROJECT_ID,
        "generated_at": "2026-07-11T23:00:00Z",
        "assessment_type": "mid",
        "service_tier": "mid",
        "mode": "mid",
        "unified_run": True,
        "express_report_generated": False,
        "full_report_generated": False,
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
            "snapshot_commit_sha": SNAPSHOT_SHA,
        },
        "scanner_evidence": {
            "status": "attached",
            "scan_id": f"scan_{run_id}",
            "snapshot_match": True,
            "tools_run": ["pip-audit", "gitleaks"],
            "failed_tools": ["semgrep"],
            "timed_out_tools": [],
            "unavailable_tools": ["bandit"],
        },
        "assessment": {
            "status": "draft",
            "assessment_type": "mid",
            "service_tier": "mid",
            "sections": [
                _technical_section("code_audit"),
                _technical_section("dependency_health"),
                _technical_section("secrets_review"),
                _technical_section("static_analysis"),
                _technical_section("ci_cd"),
                _technical_section("architecture_debt"),
                _technical_section("velocity_complexity", finding="Velocity conclusion changes the section score and requires review."),
            ],
            "evidence_ledger": {
                "status": "available",
                "ledger_id": f"ledger_{run_id}",
                "run_id": run_id,
                "snapshot_commit_sha": SNAPSHOT_SHA,
                "entry_count": 22,
                "verified_entry_count": 19,
                "unavailable_entry_count": 3,
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
            "client_name": "Unified Mid Client",
            "project_name": "Unified Mid Project",
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


def test_one_mid_run_remains_identity_bound_from_snapshot_through_acknowledged_delivery():
    run_id = _run_id()
    source_result = _persist_single_mid_run(run_id)
    run = load_mid_assessment_run(run_id)

    assert run is not None
    assert run["run_id"] == run_id
    assert run["workflow"] == "mid_assessment"
    assert run["service_tier"] == "mid"
    assert run["repository"] == REPOSITORY
    assert run["snapshot_id"] == f"snapshot_{run_id}"
    assert run["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert run["request"]["build_reports"] is False
    assert run["request"]["create_final_review_request"] is False
    assert run["response"]["unified_run"] is True
    assert run["response"]["express_report_generated"] is False
    assert run["response"]["full_report_generated"] is False

    ledger = run["response"]["assessment"]["evidence_ledger"]
    assert ledger["ledger_id"] == f"ledger_{run_id}"
    assert ledger["run_id"] == run_id
    assert ledger["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert run["response"].get("evidence_ledger_count", 1) == 1

    truth = run["response"]["mid_truth_status"]
    statuses = {section["truth_status"] for section in truth["sections"]}
    assert statuses <= ALLOWED_SECTION_STATUSES
    assert "Failed" in statuses
    assert "Unavailable" in statuses
    assert truth["summary"]["unsupported_claims_permitted"] == 0
    assert truth["unsupported_claims_permitted"] == 0
    assert truth["evidence_coverage"]["calculated"] is True
    assert truth["evidence_coverage"]["denominator"] == 12
    assert truth["evidence_coverage"]["percent"] < 100

    static_section = next(item for item in truth["sections"] if item["id"] == "static_analysis")
    assert static_section["truth_status"] == "Failed"
    assert "semgrep" in static_section["failed_evidence_tools"]
    assert "static_scanners" in static_section["missing_evidence_sources"]
    functional_qa = next(item for item in truth["sections"] if item["id"] == "functional_qa")
    assert functional_qa["truth_status"] == "Unavailable"
    assert functional_qa["score"] is None
    assert functional_qa["direct_repository_proof"] is False

    packet = build_mid_review_packet(
        run_id,
        customer_id=CUSTOMER_ID,
        project_id=PROJECT_ID,
        admin_token="test-admin-token",
    )
    assert packet["status"] == "ready_for_review"
    assert packet["run_id"] == run_id
    assert packet["snapshot_id"] == f"snapshot_{run_id}"
    assert packet["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert packet["summary"]["unsupported_claims_permitted"] == 0
    assert packet["summary"]["items_requiring_review"] > 0
    assert packet["exceptions"]
    assert all(item["requires_human_review"] is True for item in packet["exceptions"])
    assert all(item["collapsed_by_default"] is True for item in packet["verified_sections"])
    assert {item["section_id"] for item in packet["verified_sections"]}.isdisjoint(
        {item["section_id"] for item in packet["exceptions"]}
    )

    draft = generate_mid_draft_report(
        run_id,
        customer_id=CUSTOMER_ID,
        project_id=PROJECT_ID,
        admin_token="test-admin-token",
    )
    draft_pdf = base64.b64decode(draft["formats"]["pdf"], validate=True)
    assert draft["record_type"] == "mid_assessment_report"
    assert draft["run_id"] == run_id
    assert draft["snapshot_id"] == f"snapshot_{run_id}"
    assert draft["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert draft["review_packet_id"] == packet["review_packet_id"]
    assert draft["review_packet_sha256"] == packet["review_packet_sha256"]
    assert draft["client_delivery_allowed"] is False
    assert draft["approved"] is False
    assert draft_pdf.startswith(b"%PDF")
    assert hashlib.sha256(draft_pdf).hexdigest() == draft["pdf_sha256"]

    requested = request_mid_approval(
        run_id,
        customer_id=CUSTOMER_ID,
        project_id=PROJECT_ID,
        admin_token="test-admin-token",
    )["approval"]
    assert requested["run_id"] == run_id
    assert requested["snapshot_id"] == f"snapshot_{run_id}"
    assert requested["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert requested["draft_report_id"] == draft["report_id"]
    assert requested["draft_pdf_sha256"] == draft["pdf_sha256"]
    assert requested["review_packet_id"] == packet["review_packet_id"]
    assert requested["review_packet_sha256"] == packet["review_packet_sha256"]
    assert requested["exception_item_ids"]
    assert requested["validation"]["ready_for_approval"] is True

    incomplete = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Senior Technical Reviewer",
        note="Reviewed the available evidence and limitations but omitted one exception acknowledgement.",
        reviewed_item_ids=requested["exception_item_ids"][:-1],
        admin_token="test-admin-token",
    )
    assert incomplete["status"] == "blocked"
    assert incomplete["missing_reviewed_item_ids"]

    draft_before = deepcopy(STORE.get("reports", draft["report_id"]))
    decision = transition_mid_approval(
        requested["approval_id"],
        "approved",
        actor="Senior Technical Reviewer",
        note="Reviewed every current exception, failed tool, unavailable source, and score-changing conclusion for this exact snapshot.",
        reviewed_item_ids=requested["exception_item_ids"],
        admin_token="test-admin-token",
    )
    assert decision["status"] == "approved"
    approved = get_mid_approved_report(
        run_id,
        customer_id=CUSTOMER_ID,
        project_id=PROJECT_ID,
        admin_token="test-admin-token",
    )
    approved_pdf = base64.b64decode(approved["formats"]["pdf"], validate=True)
    draft_after = STORE.get("reports", draft["report_id"])

    assert approved["record_type"] == "mid_approved_report"
    assert approved["report_id"] != draft["report_id"]
    assert approved["run_id"] == run_id
    assert approved["snapshot_id"] == f"snapshot_{run_id}"
    assert approved["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert approved["source_draft_report_id"] == draft["report_id"]
    assert approved["source_draft_pdf_sha256"] == draft["pdf_sha256"]
    assert approved["review_packet_id"] == packet["review_packet_id"]
    assert approved["review_packet_sha256"] == packet["review_packet_sha256"]
    assert approved["approval_id"] == requested["approval_id"]
    assert approved["delivery_eligible"] is True
    assert approved["client_delivery_allowed"] is False
    assert approved["unsupported_claims_permitted"] == 0
    assert approved_pdf.startswith(b"%PDF")
    assert hashlib.sha256(approved_pdf).hexdigest() == approved["pdf_sha256"]
    assert draft_after["formats"]["pdf"] == draft_before["formats"]["pdf"]
    assert draft_after["pdf_sha256"] == draft_before["pdf_sha256"]
    assert draft_after["draft_status"] == "human_review_required"

    created = create_mid_delivery_access(
        {
            "run_id": run_id,
            "customer_id": CUSTOMER_ID,
            "project_id": PROJECT_ID,
            "recipient_label": "Unified Mid Client",
            "created_by": "Senior Technical Reviewer",
            "expires_in_hours": 24,
            "max_downloads": 1,
        },
        admin_token="test-admin-token",
    )
    token = created["token"]
    access_id = created["access"]["access_id"]
    assert created["status"] == "created"
    assert created["fragment_path"].startswith("/mid-delivery#token=")
    assert token.startswith(f"{access_id}.")
    assert token not in repr(delivery_store._MEMORY_ACCESS[access_id])
    assert delivery_store._MEMORY_ACCESS[access_id]["token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()

    inspected = inspect_mid_delivery_access(token)
    assert inspected["status"] == "available"
    assert inspected["delivery"]["report_id"] == approved["report_id"]
    assert inspected["delivery"]["pdf_sha256"] == approved["pdf_sha256"]
    assert inspected["delivery"]["approval_id"] == requested["approval_id"]
    assert inspected["delivery"]["approval_identity_sha256"] == approved["approval_identity_sha256"]
    assert inspected["delivery"]["review_packet_sha256"] == packet["review_packet_sha256"]
    assert inspected["delivery"]["snapshot_commit_sha"] == SNAPSHOT_SHA
    assert "pdf" not in inspected
    assert token not in repr(inspected)

    downloaded = redeem_mid_delivery_access(
        token,
        recipient_name="Client Recipient",
        acknowledged=True,
        acknowledgement_text=ACKNOWLEDGEMENT,
    )
    receipts = list_mid_delivery_receipts(
        run_id,
        customer_id=CUSTOMER_ID,
        project_id=PROJECT_ID,
        admin_token="test-admin-token",
    )
    assert downloaded["status"] == "downloaded"
    assert downloaded["pdf"] == approved_pdf
    assert downloaded["report_id"] == approved["report_id"]
    assert downloaded["approval_id"] == requested["approval_id"]
    assert downloaded["review_packet_sha256"] == packet["review_packet_sha256"]
    assert downloaded["receipt"]["run_id"] == run_id
    assert downloaded["receipt"]["report_id"] == approved["report_id"]
    assert downloaded["receipt"]["approval_id"] == requested["approval_id"]
    assert downloaded["receipt"]["pdf_sha256"] == approved["pdf_sha256"]
    assert downloaded["receipt"]["review_packet_sha256"] == packet["review_packet_sha256"]
    assert downloaded["receipt"]["recipient_name"] == "Client Recipient"
    assert downloaded["receipt"]["acknowledgement_sha256"] == hashlib.sha256(ACKNOWLEDGEMENT.encode("utf-8")).hexdigest()
    assert downloaded["receipt"]["download_ordinal"] == 1
    assert len(downloaded["receipt"]["receipt_sha256"]) == 64
    assert downloaded["access"]["downloads_remaining"] == 0
    assert receipts["status"] == "ok"
    assert len(receipts["receipts"]) == 1
    assert receipts["receipts"][0]["receipt_id"] == downloaded["receipt"]["receipt_id"]
    assert inspect_mid_delivery_access(token)["status"] == "not_found"

    run_reports = [item for item in STORE.list("reports") if item.get("run_id") == run_id]
    assert {item.get("record_type") for item in run_reports} == {"mid_assessment_report", "mid_approved_report"}
    assert all(item.get("report_type") == "mid_assessment" for item in run_reports)
    assert all(item.get("report_path") == "mid_run" for item in run_reports)
    assert not any("express" in str(item.get("record_type") or "").lower() for item in run_reports)
    assert not any("full_assessment" in str(item.get("record_type") or "").lower() for item in run_reports)

    audits = STORE.list("audit_log")
    lifecycle_actions = {
        "mid.review_packet_generated",
        "mid.draft_report_generated",
        "mid.approval_requested",
        "mid.approval_decided",
        "mid.delivery_access_created",
        "mid.delivery_downloaded",
    }
    recorded_actions = {item.get("action") for item in audits if item.get("payload", {}).get("run_id") == run_id}
    assert lifecycle_actions <= recorded_actions
    assert token not in repr(audits)
    assert source_result["optional_evidence_submission"]["token"] not in repr(run)
