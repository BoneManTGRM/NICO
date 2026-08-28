from __future__ import annotations

import base64
import hashlib
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


def _report(*, language: str = "en") -> dict:
    pdf = b"%PDF-1.4\nintermediate decision-stage draft\n%%EOF\n"
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
        "markdown": "# Intermediate decision-stage draft\n",
        "html": "<h1>Intermediate decision-stage draft</h1>",
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
        "approved",
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
