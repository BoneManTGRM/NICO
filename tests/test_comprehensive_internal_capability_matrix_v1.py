from __future__ import annotations

from nico.comprehensive_internal_capability_matrix_v1 import (
    BASELINE_COMMIT,
    PRODUCTION_FAILURE_ROOT_CAUSE,
    capability_matrix,
    validate_capability_matrix,
)


def test_all_forty_internal_capabilities_are_mapped() -> None:
    matrix = capability_matrix()
    validation = validate_capability_matrix(matrix)

    assert validation["status"] == "valid", validation["validation_errors"]
    assert validation["capability_count"] == 40
    assert len(set(validation["capability_ids"])) == 40
    assert all(item["source_paths"] for item in matrix)
    assert all(item["entry_points"] for item in matrix)
    assert all(item["validators"] for item in matrix)
    assert all(item["tests"] for item in matrix)
    assert all(item["production_proofs"] for item in matrix)
    assert all(item["client_outputs"] for item in matrix)


def test_known_production_failures_share_one_exact_terminal_contract() -> None:
    root = PRODUCTION_FAILURE_ROOT_CAUSE

    assert root["baseline_commit"] == BASELINE_COMMIT
    assert set(root["affected_workflows"]) == {
        "Unified Production Acceptance",
        "iOS WebKit Paint Proof",
        "Mobile Restart Production Proof",
    }
    assert len(root["affected_run_ids"]) == 3
    assert root["terminal_stage"] == "final_comprehensive_report_generation"
    assert root["shared_reason"].endswith(
        "client report omitted the arithmetic deployment remainder"
    )
    assert root["defect_classification"] == (
        "path_divergence_and_evidence_contract_defect"
    )
    assert "canonical operational evidence producer" in root[
        "authoritative_repair_boundary"
    ]
    assert "late PDF" in root["prohibited_repair"]


def test_external_evidence_limitations_are_not_internal_failures() -> None:
    limited = {
        item["capability_id"]: item
        for item in capability_matrix()
        if item["external_evidence_dependencies"]
    }

    assert {
        "candidate_review_disposition",
        "finding_review_disposition",
        "functional_qa_evidence_intake",
        "platform_parity_evidence_intake",
        "historical_trend_evidence",
        "requirements_traceability",
        "stakeholder_alignment_evidence",
        "six_month_roadmap_framework",
        "staffing_cost_framework",
        "human_review_workflow",
        "exact_artifact_approval",
        "approved_delivery_packaging",
    }.issubset(limited)
    assert all(
        item["current_status"]
        not in {"blocked_by_known_code_defect", "operational_with_known_integration_failure"}
        for capability_id, item in limited.items()
        if capability_id
        not in {
            "candidate_review_disposition",
            "finding_review_disposition",
            "human_review_workflow",
            "exact_artifact_approval",
            "approved_delivery_packaging",
        }
    )
