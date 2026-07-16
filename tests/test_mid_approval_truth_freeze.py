from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest

from nico import mid_terminal_truth_patch
from nico.mid_assessment_approval import request_mid_approval
from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import persist_mid_assessment_run
from nico.mid_approval_truth_freeze import MID_APPROVAL_TRUTH_FREEZE_VERSION
from nico.mid_truth_identity_consistency import repair_stale_mid_approval
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


def _run_id(prefix: str = "midrun_truth_freeze") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _section(section_id: str) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": 71,
        "status": "yellow",
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
        "customer_id": "customer_truth_freeze",
        "project_id": "project_truth_freeze",
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
            "dependency_evidence": {
                "manifest_paths": ["requirements.txt", "apps/web/package-lock.json"],
                "dependency_entries": 20,
            },
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
            "tools_requested": [
                "pip-audit",
                "npm-audit",
                "osv-scanner",
                "gitleaks",
                "trufflehog",
                "bandit",
                "semgrep",
                "typescript",
            ],
            "tools_run": [
                "pip-audit",
                "npm-audit",
                "osv-scanner",
                "gitleaks",
                "trufflehog",
                "bandit",
                "semgrep",
                "typescript",
            ],
            "failed_tools": [],
            "timed_out_tools": [],
            "unavailable_tools": [],
            "full_history_verified_tools": ["gitleaks", "trufflehog"],
        },
        "assessment": {
            "status": "draft",
            "sections": [_section(section_id) for section_id in TECHNICAL_IDS],
            "maturity_signal": {
                "level": "Mid",
                "score": 72,
                "summary": "The pre-report display score differs from the seven-section weighted score.",
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
            {
                "step": "scanner_reconciliation",
                "status": "complete",
                "message": "Scanner reconciled.",
                "evidence": {"scanner_status": "complete"},
            },
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
            "customer_id": "customer_truth_freeze",
            "project_id": "project_truth_freeze",
            "client_name": "Truth Freeze Test",
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
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "truth-freeze-admin-token")


def test_approval_freezes_truth_and_reconciles_duplicate_display_score() -> None:
    run_id = _run_id()
    _create_complete_run(run_id)

    requested = request_mid_approval(
        run_id,
        "customer_truth_freeze",
        "project_truth_freeze",
        admin_token="truth-freeze-admin-token",
    )

    assert requested["status"] == "requested"
    assert requested["approval"]["status"] == "pending"
    assert requested["truth_freeze"]["version"] == MID_APPROVAL_TRUTH_FREEZE_VERSION
    assert requested["truth_freeze"]["weighted_technical_score"] == 71
    assert requested["truth_freeze"]["prior_display_score"] == 72
    assert requested["truth_freeze"]["display_score_reconciled"] is True

    retained = STORE.get("assessment_runs", run_id)
    response = retained["response"]
    assert response["technical_score"] == 71
    assert response["assessment"]["maturity_signal"]["score"] == 71
    assert response["maturity_signal"]["score"] == 71

    report = STORE.get("reports", requested["approval"]["draft_report_id"])
    payload = report["formats"]["json"]
    assert payload["technical_score"] == 71
    assert payload["decision_summary"]["technical_score"] == 71
    assert report["source_identity"]["truth_sha256"] == requested["approval"]["truth_sha256"]


def test_existing_stale_block_projects_repair_and_recovers_same_run() -> None:
    run_id = _run_id("midrun_existing_stale")
    _create_complete_run(run_id)
    report = generate_mid_draft_report(
        run_id,
        "customer_truth_freeze",
        "project_truth_freeze",
        admin_token="truth-freeze-admin-token",
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

    projected = mid_terminal_truth_patch._terminal_retained_response(record)
    assert projected is not None
    assert projected["status"] == "running"
    assert projected["approval_request_status"] == "repair_pending"
    assert projected["continuation_required"] is True

    repaired = repair_stale_mid_approval(record, store=STORE)
    retained = STORE.get("assessment_runs", run_id)
    assert repaired is not None
    assert repaired["run_id"] == run_id
    assert repaired["status"] == "complete"
    assert repaired["approval_request_status"] == "pending"
    assert retained["status"] == "complete"
    assert retained["run_id"] == run_id
    assert retained["response"]["technical_score"] == 71
    assert retained["response"]["assessment"]["maturity_signal"]["score"] == 71
