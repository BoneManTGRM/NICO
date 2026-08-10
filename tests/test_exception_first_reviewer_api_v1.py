from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes


class _LoadOnlyService:
    def __init__(self, record: dict) -> None:
        self.record = record

    def load(self, run_id: str) -> dict:
        if run_id != self.record["identity"]["run_id"]:
            raise AssertionError("unexpected run identity")
        return deepcopy(self.record)


def _candidate(
    candidate_id: str,
    *,
    cluster_id: str,
    grouped: bool,
    individual: bool,
    representative: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "category": "static",
        "severity": "medium",
        "scanner": "semgrep",
        "rule": "python.lang.security.audit.example",
        "source_path": "nico/example.py",
        "lineage_status": "newly_observed",
        "technical_triage_verdict": "needs_review",
        "technical_triage_confidence": "medium",
        "technical_triage_rationale": "Exact evidence requires professional review.",
        "technical_triage_proof_gaps": ["first_party_reachability"],
        "technical_triage_recommended_next_step": "Review the exact source context.",
        "review_routing_class": "HUMAN_TECHNICAL_REVIEW",
        "review_requires_individual_attention": individual,
        "grouped_review_eligible": grouped,
        "cluster_id": cluster_id,
        "representative_candidate_id": representative,
        "human_disposition": None,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _record(
    *,
    terminal: bool = True,
    status: str = "review_required",
    identity_mismatch: bool = False,
    count_mismatch: bool = False,
) -> dict:
    identity = {
        "run_id": "comprun_exception_queue_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_exception_queue_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
    }
    findings = [
        _candidate(
            "NICO-SCAN-INDIVIDUAL",
            cluster_id="NICO-CLUSTER-INDIVIDUAL",
            grouped=False,
            individual=True,
            representative="NICO-SCAN-INDIVIDUAL",
        ),
        _candidate(
            "NICO-SCAN-GROUP-A",
            cluster_id="NICO-CLUSTER-GROUPED",
            grouped=True,
            individual=False,
            representative="NICO-SCAN-GROUP-A",
        ),
        _candidate(
            "NICO-SCAN-GROUP-B",
            cluster_id="NICO-CLUSTER-GROUPED",
            grouped=True,
            individual=False,
            representative="NICO-SCAN-GROUP-A",
        ),
    ]
    register = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_record_count": len(findings) + (1 if count_mismatch else 0),
        "canonical_digest_sha256": "b" * 64,
        "findings": findings,
        "technical_triage": {
            "total_candidates": len(findings),
            "candidates_requiring_individual_human_attention": 1,
            "candidates_eligible_for_grouped_review": 2,
            "cluster_count": 1,
            "human_review_work_units": 2,
            "human_disposition_created": False,
            "client_delivery_allowed": False,
        },
    }
    canonical_identity = dict(identity)
    if identity_mismatch:
        canonical_identity["commit_sha"] = "c" * 40
    canonical = {
        "identity": canonical_identity,
        "assessment": {"canonical_scanner_finding_register": register},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "artifact_schema": "nico.comprehensive_run_record.v1",
        "identity": identity,
        "status": status,
        "terminal": terminal,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_results": {
            "final_comprehensive_report_generation": {
                "status": "complete",
                "report_package": {
                    "report_id": "report_exception_queue_001",
                    "json": canonical,
                    "pdf_base64": "not-returned-by-review-queue",
                },
            }
        },
    }


def _client(monkeypatch, record: dict) -> TestClient:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "storage_source": "DATABASE_URL",
        "survives_container_replacement_verified": True,
    }
    controller = ComprehensiveApiController(_LoadOnlyService(record))
    register_comprehensive_api_routes(app, controller=controller)
    return TestClient(app)


def test_review_queue_requires_operator_auth_and_returns_only_canonical_queue(monkeypatch) -> None:
    client = _client(monkeypatch, _record())
    path = "/assessment/comprehensive-run/comprun_exception_queue_001/review-queue"

    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-NICO-Admin-Token": "wrong"}).status_code == 403

    response = client.get(path, headers={"X-NICO-Admin-Token": "operator-secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["artifact_schema"] == "nico.exception_first_reviewer_queue.v1"
    assert body["operation"] == "review_queue"
    assert body["source"] == "canonical_terminal_comprehensive_report_json"
    assert body["read_only"] is True
    assert body["status"] == "review_required"
    assert body["terminal"] is True
    assert body["candidate_count"] == 3
    assert body["human_review_work_units"] == 2
    assert len(body["candidate_register"]["findings"]) == 3
    assert body["candidate_register"]["technical_triage"]["human_review_work_units"] == 2
    assert body["human_review_required"] is True
    assert body["client_delivery_allowed"] is False
    assert body["persistence"]["durable"] is True
    assert "reports" not in body
    assert "pdf_base64" not in body
    assert "review_decision" not in body


def test_review_queue_fails_closed_before_terminal_human_review(monkeypatch) -> None:
    client = _client(monkeypatch, _record(terminal=False, status="running"))
    response = client.get(
        "/assessment/comprehensive-run/comprun_exception_queue_001/review-queue",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "comprehensive_review_queue_terminal_run_required"


def test_review_queue_rejects_cross_run_report_identity(monkeypatch) -> None:
    client = _client(monkeypatch, _record(identity_mismatch=True))
    response = client.get(
        "/assessment/comprehensive-run/comprun_exception_queue_001/review-queue",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "comprehensive_review_queue_identity_mismatch"


def test_review_queue_rejects_candidate_count_drift(monkeypatch) -> None:
    client = _client(monkeypatch, _record(count_mismatch=True))
    response = client.get(
        "/assessment/comprehensive-run/comprun_exception_queue_001/review-queue",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "comprehensive_review_queue_candidate_count_mismatch"
