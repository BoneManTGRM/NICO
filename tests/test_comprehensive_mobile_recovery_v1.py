from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_mobile_recovery_v1 import (
    ARTIFACT_ROUTE_PATHS,
    BROWSER_PROJECTION_HEADER,
    BROWSER_PROJECTION_VALUE,
)


class _Service:
    def __init__(self, record: dict) -> None:
        self.record = record

    def load(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return self.record

    def load_read_only(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return self.record


def _record(*, terminal: bool = True) -> dict:
    pdf = b"%PDF-1.4\n% NICO terminal report\n%%EOF\n"
    markdown = "# NICO Comprehensive Technical Assessment\n\nFinal report pending human approval.\n"
    html = "<!doctype html><html><body><h1>NICO Comprehensive Technical Assessment</h1></body></html>"
    canonical = {
        "report_language": "en",
        "locale": "en",
        "identity": {
            "run_id": "comprun_mobile_recovery_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_mobile_recovery_001",
            "report_language": "en",
            "locale": "en",
        },
        "assessment": {
            "report_language": "en",
            "locale": "en",
            "maturity_signal": {"level": "Senior", "presented_score": 91},
        },
        "large": "z" * (2 * 1024 * 1024),
    }
    truth_sha256 = canonical_sha256(canonical)
    report = {
        "service_id": "comprehensive",
        "report_id": "report_mobile_recovery_001",
        "report_language": "en",
        "locale": "en",
        "markdown": markdown,
        "html": html,
        "json": canonical,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_filename": "nico-comprehensive-FINAL-PENDING-APPROVAL.pdf",
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "canonical_truth_sha256": truth_sha256,
    }
    assessment = {
        "executive_summary": "Decision-grade assessment complete pending expert review.",
        "evidence_coverage": {"calculated": True, "percent": 98, "label": "Evidence"},
        "maturity_signal": {"level": "Senior", "score": 91, "presented_score": 91},
        "sections": [
            {
                "id": "architecture",
                "label": "Architecture",
                "score": 91,
                "presented_score": 91,
                "summary": "Architecture evidence was reconciled.",
                "evidence": ["bounded evidence"],
            }
        ],
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }
    status = "review_required" if terminal else "running"
    return {
        "artifact_schema": "nico.comprehensive_run_record.v4",
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_mobile_recovery_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_mobile_recovery_001",
            "customer_id": "customer_mobile",
            "project_id": "project_mobile",
            "assessment_depth": "strategic",
            "report_language": "en",
        },
        "status": status,
        "current_stage": "human_review_request" if terminal else "cross_format_truth_verification",
        "completed_stages": ["final_comprehensive_report_generation"] if terminal else [],
        "stage_results": {
            "final_comprehensive_report_generation": {
                "status": "complete" if terminal else "running",
                "summary": "Final report generated." if terminal else "Final report is being generated.",
                "report_package": report,
                "assessment": assessment,
            }
        },
        "blockers": [],
        "progress_percent": 100.0 if terminal else 94.0,
        "revision": 77,
        "terminal": terminal,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "integrity_sha256": "c" * 64,
    }


def _approved_record(
    *,
    accepted_pdf_sha256: str = "",
    client_delivery_allowed: bool = False,
) -> dict:
    from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition

    record = _record()
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    identity = record["identity"]
    report["json"]["identity"] = deepcopy(identity)
    report["canonical_truth_sha256"] = canonical_sha256(report["json"])
    pdf = base64.b64decode(report["pdf_base64"], validate=True)
    accepted = build_accepted_report_edition(
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        tree_sha="tree-mobile-recovery-001",
        run_id=identity["run_id"],
        scanner_run_id="scanner-mobile-recovery-001",
        evidence_bundle_hash="evidence-mobile-recovery-001",
        report_language=identity["report_language"],
        assessment_depth=identity["assessment_depth"],
        artifacts={
            "markdown": report["markdown"],
            "html": report["html"],
            "pdf": pdf,
            "json": report["json"],
        },
        reviewer="Authorized Reviewer",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Exact immutable report reviewed.",
        decided_at="2026-08-28T12:00:00+00:00",
    )
    if accepted_pdf_sha256:
        accepted["artifact_digests"]["pdf"]["sha256"] = accepted_pdf_sha256
    record.update(
        {
            "status": "approved",
            "human_review_completed": True,
            "client_delivery_allowed": client_delivery_allowed,
            "accepted_edition": accepted,
            "review_decision": deepcopy(accepted),
            "review_history": [deepcopy(accepted)],
        }
    )
    return record


def _app(record: dict) -> FastAPI:
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "durability_verified": True,
        "survives_container_replacement_verified": True,
    }
    routes.register_comprehensive_api_routes(
        app,
        controller=ComprehensiveApiController(_Service(record)),
    )
    return app


