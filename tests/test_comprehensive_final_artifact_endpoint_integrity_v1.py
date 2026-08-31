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
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_same_run_locale_report_v1 import (
    _canonical_hash,
    install_same_run_locale_report,
)


RUN_ID = "comprun_final_artifact_integrity_001"
REPOSITORY = "BoneManTGRM/NICO"
COMMIT_SHA = "a" * 40
LEDGER_ID = "ledger_final_artifact_integrity_001"
FINAL_STAGE = "final_comprehensive_report_generation"


class _Service:
    def __init__(self, record: dict) -> None:
        self.record = record

    def load(self, run_id: str) -> dict:
        assert run_id == RUN_ID
        return self.record

    def load_read_only(self, run_id: str) -> dict:
        assert run_id == RUN_ID
        return self.record

    def load_public_intake(self, run_id: str) -> None:
        assert run_id == RUN_ID
        return None


def _report(*, language: str = "en") -> dict:
    pdf = b"%PDF-1.4\nintermediate decision-stage draft\n%%EOF\n"
    markdown = "# Intermediate decision-stage draft\n"
    html = "<h1>Intermediate decision-stage draft</h1>"
    canonical = {
        "service_id": "comprehensive",
        "report_id": "report_intermediate_decision_stage_001",
        "report_language": language,
        "locale": language,
        "identity": {
            "run_id": RUN_ID,
            "repository": REPOSITORY,
            "commit_sha": COMMIT_SHA,
            "evidence_ledger_id": LEDGER_ID,
            "report_language": language,
            "locale": language,
        },
        "assessment": {
            "report_language": language,
            "locale": language,
            "maturity_signal": {"score": 93, "presented_score": 93},
            "sections": [],
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha256 = _canonical_hash(canonical)
    return {
        "service_id": "comprehensive",
        "report_id": canonical["report_id"],
        "report_language": language,
        "locale": language,
        "markdown": markdown,
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html": html,
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "json": canonical,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_filename": "nico-intermediate-DRAFT.pdf",
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "canonical_truth_sha256": truth_sha256,
    }


def _record_with_blocked_final_stage() -> dict:
    report = _report(language="en")
    return {
        "artifact_schema": "nico.comprehensive_run_record.v5",
        "service_id": "comprehensive",
        "identity": {
            "run_id": RUN_ID,
            "repository": REPOSITORY,
            "commit_sha": COMMIT_SHA,
            "evidence_ledger_id": LEDGER_ID,
            "customer_id": "customer_final_artifact_integrity",
            "project_id": "project_final_artifact_integrity",
            "assessment_depth": "strategic",
            "report_language": "en",
        },
        "status": "blocked",
        "current_stage": FINAL_STAGE,
        "completed_stages": list(COMPREHENSIVE_STAGES[:19]),
        "stage_results": {
            "decision_report_generation": {
                "status": "complete",
                "report_package": report,
                "assessment": report["json"]["assessment"],
            },
            FINAL_STAGE: {
                "status": "blocked",
                "reason": "final_report_publication_deadline_exceeded",
                "error_code": "final_report_publication_deadline_exceeded",
                "retryable": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "artifacts_available": False,
            },
        },
        "blockers": [],
        "progress_percent": 82.61,
        "revision": 63,
        "terminal": True,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "integrity_sha256": "b" * 64,
    }


def _record_with_final_language_mismatch() -> dict:
    record = _record_with_blocked_final_stage()
    report = _report(language="en")
    record.update(
        {
            "status": "review_required",
            "current_stage": "client_acceptance_pending",
            "completed_stages": list(COMPREHENSIVE_STAGES),
            "progress_percent": 100.0,
            "revision": 88,
        }
    )
    record["identity"]["report_language"] = "es-MX"
    record["stage_results"][FINAL_STAGE] = {
        "status": "complete",
        "report_package": report,
        "assessment": report["json"]["assessment"],
    }
    return record


def _record_with_canonical_final_report(
    *,
    run_status: str = "review_required",
    stage_status: str = "complete",
) -> dict:
    record = _record_with_blocked_final_stage()
    report = _report(language="en")
    record.update(
        {
            "status": run_status,
            "current_stage": "client_acceptance_pending",
            "completed_stages": list(COMPREHENSIVE_STAGES),
            "progress_percent": 100.0,
            "revision": 89,
        }
    )
    record["stage_results"][FINAL_STAGE] = {
        "status": stage_status,
        "report_package": report,
        "assessment": report["json"]["assessment"],
    }
    return record


def _record_with_wrapper_only_language() -> dict:
    record = _record_with_canonical_final_report()
    report = record["stage_results"][FINAL_STAGE]["report_package"]
    canonical = report["json"]
    canonical.pop("report_language")
    canonical.pop("locale")
    canonical["identity"].pop("report_language")
    canonical["identity"].pop("locale")
    canonical["assessment"].pop("report_language")
    canonical["assessment"].pop("locale")
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
    install_same_run_locale_report(app)
    return app


@pytest.mark.parametrize(
    "path",
    (
        "report/markdown",
        "report/html",
        "report/json",
        "report/pdf",
        "localized-report/en",
        "localized-report/en/pdf",
        "localized-report/es-MX",
        "localized-report/es-MX/pdf",
    ),
)
def test_terminal_blocked_final_stage_never_exposes_intermediate_draft(path: str) -> None:
    record = _record_with_blocked_final_stage()
    before = deepcopy(record)

    response = TestClient(_app(record)).get(
        f"/assessment/comprehensive-run/{RUN_ID}/{path}"
    )

    assert response.status_code == 409
    assert record == before
    detail = response.json()["detail"]
    assert detail.get("client_delivery_allowed") is not True


@pytest.mark.parametrize("path", ("report/json", "report/pdf"))
def test_final_stage_artifact_language_must_match_run_identity(path: str) -> None:
    response = TestClient(_app(_record_with_final_language_mismatch())).get(
        f"/assessment/comprehensive-run/{RUN_ID}/{path}"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_report_artifact_missing"
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False


@pytest.mark.parametrize(
    "run_status",
    (
        "complete",
        "completed",
        "review_required",
        "rejected",
        "declined",
    ),
)
@pytest.mark.parametrize(
    "stage_status",
    ("complete", "completed", "passed", "review_required", "success", "succeeded"),
)
def test_exact_language_bound_final_stage_artifact_accepts_success_compatibility(
    run_status: str,
    stage_status: str,
) -> None:
    response = TestClient(
        _app(
            _record_with_canonical_final_report(
                run_status=run_status,
                stage_status=stage_status,
            )
        )
    ).get(f"/assessment/comprehensive-run/{RUN_ID}/report/json")

    assert response.status_code == 200
    assert response.json()["identity"]["run_id"] == RUN_ID


def test_report_wrapper_language_cannot_replace_canonical_json_language() -> None:
    response = TestClient(_app(_record_with_wrapper_only_language())).get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/json"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "comprehensive_report_artifact_missing"


def test_approved_status_without_exact_accepted_edition_fails_closed() -> None:
    record = _record_with_canonical_final_report(run_status="approved")
    record["human_review_completed"] = True
    record["client_delivery_allowed"] = True

    response = TestClient(_app(record)).get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/json"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )
    assert response.json()["detail"]["client_delivery_allowed"] is False


def test_approved_manifest_family_tampering_fails_closed_on_all_report_routes() -> None:
    from nico.decision_grade_accepted_edition_v2 import (
        build_accepted_report_edition,
    )
    from nico.phase17_canonical_artifact_rebuild_v1 import (
        rebuild_client_artifacts,
    )
    from tests.test_v2_premium_report_renderer import _package

    source_input = _package("en")
    source_input["json"]["identity"].update(
        {
            "run_id": RUN_ID,
            "repository": REPOSITORY,
            "commit_sha": COMMIT_SHA,
            "evidence_ledger_id": LEDGER_ID,
            "assessment_depth": "strategic",
        }
    )
    source = rebuild_client_artifacts(source_input)
    source["report_id"] = "report_manifest_integrity_approved_001"
    identity = source["json"]["identity"]
    pdf = base64.b64decode(source["pdf_base64"], validate=True)
    accepted = build_accepted_report_edition(
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        tree_sha="tree-final-artifact-integrity-001",
        run_id=identity["run_id"],
        scanner_run_id="scanner-final-artifact-integrity-001",
        evidence_bundle_hash="evidence-final-artifact-integrity-001",
        report_language=identity["report_language"],
        assessment_depth=identity["assessment_depth"],
        artifacts={
            "markdown": source["markdown"],
            "html": source["html"],
            "pdf": pdf,
            "json": source["json"],
            "evidence_manifest": source["evidence_manifest_json"],
        },
        reviewer="Authorized Test Reviewer",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Exact immutable test artifacts reviewed.",
        decided_at="2026-08-28T12:00:00+00:00",
    )
    record = _record_with_canonical_final_report(run_status="approved")
    record["identity"].update(
        {
            "commit_sha": COMMIT_SHA,
            "assessment_depth": "strategic",
        }
    )
    record["human_review_completed"] = True
    record["client_delivery_allowed"] = False
    record["accepted_edition"] = accepted
    record["review_decision"] = deepcopy(accepted)
    record["review_history"] = [deepcopy(accepted)]
    record["stage_results"][FINAL_STAGE] = {
        "status": "complete",
        "report_package": source,
        "assessment": source["json"]["assessment"],
    }

    baseline = TestClient(_app(record))
    assert baseline.get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/json"
    ).status_code == 200
    assert baseline.get(
        f"/assessment/comprehensive-run/{RUN_ID}/localized-report/en"
    ).status_code == 200

    legacy_record = deepcopy(record)
    legacy_report = legacy_record["stage_results"][FINAL_STAGE]["report_package"]
    legacy_hash = _canonical_hash(legacy_report["json"])
    assert legacy_hash != legacy_report["canonical_truth_sha256"]
    legacy_report["canonical_truth_sha256"] = legacy_hash
    legacy_client = TestClient(_app(legacy_record))
    assert legacy_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/json"
    ).status_code == 200
    assert legacy_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}/localized-report/en"
    ).status_code == 200
    assert legacy_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/pdf"
    ).status_code == 200
    assert legacy_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}/localized-report/en/pdf"
    ).status_code == 200
    legacy_status = legacy_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}"
    ).json()
    assert legacy_status["status"] == "approved"
    assert legacy_status["response_projection"][
        "terminal_report_package_integrity_valid"
    ] is True

    def stale_manifest_hash(report: dict) -> None:
        report["evidence_manifest_sha256"] = "0" * 64

    def stale_detached_manifest(report: dict) -> None:
        report["artifact_manifest"]["manifest_id"] += "-tampered"

    def stale_draft_identity(report: dict) -> None:
        report["draft_artifact_identity"]["pdf_sha256"] = "0" * 64

    def missing_draft_identity(report: dict) -> None:
        report.pop("draft_artifact_identity")

    def stripped_top_level_manifest_family(report: dict) -> None:
        for field in (
            "artifact_manifest",
            "evidence_manifest_json",
            "evidence_manifest_sha256",
            "canonical_json",
            "canonical_json_sha256",
            "draft_artifact_identity",
        ):
            report.pop(field)

    def rebound_to_wrong_evidence_ledger(report: dict) -> None:
        manifest = deepcopy(report["artifact_manifest"])
        manifest["identity"]["evidence_ledger_id"] = "ledger_substituted_001"
        manifest_text = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        manifest_sha256 = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        report["artifact_manifest"] = manifest
        report["evidence_manifest_json"] = manifest_text
        report["evidence_manifest_sha256"] = manifest_sha256
        report["draft_artifact_identity"][
            "evidence_ledger_id"
        ] = "ledger_substituted_001"
        report["draft_artifact_identity"][
            "evidence_manifest_sha256"
        ] = manifest_sha256

    for mutate in (
        stale_manifest_hash,
        stale_detached_manifest,
        stale_draft_identity,
        missing_draft_identity,
        stripped_top_level_manifest_family,
        rebound_to_wrong_evidence_ledger,
    ):
        tampered = deepcopy(record)
        report = tampered["stage_results"][FINAL_STAGE]["report_package"]
        mutate(report)
        client = TestClient(_app(tampered))
        for route in ("report/json", "localized-report/en"):
            response = client.get(
                f"/assessment/comprehensive-run/{RUN_ID}/{route}"
            )
            assert response.status_code == 409
        status = client.get(
            f"/assessment/comprehensive-run/{RUN_ID}"
        ).json()
        assert status["status"] == "blocked"
        assert status["approval_status"] == "invalidated_artifact_mismatch"
        assert status["client_delivery_allowed"] is False

    pending = deepcopy(record)
    pending["status"] = "review_required"
    pending["human_review_completed"] = False
    pending.pop("accepted_edition")
    pending_report = pending["stage_results"][FINAL_STAGE]["report_package"]
    pending_report["evidence_manifest_sha256"] = "0" * 64
    pending_client = TestClient(_app(pending))
    pending_status = pending_client.get(
        f"/assessment/comprehensive-run/{RUN_ID}"
    ).json()
    assert pending_status["status"] == "blocked"
    assert pending_status["canonical_status"] == "review_required"
    assert pending_status["approval_status"] == "invalidated_artifact_mismatch"
    assert pending_status["response_projection"]["artifact_integrity_valid"] is False
    assert pending_status["response_projection"][
        "review_package_invalidated_by_artifact_mismatch"
    ] is True
    assert "reports" not in pending_status
    for route in (
        "report/json",
        "report/pdf",
        "localized-report/en",
        "localized-report/en/pdf",
    ):
        assert pending_client.get(
            f"/assessment/comprehensive-run/{RUN_ID}/{route}"
        ).status_code == 409


