from __future__ import annotations

import base64
import hashlib
import sqlite3
import time
from pathlib import Path

import pytest

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _controller(path: Path) -> ComprehensiveApiController:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    executors = {}
    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            result = {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            for field in (
                "repository_provider",
                "provider_access_mode",
                "provider_credential_used",
            ):
                if field in context:
                    result[field] = context[field]
            if _capability == "final_report_generation":
                identity = {
                    key: context[key]
                    for key in (
                        "run_id",
                        "repository",
                        "commit_sha",
                        "evidence_ledger_id",
                    )
                }
                identity["report_language"] = "en"
                pdf = b"%PDF-1.4\n%%EOF\n"
                canonical = {
                    "report_language": "en",
                    "locale": "en",
                    "identity": identity,
                    "assessment": {
                        "report_language": "en",
                        "locale": "en",
                    },
                }
                result["report_package"] = {
                    "report_id": f"report_{context['run_id']}",
                    "report_language": "en",
                    "locale": "en",
                    "markdown": (
                        "# NICO Comprehensive Technical Assessment\n"
                        "CLIENT DELIVERY NOT AUTHORIZED"
                    ),
                    "html": (
                        "<html><body>NICO Comprehensive Technical Assessment</body></html>"
                    ),
                    "pdf_base64": base64.b64encode(pdf).decode("ascii"),
                    "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                    "pdf_page_count": 1,
                    "json": canonical,
                    "canonical_truth_sha256": canonical_sha256(canonical),
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            return result

        executors[capability] = execute
    return ComprehensiveApiController(ComprehensiveRunService(store, executors))


def _payload() -> dict:
    return {
        "run_id": "comprun_api_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "evidence_ledger_id": "ledger_api_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "authorized": True,
        "authorization_confirmed": True,
    }


def _continue_to_review(
    controller: ComprehensiveApiController,
    run_id: str,
    *,
    timeout: float = 4.0,
) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = controller.continue_run(run_id)
        if last.get("status") == "review_required":
            return last
        assert last.get("status") == "running"
        assert last.get("client_delivery_allowed") is False
        time.sleep(0.02)
    raise AssertionError(f"run did not reach human review before timeout: {last}")


def test_start_returns_canonical_two_service_identity(tmp_path: Path) -> None:
    response = _controller(tmp_path / "runs.db").start(_payload())

    assert response["service_id"] == "comprehensive"
    assert response["operation"] == "started"
    assert response["run_id"] == "comprun_api_001"
    assert response["repository"] == "BoneManTGRM/NICO"
    assert response["status"] == "ready"
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False
    assert "mid" not in response
    assert "full" not in response
    assert "deep" not in response


def test_start_requires_explicit_authorization(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    payload = _payload()
    payload["authorization_confirmed"] = False

    with pytest.raises(ValueError, match="explicit_authorization_required"):
        controller.start(payload)


def test_anonymous_provider_access_binding_survives_durable_stage_context(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path / "provider-access.db")
    payload = _payload()
    payload.update(
        {
            "repository_provider": "github",
            "provider_access_mode": "anonymous_public",
            "provider_credential_used": False,
        }
    )

    controller.start(payload)
    stored = controller._service.load_read_only(payload["run_id"])  # type: ignore[attr-defined]
    assert stored["repository_provider"] == "github"
    assert stored["provider_access_mode"] == "anonymous_public"
    assert stored["provider_credential_used"] is False

    controller.continue_run(payload["run_id"], {"max_stages": 1})
    continued = controller._service.load_read_only(payload["run_id"])  # type: ignore[attr-defined]
    stage = continued["stage_results"]["authorization_and_scope"]
    assert stage["repository_provider"] == "github"
    assert stage["provider_access_mode"] == "anonymous_public"
    assert stage["provider_credential_used"] is False


def test_status_returns_exact_persisted_run(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    started = controller.start(_payload())
    status = controller.status(started["run_id"])

    assert status["operation"] == "status"
    assert status["integrity_sha256"] == started["integrity_sha256"]
    assert status["revision"] == started["revision"]
    assert status["record"] == started["record"]


def test_continue_can_advance_bounded_number_of_stages(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "runs.db")
    controller.start(_payload())

    response = controller.continue_run("comprun_api_001", {"max_stages": 2})

    assert response["operation"] == "continued"
    assert response["completed_stages"] == list(COMPREHENSIVE_STAGES[:2])
    assert response["revision"] == 3
    assert response["terminal"] is False
    assert response["client_delivery_allowed"] is False


def test_continue_without_bound_stops_at_async_final_report_boundary_then_reaches_review(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path / "runs.db")
    controller.start(_payload())

    first = controller.continue_run("comprun_api_001")

    assert first["status"] == "running"
    assert first["terminal"] is False
    assert first["client_delivery_allowed"] is False
    marker = first["record"]["stage_results"]["final_comprehensive_report_generation"]
    # The final report is launched behind the durable background boundary. With a tiny
    # in-memory test executor the worker may legitimately finish before the first
    # continuation response is projected, so both the persisted running marker and an
    # already-published complete result are valid observations. Neither case may block
    # the request, approve the report, or authorize delivery.
    assert marker["status"] in {"running", "complete"}
    if marker["status"] == "running":
        assert marker["reason"] == "final_report_background_publication_in_progress"
    else:
        if "report_package" in marker:
            assert marker["report_package"]["report_id"] == "report_comprun_api_001"
        else:
            assert first["record"]["response_projection"][
                "report_payload_deferred_until_terminal"
            ] is True
        assert marker["human_review_required"] is True
        assert marker["client_delivery_allowed"] is False

    response = _continue_to_review(controller, "comprun_api_001")
    assert response["status"] == "review_required"
    assert response["progress_percent"] == 100.0
    assert response["completed_stages"] == list(COMPREHENSIVE_STAGES)
    assert response["terminal"] is True
    assert response["reports"]["report_id"] == "report_comprun_api_001"
    assert response["reports"]["pdf_base64"].startswith("JVBER")
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False


def test_request_validation_rejects_missing_identity_and_invalid_bounds(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path / "runs.db")
    payload = _payload()
    payload["commit_sha"] = ""

    with pytest.raises(ValueError, match="commit_sha_required"):
        controller.start(payload)

    controller.start(_payload())
    with pytest.raises(ValueError, match="max_stages_must_be_non_negative"):
        controller.continue_run("comprun_api_001", {"max_stages": -1})


def test_controller_projects_human_approval_separately_from_delivery_authorization(
    tmp_path: Path,
) -> None:
    from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition

    controller = _controller(tmp_path / "state-matrix.db")
    controller.start(_payload())
    _continue_to_review(controller, "comprun_api_001")
    record = controller._service.load_read_only("comprun_api_001")  # type: ignore[attr-defined]
    report = record["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    identity = report["json"]["identity"]
    identity["assessment_depth"] = record["identity"]["assessment_depth"]
    report["canonical_truth_sha256"] = canonical_sha256(report["json"])
    pdf = base64.b64decode(report["pdf_base64"], validate=True)
    accepted = build_accepted_report_edition(
        repository=identity["repository"],
        commit_sha=identity["commit_sha"],
        tree_sha="tree-api-controller-001",
        run_id=identity["run_id"],
        scanner_run_id="scanner-api-controller-001",
        evidence_bundle_hash="evidence-api-controller-001",
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
    record["status"] = "approved"
    record["terminal"] = True
    record["human_review_completed"] = True
    record["client_delivery_allowed"] = False
    record["accepted_edition"] = accepted
    record["review_decision"] = accepted
    record["review_history"] = [accepted]

    pending = controller._response(record, operation="status")
    assert pending["status"] == "approved"
    assert pending["human_review_completed"] is True
    assert pending["client_delivery_allowed"] is False
    assert pending["delivery_status"] == "pending_authorization"
    assert pending["record"]["delivery_status"] == "pending_authorization"

    record["client_delivery_allowed"] = True
    unauthorized_flag = controller._response(record, operation="status")
    assert unauthorized_flag["status"] == "approved"
    assert unauthorized_flag["approval_status"] == "approved_final"
    assert unauthorized_flag["human_review_completed"] is True
    assert unauthorized_flag["client_delivery_allowed"] is False
    assert unauthorized_flag["delivery_status"] == (
        "blocked_authorization_integrity"
    )
    assert unauthorized_flag["record"]["client_delivery_allowed"] is False
    assert unauthorized_flag["record"]["delivery_status"] == (
        "blocked_authorization_integrity"
    )
    assert unauthorized_flag["response_projection"][
        "delivery_authorization_invalidated"
    ] is True