def test_browser_terminal_status_returns_small_manifest_not_embedded_artifacts(
    monkeypatch,
) -> None:
    def fail_if_called(_record):
        raise AssertionError(
            "public browser status must not digest the reviewer artifact package"
        )

    monkeypatch.setattr(routes, "review_artifact_identity", fail_if_called)
    response = TestClient(_app(_record())).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001",
        headers={BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["assessment"]["maturity_signal"]["presented_score"] == 91
    assert body["reports"]["pdf_available"] is True
    assert body["reports"]["markdown_available"] is True
    assert body["reports"]["artifact_delivery"] == "on_demand_exact_run"
    assert "pdf_base64" not in body["reports"]
    assert "markdown" not in body["reports"]
    assert "html" not in body["reports"]
    assert "json" not in body["reports"]
    assert "review_artifact_identity" not in body
    assert len(response.content) < 200_000


def test_non_browser_status_preserves_full_report_for_existing_consumers() -> None:
    record = _record()
    response = TestClient(_app(record)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    )

    assert response.status_code == 200
    payload = response.json()
    report = payload["reports"]
    assert payload["review_artifact_identity"] == routes.review_artifact_identity(
        record
    )
    assert report["markdown"].startswith("# NICO Comprehensive")
    assert base64.b64decode(report["pdf_base64"]).startswith(b"%PDF")
    assert report["canonical_truth_sha256"] == canonical_sha256(report["json"])
    assert report["json"]["assessment"]["maturity_signal"]["presented_score"] == 91
    assert len(report["json"]["large"]) == 2 * 1024 * 1024


def test_exact_run_artifact_routes_stream_canonical_content() -> None:
    client = TestClient(_app(_record()))
    markdown = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/markdown"
    )
    pdf = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    canonical = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/json"
    )

    assert markdown.status_code == 200
    assert markdown.text.startswith("# NICO Comprehensive Technical Assessment")
    assert markdown.headers["x-nico-run-id"] == "comprun_mobile_recovery_001"
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["x-nico-artifact-sha256"] == hashlib.sha256(pdf.content).hexdigest()
    assert pdf.headers["x-nico-commit-sha"] == "b" * 40
    assert pdf.headers["x-nico-report-language"] == "en"
    assert pdf.headers["x-nico-assessment-rerun"] == "false"
    assert pdf.headers["x-nico-approval-status"] == "pending_human_approval"
    assert pdf.headers["x-nico-client-delivery-allowed"] == "false"
    assert "x-nico-accepted-pdf-sha256" not in pdf.headers
    assert "FINAL-PENDING-APPROVAL.pdf" in pdf.headers["content-disposition"]
    assert canonical.status_code == 200
    assert canonical.headers["x-nico-canonical-truth-sha256"] == canonical_sha256(
        canonical.json()
    )
    assert len(json.dumps(canonical.json())) > 2 * 1024 * 1024