@pytest.mark.parametrize("path", ("report/json", "report/pdf"))
def test_final_package_rejects_stale_canonical_truth_hash(path: str) -> None:
    record = _record_with_canonical_final_report()
    report = record["stage_results"][FINAL_STAGE]["report_package"]
    report["json"]["assessment"]["maturity_signal"]["score"] = 94

    response = TestClient(_app(record)).get(
        f"/assessment/comprehensive-run/{RUN_ID}/{path}"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )


@pytest.mark.parametrize("pdf_sha256", ("", "0" * 64))
def test_final_package_requires_exact_stored_pdf_hash(pdf_sha256: str) -> None:
    record = _record_with_canonical_final_report()
    report = record["stage_results"][FINAL_STAGE]["report_package"]
    report["pdf_sha256"] = pdf_sha256

    response = TestClient(_app(record)).get(
        f"/assessment/comprehensive-run/{RUN_ID}/report/pdf"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "comprehensive_report_artifact_missing"
    )


def test_terminal_status_omits_noncanonical_intermediate_report_manifest() -> None:
    response = TestClient(_app(_record_with_blocked_final_stage())).get(
        f"/assessment/comprehensive-run/{RUN_ID}",
        headers={"X-NICO-Browser-Projection": "terminal-manifest-v1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["terminal"] is True
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert "reports" not in payload
    assert payload["response_projection"]["terminal_report_manifest_attached"] is False
    assert payload["response_projection"]["exact_run_artifact_endpoints_required"] is False
