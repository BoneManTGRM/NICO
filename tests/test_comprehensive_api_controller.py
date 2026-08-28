from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path

import pytest

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_capability_registry import execution_plan
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
                result["report_package"] = {
                    "report_id": f"report_{context['run_id']}",
                    "markdown": (
                        "# NICO Comprehensive Technical Assessment\n"
                        "CLIENT DELIVERY NOT AUTHORIZED"
                    ),
                    "html": (
                        "<html><body>NICO Comprehensive Technical Assessment</body></html>"
                    ),
                    "pdf_base64": base64.b64encode(
                        b"%PDF-1.4\n%%EOF\n"
                    ).decode("ascii"),
                    "pdf_page_count": 1,
                    "json": {"identity": identity},
                    "canonical_truth_sha256": "a" * 64,
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
    # continuation response is projected. In either case the browser response stays
    # bounded and never carries the full final artifact package.
    assert marker["status"] in {"running", "complete"}
    if marker["status"] == "running":
        assert marker["reason"] == "final_report_background_publication_in_progress"
    else:
        assert marker["response_bounded"] is True
        assert "report_package" not in marker
        assert "report_package" in marker.get("omitted_large_fields", [])
        assert marker["human_review_required"] is True
        assert marker["client_delivery_allowed"] is False

    response = _continue_to_review(controller, "comprun_api_001")
    assert response["status"] == "review_required"
    assert response["progress_percent"] == 100.0
    assert response["completed_stages"] == list(COMPREHENSIVE_STAGES)
    assert response["terminal"] is True
    assert response["reports"]["report_id"] == "report_comprun_api_001"
    assert response["reports"]["pdf_available"] is True
    assert response["reports"]["markdown_available"] is True
    assert response["reports"]["html_available"] is True
    assert response["reports"]["json_available"] is True
    for large_field in ("pdf_base64", "markdown", "html", "json"):
        assert large_field not in response["reports"]
    assert response["response_projection"]["terminal_report_artifacts_inlined"] is False
    assert response["response_projection"]["terminal_canonical_json_attached"] is False
    assert response["response_projection"]["exact_run_artifact_endpoints_required"] is True
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False

    # Browser projection is transport-only: immutable exact-run artifacts remain in
    # durable assessment truth for the dedicated report endpoints.
    durable = controller._service.load("comprun_api_001")
    final_stage = durable["stage_results"]["final_comprehensive_report_generation"]
    package = final_stage["report_package"]
    assert package["pdf_base64"].startswith("JVBER")
    assert package["markdown"].startswith("# NICO Comprehensive")
    assert package["json"]["identity"]["run_id"] == "comprun_api_001"
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False


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