def test_exact_artifact_download_never_invokes_maintenance_capable_load() -> None:
    record = _record()

    class ReadOnlyArtifactService(_Service):
        def load(self, run_id: str) -> dict:
            raise AssertionError("artifact download must not resume or maintain a run")

    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "durability_verified": True,
        "survives_container_replacement_verified": True,
    }
    routes.register_comprehensive_api_routes(
        app,
        controller=ComprehensiveApiController(ReadOnlyArtifactService(record)),
    )

    response = TestClient(app).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_approved_pdf_route_streams_only_exact_accepted_edition_bytes() -> None:
    approved = _approved_record()
    before = deepcopy(approved)
    exact = TestClient(_app(approved)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )

    assert exact.status_code == 200
    observed = hashlib.sha256(exact.content).hexdigest()
    accepted = approved["accepted_edition"]["artifact_digests"]["pdf"]["sha256"]
    assert observed == accepted
    assert exact.headers["x-nico-artifact-sha256"] == accepted
    assert exact.headers["x-nico-accepted-pdf-sha256"] == accepted
    assert exact.headers["x-nico-accepted-edition-language"] == "en"
    assert exact.headers["x-nico-accepted-edition-manifest-sha256"] == approved[
        "accepted_edition"
    ]["accepted_edition_manifest_sha256"]
    assert exact.headers["x-nico-commit-sha"] == "b" * 40
    assert exact.headers["x-nico-report-language"] == "en"
    assert exact.headers["x-nico-assessment-rerun"] == "false"
    assert exact.headers["x-nico-approval-status"] == "approved_final"
    assert exact.headers["x-nico-delivery-status"] == "pending_authorization"
    assert exact.headers["x-nico-client-delivery-allowed"] == "false"
    assert "FINAL-PENDING-APPROVAL.pdf" in exact.headers[
        "content-disposition"
    ]
    assert approved == before

    approval_pending_delivery = _approved_record(client_delivery_allowed=False)
    pending = TestClient(_app(approval_pending_delivery)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    assert pending.status_code == 200
    assert hashlib.sha256(pending.content).hexdigest() == accepted
    assert pending.headers["x-nico-accepted-pdf-sha256"] == accepted
    assert pending.headers["x-nico-client-delivery-allowed"] == "false"
    assert pending.headers["x-nico-delivery-status"] == "pending_authorization"

    mismatched = _approved_record(accepted_pdf_sha256="0" * 64)
    blocked = TestClient(_app(mismatched)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )
    assert blocked.json()["detail"]["client_delivery_allowed"] is False


@pytest.mark.parametrize(
    "path",
    (
        "report/markdown",
        "report/html",
        "report/json",
    ),
)
def test_approved_non_pdf_routes_require_the_same_exact_accepted_edition(
    path: str,
) -> None:
    response = TestClient(_app(_approved_record())).get(
        f"/assessment/comprehensive-run/comprun_mobile_recovery_001/{path}"
    )

    assert response.status_code == 200
    assert response.headers["x-nico-approval-status"] == "approved_final"
    assert response.headers["x-nico-delivery-status"] == "pending_authorization"
    assert response.headers["x-nico-client-delivery-allowed"] == "false"


def test_raw_delivery_flag_cannot_replace_distinct_authorization_receipt() -> None:
    record = _approved_record(client_delivery_allowed=True)
    client = TestClient(_app(record))

    artifact = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    status = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    ).json()

    assert artifact.status_code == 200
    assert artifact.headers["x-nico-approval-status"] == "approved_final"
    assert artifact.headers["x-nico-delivery-status"] == "pending_authorization"
    assert artifact.headers["x-nico-client-delivery-allowed"] == "false"
    assert status["status"] == "approved"
    assert status["human_review_completed"] is True
    assert status["client_delivery_allowed"] is False
    assert status["delivery_status"] == "blocked_authorization_integrity"
    assert status["response_projection"][
        "delivery_authorization_invalidated"
    ] is True


@pytest.mark.parametrize(
    ("path", "artifact"),
    (
        ("report/markdown", "markdown"),
        ("report/html", "html"),
        ("report/json", "json"),
    ),
)
def test_approved_non_pdf_routes_reject_artifacts_changed_after_approval(
    path: str,
    artifact: str,
) -> None:
    record = _approved_record()
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    if artifact == "json":
        report["json"]["assessment"]["maturity_signal"]["presented_score"] = 92
        report["canonical_truth_sha256"] = canonical_sha256(report["json"])
    else:
        report[artifact] += "\nchanged after exact human approval"

    response = TestClient(_app(record)).get(
        f"/assessment/comprehensive-run/comprun_mobile_recovery_001/{path}"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )
    assert "x-nico-approval-status" not in response.headers
    assert "x-nico-client-delivery-allowed" not in response.headers


