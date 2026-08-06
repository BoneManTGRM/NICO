from __future__ import annotations

from pathlib import Path

from nico.comprehensive_internal_capability_matrix_v2 import (
    QUALIFIED_MAIN_SHA,
    completion_state,
    current_capability_matrix,
    validate_current_capability_matrix,
)


def test_current_matrix_reconciles_all_forty_capabilities_to_qualified_main() -> None:
    validation = validate_current_capability_matrix()

    assert validation["status"] == "valid", validation["validation_errors"]
    assert validation["qualified_main_sha"] == QUALIFIED_MAIN_SHA
    assert validation["capability_count"] == 40
    assert len(set(validation["capability_ids"])) == 40
    assert validation["deployment_identity"]["provider_statuses"] == {
        "railway": "success",
        "vercel": "success",
    }
    assert validation["human_review_required"] is True
    assert validation["client_delivery_allowed"] is False


def test_every_mapped_source_path_is_classified_without_promoting_absent_work() -> None:
    root = Path(__file__).resolve().parents[1]

    for item in current_capability_matrix(root):
        source_paths = sorted(item["source_paths"])
        classified = sorted(
            item["existing_source_paths"] + item["missing_source_paths"]
        )
        assert source_paths == classified
        assert all((root / path).is_file() for path in item["existing_source_paths"])
        assert all(not (root / path).is_file() for path in item["missing_source_paths"])
        if item["missing_source_paths"]:
            assert item["current_status"] not in {
                "operational",
                "production_qualified_at_exact_sha",
            }


def test_repaired_operational_boundary_is_qualified_and_history_is_preserved() -> None:
    by_id = {
        item["capability_id"]: item
        for item in current_capability_matrix()
    }
    repaired = {
        "evidence_reconciliation",
        "operational_workflow_deployment_analysis",
        "canonical_json",
        "pdf_report",
        "html_report",
        "markdown_report",
        "browser_mobile_operation",
        "restart_recovery",
    }

    for capability_id in repaired:
        item = by_id[capability_id]
        assert item["implementation_state"] == "fully_present", capability_id
        assert item["current_status"] == "production_qualified_at_exact_sha"
        assert item["known_failures"] == []
        assert item["historical_status"] != item["current_status"]

    state = completion_state()
    assert state["historical_failure_record"]["defect_classification"] == (
        "path_divergence_and_evidence_contract_defect"
    )
    assert state["qualified_main"]["workflow_runs"] == {
        "Unified Production Acceptance": "21009616709",
        "Mobile Restart Production Proof": "21009616706",
        "iOS WebKit Paint Proof": "21009616704",
        "File list guard": "21009616705",
    }


def test_absent_package_three_through_five_modules_remain_dependency_pending() -> None:
    by_id = {
        item["capability_id"]: item
        for item in current_capability_matrix()
    }

    assert 1085 in by_id["functional_qa_evidence_intake"]["dependency_issues"]
    assert 1086 in by_id["candidate_review_disposition"]["dependency_issues"]
    assert 1087 in by_id["finding_review_disposition"]["dependency_issues"]

    for capability_id in (
        "functional_qa_evidence_intake",
        "candidate_review_disposition",
        "finding_review_disposition",
    ):
        assert by_id[capability_id]["missing_source_paths"]
        assert by_id[capability_id]["current_status"] in {
            "partially_present_dependency_pending",
            "dependency_package_pending",
        }
