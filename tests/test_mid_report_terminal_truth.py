from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import mid_assessment_report
from nico.assessment_persistence_truth_patch import _truthful_persistence_metadata
from nico.mid_terminal_truth_patch import MID_STATUS_PATH, mid_status_endpoint, normalize_mid_terminal_truth
from nico.report_quality_gate import evaluate_report_payload
from nico.storage import STORE


def _run_id(prefix: str = "midrun_truth") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _technical_section(section_id: str, score: int = 70) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "yellow",
        "truth_status": "Verified with limitations",
        "summary": f"Retained evidence supports a bounded conclusion for {section_id} with explicit review limitations.",
        "evidence": [f"Exact-run evidence for {section_id} was retained."],
        "findings": [f"Review the material condition retained for {section_id}."],
        "unavailable": ["Automated evidence does not prove the absence of all defects."],
        "missing_evidence_sources": [],
        "failed_evidence_tools": [],
        "source_classification": "repository_evidence",
        "direct_repository_proof": True,
        "human_review_required": True,
        "unsupported_claims_permitted": False,
    }


def _report_record(run_id: str) -> tuple[dict, dict, dict]:
    section_ids = [
        "code_audit",
        "dependency_health",
        "secrets_review",
        "static_analysis",
        "ci_cd",
        "architecture_debt",
        "velocity_complexity",
    ]
    sections = [_technical_section(section_id) for section_id in section_ids]
    truth = {
        "version": "mid-truth-status-test",
        "sections": sections,
        "summary": {
            "section_count": 7,
            "verified": 0,
            "verified_with_limitations": 7,
            "unavailable": 0,
            "failed": 0,
            "human_review_required": 0,
            "items_requiring_review": 7,
            "unsupported_claims_permitted": 0,
        },
        "evidence_coverage": {
            "calculated": True,
            "percent": 83,
            "numerator": 10,
            "denominator": 12,
            "method": "Explicit exact-run evidence units.",
        },
        "unsupported_claims_permitted": 0,
    }
    record = {
        "run_id": run_id,
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": "a" * 40,
        "request": {"client_name": "Test Client", "project_name": "Test Project"},
        "response": {
            "mid_truth_status": truth,
            "assessment": {
                "sections": sections,
                "maturity_signal": {
                    "level": "Senior",
                    "score": 91,
                    "summary": "The earlier assessment display score preceded final seven-section report reconciliation.",
                },
            },
        },
    }
    packet = {
        "review_packet_id": f"packet_{run_id}",
        "review_packet_sha256": "b" * 64,
        "summary": {"items_requiring_review": 7},
        "exceptions": [],
        "verified_sections": section_ids,
    }
    identity = {
        "report_version": "test",
        "report_type": "mid_assessment",
        "report_path": "mid_run",
        "run_id": run_id,
        "customer_id": "customer_test",
        "project_id": "project_test",
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": "a" * 40,
        "review_packet_id": packet["review_packet_id"],
        "review_packet_sha256": packet["review_packet_sha256"],
        "truth_version": truth["version"],
        "truth_sha256": "c" * 64,
        "evidence_coverage_percent": 83,
        "evidence_coverage_numerator": 10,
        "evidence_coverage_denominator": 12,
    }
    return record, packet, identity


def test_final_reconciled_mid_score_does_not_false_block_quality_gate() -> None:
    run_id = _run_id()
    record, packet, identity = _report_record(run_id)

    payload = mid_assessment_report._report_payload(record, packet, identity, "2099-01-01T00:00:00Z")
    integrity = payload["score_integrity"]
    manifest = evaluate_report_payload(payload, "mid")

    assert integrity["reported_score_before_final_report_reconciliation"] == 91
    assert integrity["reported_score_match_before_final_report_reconciliation"] is False
    assert integrity["final_report_score"] == 70
    assert integrity["score_match"] is True
    assert integrity["final_report_score_matches_weighted_calculation"] is True
    assert payload["technical_score"] == 70
    assert not any(item["code"] == "score_integrity_mismatch" for item in manifest["issues"])
    assert manifest["status"] in {"ready_for_human_review", "review_required"}