def test_status_projection_invalidates_approval_when_exact_artifacts_change() -> None:
    record = _approved_record()
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    report["markdown"] += "\nchanged after exact human approval"

    response = TestClient(_app(record)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["canonical_status"] == "approved"
    assert body["approval_status"] == "invalidated_artifact_mismatch"
    assert body["human_review_completed"] is False
    assert body["client_delivery_allowed"] is False
    assert body["delivery_status"] == "blocked_artifact_integrity"
    assert body["record"]["status"] == "blocked"
    assert body["record"]["human_review_completed"] is False
    assert body["record"]["client_delivery_allowed"] is False
    assert "accepted_edition" not in body
    assert "reports" not in body
    assert body["response_projection"][
        "approval_invalidated_by_artifact_mismatch"
    ] is True


def test_pending_status_cannot_reuse_stale_completed_approval_state() -> None:
    record = _approved_record()
    record["status"] = "review_required"

    body = TestClient(_app(record)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    ).json()

    assert body["status"] == "review_required"
    assert body["approval_status"] == "pending_human_approval"
    assert body["human_review_completed"] is False
    assert body["client_delivery_allowed"] is False
    assert "accepted_edition" not in body
    assert "review_decision" not in body
    assert body["response_projection"]["stale_approval_state_suppressed"] is True


def test_rejected_status_requires_exact_hashed_human_decision() -> None:
    record = _record()
    record["status"] = "rejected"
    record["human_review_completed"] = False

    body = TestClient(_app(record)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    ).json()

    assert body["status"] == "blocked"
    assert body["canonical_status"] == "rejected"
    assert body["approval_status"] == "invalidated_review_receipt_mismatch"
    assert body["human_review_completed"] is False
    assert body["client_delivery_allowed"] is False
    assert body["response_projection"][
        "rejection_invalidated_by_review_mismatch"
    ] is True


def test_approved_pdf_route_rejects_manifest_and_language_tampering() -> None:
    tampered_manifest = _approved_record()
    tampered_manifest["accepted_edition"]["review"]["reason"] = "tampered"
    manifest_response = TestClient(_app(tampered_manifest)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    assert manifest_response.status_code == 409
    assert manifest_response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )

    wrong_language = _approved_record()
    accepted = wrong_language["accepted_edition"]
    accepted["report_language"] = "es-MX"
    accepted.pop("accepted_edition_manifest_sha256")
    accepted["accepted_edition_manifest_sha256"] = canonical_sha256(accepted)
    language_response = TestClient(_app(wrong_language)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    assert language_response.status_code == 409
    assert language_response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )

    delivery_rewritten = _approved_record()
    accepted = delivery_rewritten["accepted_edition"]
    accepted["client_delivery_allowed"] = True
    accepted["delivery_status"] = "approved_for_delivery"
    accepted.pop("accepted_edition_manifest_sha256")
    accepted["accepted_edition_manifest_sha256"] = canonical_sha256(accepted)
    rewritten_response = TestClient(_app(delivery_rewritten)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    assert rewritten_response.status_code == 409
    assert rewritten_response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )


def test_approved_pdf_route_rejects_current_bytes_changed_after_approval() -> None:
    record = _approved_record()
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    changed = b"%PDF-1.4\nchanged after exact human approval\n%%EOF\n"
    report["pdf_base64"] = base64.b64encode(changed).decode("ascii")
    report["pdf_sha256"] = hashlib.sha256(changed).hexdigest()

    response = TestClient(_app(record)).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )


def test_report_artifacts_fail_closed_before_terminal_state() -> None:
    response = TestClient(_app(_record(terminal=False))).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_report_not_ready"
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False


def test_artifact_route_registration_is_idempotent() -> None:
    app = _app(_record())
    controller = ComprehensiveApiController(_Service(_record()))
    routes.register_comprehensive_api_routes(app, controller=controller)

    paths = [str(getattr(route, "path", "")) for route in app.routes]
    for path in ARTIFACT_ROUTE_PATHS:
        assert paths.count(path) == 1
