from __future__ import annotations

from copy import deepcopy

from nico import express_async_api as express
from nico import express_failure_stage_truth_v3 as truth


def _payload() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_test",
        "project_id": "project_test",
        "authorized": True,
        "authorization_confirmed": True,
    }


def test_terminal_failure_preserves_actual_stage_and_later_stages_remain_pending(monkeypatch) -> None:
    installed = truth.install_express_failure_stage_truth_v3()
    assert installed["actual_failure_stage_preserved"] is True
    assert installed["later_pending_stages_remain_pending"] is True

    run_id = "express_run_failure_stage_truth"
    payload = _payload()
    recorded = []
    monkeypatch.setattr(express, "_record", lambda *args, **kwargs: recorded.append(deepcopy(args)) or {})

    express._record_stage(
        run_id,
        payload,
        "repository_evidence",
        "Collecting exact-commit repository evidence.",
    )
    failure = express._response(
        run_id,
        payload,
        "failed",
        "Express assessment execution failed on the backend.",
        code="express_backend_execution_failed",
        stage="failed",
        progress_percent=100,
    )

    progress = {item["step"]: item for item in failure["progress"]}
    assert failure["failure_stage"] == "repository_evidence"
    assert failure["failure_ui_stage"] == "repository_evidence"
    assert failure["failure_code"] == "express_backend_execution_failed"
    assert failure["current_stage"] == "repository_evidence"
    assert progress["request_accepted"]["status"] == "complete"
    assert progress["repository_evidence"]["status"] == "failed"
    assert progress["repository_evidence"]["evidence"]["failure_stage"] == "repository_evidence"
    assert progress["repository_evidence"]["evidence"]["failure_code"] == "express_backend_execution_failed"
    assert progress["scanner_reconciliation"]["status"] == "pending"
    assert progress["truth_and_review_gates"]["status"] == "pending"
    assert progress["complete"]["status"] == "pending"

    truth._forget(run_id)


def test_backend_diagnostic_stage_maps_to_one_truthful_ui_failure() -> None:
    installed = truth.install_express_failure_stage_truth_v3()
    assert installed["backend_stage_mapped_to_ui_stage"] is True

    failure = express._response(
        "express_run_backend_stage_truth",
        _payload(),
        "failed",
        "Express report artifacts did not satisfy the final gate.",
        code="express_report_artifacts_missing",
        stage="failed",
        progress_percent=100,
        evidence={
            "failure_stage": "validate_final_artifacts",
            "diagnostic_id": "express_diag_test",
            "exception_class": "HTTPException",
        },
    )

    progress = {item["step"]: item for item in failure["progress"]}
    assert failure["failure_stage"] == "validate_final_artifacts"
    assert failure["failure_ui_stage"] == "truth_and_review_gates"
    assert failure["current_stage"] == "truth_and_review_gates"
    assert progress["report_generation"]["status"] == "complete"
    assert progress["truth_and_review_gates"]["status"] == "failed"
    assert progress["truth_and_review_gates"]["evidence"]["failure_stage"] == "validate_final_artifacts"
    assert progress["complete"]["status"] == "pending"
    assert sum(item["status"] == "failed" for item in progress.values()) == 1


def test_installation_is_idempotent_and_does_not_expose_raw_exception_details() -> None:
    first = truth.install_express_failure_stage_truth_v3()
    second = truth.install_express_failure_stage_truth_v3()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert second["safe_failure_code_exposed"] is True
    assert second["raw_exception_exposed"] is False
    assert second["human_review_required"] is True
    assert second["client_delivery_allowed"] is False