def test_terminal_mid_state_reconciles_stale_scanner_and_exposes_quality_codes() -> None:
    run_id = _run_id()
    STORE.put(
        "reports",
        f"mid_report_{run_id}",
        {
            "report_id": f"mid_report_{run_id}",
            "run_id": run_id,
            "customer_id": "customer_test",
            "project_id": "project_test",
            "status": "blocked",
            "report_path": "mid_run",
            "report_version": "test",
            "report_quality_manifest": {
                "status": "blocked",
                "quality_score": 76,
                "issues": [
                    {
                        "severity": "critical",
                        "code": "score_integrity_mismatch",
                        "message": "Reported technical score did not match the retained weighted calculation.",
                    }
                ],
                "rendered_formats": {"status": "verified"},
            },
        },
    )
    result = {
        "run_id": run_id,
        "customer_id": "customer_test",
        "project_id": "project_test",
        "status": "complete",
        "scanner": {"scan_id": f"scan_{run_id}", "status": "running"},
        "scanner_evidence": {"scan_id": f"scan_{run_id}", "status": "attached", "scanner_status": "complete"},
        "report_generation_status": "blocked",
        "approval_request_status": "pending",
        "assessment": {
            "maturity_signal": {"level": "Mid", "score": 70, "evidence_readiness_score": 83},
            "evidence_coverage": {"calculated": True, "percent": 83, "numerator": 10, "denominator": 12},
        },
        "progress": [
            {"step": "scanner_reconciliation", "status": "running", "message": "Continuing scanner reconciliation.", "evidence": {"scanner_status": "complete"}},
            {"step": "evidence_attachment", "status": "complete", "message": "Evidence attached.", "evidence": {}},
            {"step": "scoring", "status": "complete", "message": "Scoring complete.", "evidence": {}},
            {"step": "reports", "status": "blocked", "message": "Report blocked.", "evidence": {}},
            {"step": "approval_request", "status": "not_started", "message": "Not started.", "evidence": {}},
        ],
    }

    output = normalize_mid_terminal_truth(result)
    progress = {item["step"]: item for item in output["progress"]}

    assert output["status"] == "blocked"
    assert output["current_stage"] == "reports"
    assert output["progress_percent"] == 100
    assert output["scanner"]["status"] == "complete"
    assert progress["scanner_reconciliation"]["status"] == "complete"
    assert progress["reports"]["evidence"]["critical_issue_codes"] == ["score_integrity_mismatch"]
    assert output["report_quality_blockers"] == ["score_integrity_mismatch"]
    assert output["technical_score"] == 70
    assert output["evidence_coverage"]["percent"] == 83
    assert output["continuation_required"] is False


def test_mid_and_full_persistence_metadata_do_not_call_writable_sqlite_durable() -> None:
    class FakeStore:
        def status(self):
            return {
                "adapter": "sqlite",
                "persistence_available": True,
                "durability_verified": False,
                "persistence_note": "SQLite recording is writable.",
                "durability_warning": "Container survival is not verified.",
            }

    status = _truthful_persistence_metadata(FakeStore(), restored=False)

    assert status["writable"] is True
    assert status["recorded"] is False
    assert status["durable"] is False
    assert status["durability_verified"] is False
    assert status["survives_container_replacement_verified"] is False
    assert "not verified" in status["warning"].lower()


def test_canonical_mid_status_returns_bounded_404_instead_of_generic_500() -> None:
    app = FastAPI()
    app.add_api_route(MID_STATUS_PATH, mid_status_endpoint, methods=["POST"])
    client = TestClient(app)

    response = client.post(
        "/assessment/mid-run/midrun_missing_status/status",
        json={"customer_id": "default_customer", "project_id": "default_project"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["status"] == "not_found"
    assert response.status_code != 500
