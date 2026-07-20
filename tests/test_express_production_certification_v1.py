from __future__ import annotations

from copy import deepcopy

from nico.express_production_certification import build_express_production_certification


SHA = "a" * 40
FINGERPRINT = "b" * 64


def _complete_result() -> dict:
    return {
        "status": "complete",
        "commit_sha": SHA,
        "express_terminal_contract": {"status": "complete"},
        "deployment_identity": {
            "production_sha": SHA,
            "frontend_sha": SHA,
            "backend_sha": SHA,
        },
        "persistence_truth": {
            "restart_retrieval_verified": True,
            "durable_store_verified": True,
        },
        "express_cross_format_contract": {
            "status": "complete",
            "truth_fingerprint": FINGERPRINT,
        },
        "express_visual_qa": {"status": "pass"},
        "express_artifact_inspection": {
            "pdf_pages_inspected": True,
            "markdown_inspected": True,
            "html_inspected": True,
            "json_inspected": True,
            "safe_api_inspected": True,
            "reviewer_record_inspected": True,
            "progress_ui_inspected": True,
        },
    }


def test_set_1_requires_exact_immutable_snapshot_identity() -> None:
    result = _complete_result()
    result["commit_sha"] = "short"
    certification = build_express_production_certification(result, prior_runs=[])
    assert certification["status"] == "not_certified"
    assert "exact_snapshot_sha_present" in certification["missing_requirements"]


def test_set_2_requires_frontend_backend_and_production_sha_match() -> None:
    result = _complete_result()
    result["deployment_identity"]["backend_sha"] = "c" * 40
    certification = build_express_production_certification(result, prior_runs=[])
    assert certification["checks"]["frontend_deployment_sha_matches"] is True
    assert certification["checks"]["backend_deployment_sha_matches"] is False
    assert certification["status"] == "not_certified"


def test_set_3_requires_durable_restart_retrieval() -> None:
    result = _complete_result()
    result["persistence_truth"] = {"restart_retrieval_verified": False, "durable_store_verified": True}
    certification = build_express_production_certification(result, prior_runs=[])
    assert "restart_retrieval_verified" in certification["missing_requirements"]
    assert certification["client_delivery_allowed"] is False


def test_set_4_requires_two_completed_same_sha_matching_fingerprints() -> None:
    result = _complete_result()
    first = build_express_production_certification(deepcopy(result), prior_runs=[])
    assert "two_completed_same_sha_runs" in first["missing_requirements"]

    prior = deepcopy(result)
    prior["status"] = "complete"
    second = build_express_production_certification(result, prior_runs=[prior])
    assert second["checks"]["two_completed_same_sha_runs"] is True
    assert second["checks"]["two_run_truth_fingerprint_matches"] is True


def test_set_5_requires_full_artifact_and_ui_inspection() -> None:
    result = _complete_result()
    result["express_artifact_inspection"]["pdf_pages_inspected"] = False
    prior = deepcopy(_complete_result())
    certification = build_express_production_certification(result, prior_runs=[prior])
    assert "pdf_pages_inspected" in certification["missing_requirements"]
    assert certification["status"] == "not_certified"


def test_all_five_sets_produce_certified_pending_human_review() -> None:
    result = _complete_result()
    prior = deepcopy(result)
    certification = build_express_production_certification(result, prior_runs=[prior])
    assert certification["status"] == "certified_pending_human_review"
    assert certification["missing_requirements"] == []
    assert certification["human_review_required"] is True
    assert certification["client_delivery_allowed"] is False
