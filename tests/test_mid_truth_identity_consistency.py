from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest

from nico.mid_assessment_approval import request_mid_approval, validate_mid_approval
from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import persist_mid_assessment_run
from nico.mid_truth_identity_consistency import (
    MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
    canonicalize_mid_truth,
    repair_stale_mid_approval,
)
from nico.storage import STORE


TECHNICAL_IDS = (
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
)


def _run_id(prefix: str = "midrun_truth_identity") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _section(section_id: str, score: int = 82) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green",
        "summary": f"Exact-run evidence supports a bounded conclusion for {section_id}.",
        "evidence": [f"Retained exact-run evidence for {section_id}."],
        "findings": [],
        "unavailable": [],
        "human_review_required": False,
    }


def _create_complete_run(run_id: str) -> dict:
    result = {
        "status": "complete",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_truth_identity",
        "project_id": "project_truth_identity",
        "generated_at": "2099-01-01T00:00:00Z",
        "repository_snapshot": {
            "status": "attached",
            "snapshot_id": f"snapshot_{run_id}",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "repository_evidence": {
            "status": "attached",
            "snapshot_commit_sha": "a" * 40,
            "file_evidence": {"files_profiled": 30},
            "dependency_evidence": {"manifest_paths": ["requirements.txt", "apps/web/package-lock.json"], "dependency_entries": 20},
            "workflow_evidence": {
                "workflow_file_count": 8,
                "workflow_configuration_snapshot_sha": "a" * 40,
                "jobs_observed": 20,
                "deployments_observed": 2,
            },
            "activity_evidence": {"commits_returned": 25, "pull_requests_returned": 10},
        },
        "complexity_evidence": {
            "status": "attached",
            "files_analyzed": 25,
            "snapshot_commit_sha": "a" * 40,
        },
        "scanner": {"status": "complete", "scan_id": f"scan_{run_id}"},
        "scanner_evidence": {
            "status": "attached",
            "scanner_status": "complete",
            "scan_id": f"scan_{run_id}",
            "snapshot_match": True,
            "tools_requested": ["pip-audit", "osv-scanner", "gitleaks", "trufflehog", "bandit", "semgrep"],
            "tools_run": ["pip-audit", "osv-scanner", "gitleaks", "trufflehog", "bandit", "semgrep"],
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
        },
        "assessment": {
            "status": "draft",
            "sections": [_section(section_id, 78 + index) for index, section_id in enumerate(TECHNICAL_IDS)],
            "maturity_signal": {
                "level": "Senior",
                "score": 81,
                "summary": "Seven technical sections were scored from retained evidence.",
                "evidence_readiness_score": 100,
            },
            "evidence_ledger": {
                "status": "available",
                "entry_count": 20,
                "verified_entry_count": 20,
                "unavailable_entry_count": 0,
            },
        },
        "progress": [
            {"step": "scanner_reconciliation", "status": "complete", "message": "Scanner reconciled.", "evidence": {"scanner_status": "complete"}},
            {"step": "evidence_attachment", "status": "complete", "message": "Evidence attached.", "evidence": {}},
            {"step": "scoring", "status": "complete", "message": "Scoring complete.", "evidence": {}},
            {"step": "reports", "status": "planned", "message": "Mid draft planned.", "evidence": {}},
            {"step": "approval_request", "status": "planned", "message": "Mid review planned.", "evidence": {}},
        ],
        "human_review_required": True,
        "client_ready": False,
    }
    persist_mid_assessment_run(
        result,
        {
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_truth_identity",
            "project_id": "project_truth_identity",
            "client_name": "Truth Identity Test",
            "project_name": "NICO",
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
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "truth-identity-admin-token")


def test_approval_canonicalizes_stale_stored_truth_before_report_packet_and_request() -> None:
    run_id = _run_id()
    _create_complete_run(run_id)
    record = STORE.get("assessment_runs", run_id)
    stale_truth = deepcopy(record["response"]["mid_truth_status"])
    stale_truth["summary"]["scope_disclosures"] = 999
    stale_truth["rule"] = "Legacy serialized truth representation."
    stale_hash = canonicalize_mid_truth(run_id, persist=False)["truth_sha256"]
    record["response"]["mid_truth_status"] = stale_truth
    STORE.put("assessment_runs", run_id, record)

    requested = request_mid_approval(
        run_id,
        "customer_truth_identity",
        "project_truth_identity",
        admin_token="truth-identity-admin-token",
    )
    approval = requested["approval"]
    report = STORE.get("reports", approval["draft_report_id"])
    canonical = canonicalize_mid_truth(run_id, persist=False)

    assert requested["status"] == "requested"
    assert approval["status"] == "pending"
    assert report["source_identity"]["truth_sha256"] == approval["truth_sha256"]
    assert approval["truth_sha256"] == canonical["truth_sha256"]
    assert approval["truth_sha256"] == stale_hash
    assert approval["validation"]["ready_for_approval"] is True
    assert approval["client_delivery_allowed"] is False


def test_stale_approval_terminal_state_repairs_same_run_without_rescan_or_replacement() -> None:
    run_id = _run_id("midrun_same_run_repair")
    _create_complete_run(run_id)
    report = generate_mid_draft_report(
        run_id,
        "customer_truth_identity",
        "project_truth_identity",
        admin_token="truth-identity-admin-token",
    )
    assert report["status"] == "complete"

    record = STORE.get("assessment_runs", run_id)
    response = deepcopy(record["response"])
    response.update(
        {
            "status": "blocked",
            "report_generation_status": "complete",
            "mid_report": {
                "status": "complete",
                "report_id": report["report_id"],
                "report_path": report["report_path"],
                "report_version": report["report_version"],
                "pdf_sha256": report["pdf_sha256"],
                "pdf_filename": report["pdf_filename"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "approval_request": {},
            "approval_request_status": "blocked",
            "approval_request_error": "The Mid draft is stale relative to the current truth model.",
            "current_stage": "approval_request",
            "progress_percent": 100,
        }
    )
    for item in response["progress"]:
        if item["step"] == "reports":
            item.update({"status": "complete", "message": "Dedicated Mid draft report generated."})
        if item["step"] == "approval_request":
            item.update({"status": "blocked", "message": "The Mid draft is stale relative to the current truth model."})
    record["status"] = "blocked"
    record["report_id"] = report["report_id"]
    record["response"] = response
    STORE.put("assessment_runs", run_id, record)

    repaired = repair_stale_mid_approval(record, store=STORE)
    retained = STORE.get("assessment_runs", run_id)
    approval = STORE.get("approvals", retained["approval_id"])
    validation = validate_mid_approval(approval)
    matching_runs = [item for item in STORE.list("assessment_runs") if item.get("run_id") == run_id]

    assert repaired is not None
    assert repaired["run_id"] == run_id
    assert repaired["status"] == "complete"
    assert repaired["report_generation_status"] == "complete"
    assert repaired["approval_request_status"] == "pending"
    assert repaired["approval_request"]["approval_id"] == retained["approval_id"]
    assert repaired["same_run_approval_repair"]["version"] == MID_TRUTH_IDENTITY_CONSISTENCY_VERSION
    assert repaired["same_run_approval_repair"]["repository_recaptured"] is False
    assert repaired["same_run_approval_repair"]["scanner_rerun"] is False
    assert repaired["same_run_approval_repair"]["score_recomputed"] is False
    assert repaired["same_run_approval_repair"]["replacement_run_created"] is False
    assert repaired["same_run_approval_repair"]["duplicate_start_allowed"] is False
    assert retained["status"] == "complete"
    assert retained["run_id"] == run_id
    assert validation["ready_for_approval"] is True
    assert len(matching_runs) == 1


def test_report_quality_block_is_not_reclassified_as_repairable_approval_staleness() -> None:
    run_id = _run_id("midrun_nonrepairable")
    _create_complete_run(run_id)
    record = STORE.get("assessment_runs", run_id)
    response = deepcopy(record["response"])
    response.update(
        {
            "status": "blocked",
            "report_generation_status": "blocked",
            "approval_request_status": "blocked",
            "approval_request_error": "The Mid draft is stale relative to the current truth model.",
        }
    )
    record["status"] = "blocked"
    record["response"] = response
    STORE.put("assessment_runs", run_id, record)

    assert repair_stale_mid_approval(record, store=STORE) is None
    assert STORE.get("assessment_runs", run_id)["status"] == "blocked"
