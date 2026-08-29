from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_approved_delivery_v4 import (
    attach_approved_delivery_package,
    validate_approved_delivery_package,
)
from nico.comprehensive_delivery_authorization_v1 import authorize_accepted_edition
from nico.comprehensive_final_decision_truth_v1 import (
    synchronize_final_decision_truth,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_review_decision_v1 import (
    build_reviewed_edition,
    review_artifact_identity,
)
from nico.comprehensive_review_work_safe_v1 import apply_review_work_action
from nico.comprehensive_run_record import (
    _record_hash,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_same_run_locale_report_v1 import (
    install_same_run_locale_report,
)
from tests.test_phase4_approved_delivery_v4 import _record as _phase4_source_record


class _ReadOnlyService:
    def __init__(self, record: dict) -> None:
        self.record = record

    def load(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return self.record

    def load_read_only(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return self.record


def _authorized_phase4_record() -> dict:
    """Build a real validated run, approval manifest, and delivery package."""

    source = _phase4_source_record()
    identity = source["identity"]
    record = create_comprehensive_run_record(
        run_id=identity["run_id"],
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        evidence_ledger_id=identity["evidence_ledger_id"],
        customer_id=identity["customer_id"],
        project_id=identity["project_id"],
        authorized=True,
        assessment_depth=identity["assessment_depth"],
        report_language=identity["report_language"],
        human_evidence=source["human_evidence"],
    )
    record.update(
        {
            "status": "review_required",
            "terminal": True,
            "current_stage": "client_acceptance_pending",
            "completed_stages": list(COMPREHENSIVE_STAGES),
            "progress_percent": 100.0,
            "stage_results": deepcopy(source["stage_results"]),
            "generator_versions": deepcopy(source["generator_versions"]),
        }
    )
    record["stage_results"]["final_comprehensive_report_generation"][
        "status"
    ] = "complete"
    record["integrity_sha256"] = _record_hash(record)

    record["review_work_ledger"] = apply_review_work_action(
        record,
        {
            "action": "disposition_candidate",
            "candidate_id": "candidate-phase4-1",
            "disposition": "false_positive",
            "rationale": (
                "Exact retained evidence supports a non-actionable human disposition."
            ),
            "reviewer": "Alice Security",
            "reviewer_role": "Cybersecurity specialist",
            "review_authorized": True,
            "authorization_confirmed": True,
        },
        now=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
    )
    record["integrity_sha256"] = _record_hash(record)
    record = synchronize_final_decision_truth(
        record,
        decision="approved",
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision_reason=(
            "All exact candidate and residual-risk review gates are complete."
        ),
        decided_at="2026-08-21T15:00:00+00:00",
    )
    accepted_edition = build_reviewed_edition(
        record,
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decision_reason=(
            "All exact candidate and residual-risk review gates are complete."
        ),
        decided_at="2026-08-21T15:00:00+00:00",
    )
    record["status"] = "approved"
    record["human_review_completed"] = True
    record["accepted_edition"] = deepcopy(accepted_edition)
    record["review_decision"] = deepcopy(accepted_edition)
    record["review_history"] = [deepcopy(accepted_edition)]
    record["integrity_sha256"] = _record_hash(record)
    record["delivery_authorization"] = authorize_accepted_edition(
        record,
        accepted_edition,
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason=(
            "Explicitly authorize delivery of this exact accepted edition."
        ),
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )
    record["integrity_sha256"] = _record_hash(record)
    return attach_approved_delivery_package(record, accepted_edition)


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
        controller=ComprehensiveApiController(_ReadOnlyService(record)),
    )
    install_same_run_locale_report(app)
    return app


def test_real_phase4_authorization_reaches_generic_and_localized_artifact_routes() -> None:
    record = _authorized_phase4_record()
    run_id = record["identity"]["run_id"]
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    expected_pdf = base64.b64decode(report["pdf_base64"], validate=True)
    expected_pdf_sha256 = hashlib.sha256(expected_pdf).hexdigest()

    assert "response_projection" not in record
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    assert validate_approved_delivery_package(
        record,
        record["approved_delivery_package"],
    )["status"] == "valid"

    controller = ComprehensiveApiController(_ReadOnlyService(record))
    status = controller.status_read_only(run_id)
    assert status["status"] == "approved"
    assert status["approval_status"] == "approved_final"
    assert status["delivery_status"] == "approved_for_delivery"
    assert status["client_delivery_allowed"] is True
    assert status["response_projection"][
        "terminal_report_package_integrity_valid"
    ] is True
    assert status["response_projection"][
        "delivery_authorization_integrity_valid"
    ] is True

    client = TestClient(_app(record))
    generic_json = client.get(
        f"/assessment/comprehensive-run/{run_id}/report/json"
    )
    generic_pdf = client.get(
        f"/assessment/comprehensive-run/{run_id}/report/pdf"
    )
    localized_json = client.get(
        f"/assessment/comprehensive-run/{run_id}/localized-report/en"
    )
    localized_pdf = client.get(
        f"/assessment/comprehensive-run/{run_id}/localized-report/en/pdf"
    )

    assert generic_json.status_code == 200
    assert generic_json.json() == report["json"]
    assert generic_json.headers["x-nico-approval-status"] == "approved_final"
    assert generic_json.headers["x-nico-client-delivery-allowed"] == "true"

    assert generic_pdf.status_code == 200
    assert generic_pdf.content == expected_pdf
    assert generic_pdf.headers["x-nico-pdf-sha256"] == expected_pdf_sha256
    assert generic_pdf.headers["x-nico-accepted-pdf-sha256"] == expected_pdf_sha256
    assert generic_pdf.headers["x-nico-client-delivery-allowed"] == "true"

    assert localized_json.status_code == 200
    localized_body = localized_json.json()
    assert localized_body["run_id"] == run_id
    assert localized_body["report_language"] == "en"
    assert localized_body["assessment_rerun"] is False
    assert localized_body["canonical_truth_sha256"] == report[
        "canonical_truth_sha256"
    ]
    assert localized_body["approval_status"] == "approved_final"
    assert localized_body["client_delivery_allowed"] is True

    assert localized_pdf.status_code == 200
    assert localized_pdf.content == expected_pdf
    assert localized_pdf.headers["x-nico-pdf-sha256"] == expected_pdf_sha256
    assert localized_pdf.headers["x-nico-approval-status"] == "approved_final"
    assert localized_pdf.headers["x-nico-client-delivery-allowed"] == "true"
