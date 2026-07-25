from __future__ import annotations

from nico.decision_grade_ci_reliability_v1 import (
    build_ci_reliability_evidence,
    classify_ci_run,
    wrap_report_builder_with_ci_reliability,
)


def test_success_is_included_in_reliability_denominator() -> None:
    result = classify_ci_run({"id": 1, "name": "NICO CI", "conclusion": "success"})
    assert result["classification"] == "success"
    assert result["reliability_denominator_included"] is True
    assert result["failure_numerator_included"] is False


def test_code_and_test_failures_are_distinguished_from_infrastructure() -> None:
    code = classify_ci_run({"conclusion": "failure", "failed_step": "Run pytest tests"})
    infra = classify_ci_run({"conclusion": "failure", "message": "Hosted runner lost network connection"})
    assert code["classification"] == "code_or_test_failure"
    assert infra["classification"] == "infrastructure_failure"
    assert code["failure_numerator_included"] is True
    assert infra["failure_numerator_included"] is True


def test_timeout_has_its_own_failure_class() -> None:
    result = classify_ci_run({"conclusion": "failure", "message": "Job timed out"})
    assert result["classification"] == "timeout"
    assert result["reliability_denominator_included"] is True


def test_expected_cancellation_is_excluded_without_becoming_failure() -> None:
    result = classify_ci_run({"conclusion": "cancelled", "superseded": True})
    assert result["classification"] == "cancelled_expected"
    assert result["reliability_denominator_included"] is False
    assert result["failure_numerator_included"] is False


def test_unclassified_cancellation_forces_review_limited_assurance() -> None:
    evidence = build_ci_reliability_evidence([{"conclusion": "cancelled", "name": "CI"}])
    assert evidence["status"] == "partial"
    assert evidence["assurance"] == "REVIEW LIMITED"
    assert evidence["unclassified_non_success_count"] == 1
    assert evidence["human_review_required"] is True


def test_reliability_math_uses_only_equivalent_classified_outcomes() -> None:
    evidence = build_ci_reliability_evidence([
        {"conclusion": "success", "name": "CI"},
        {"conclusion": "failure", "name": "CI", "failed_step": "pytest"},
        {"conclusion": "cancelled", "name": "CI", "superseded": True},
        {"conclusion": "skipped", "name": "Optional"},
    ])
    assert evidence["reliability_denominator"] == 2
    assert evidence["success_count"] == 1
    assert evidence["failure_count"] == 1
    assert evidence["success_rate_percent"] == 50.0
    assert evidence["failure_rate_percent"] == 50.0


def test_missing_requested_workflow_blocks_verified_assurance() -> None:
    evidence = build_ci_reliability_evidence(
        [{"conclusion": "success", "name": "Unit Tests"}],
        requested_workflows=["Unit Tests", "Security Audit"],
    )
    assert evidence["missing_requested_workflows"] == ["Security Audit"]
    assert evidence["status"] == "partial"


def test_wrapper_adds_evidence_to_result_package_and_canonical_json() -> None:
    def delegate(*args, **kwargs):
        return {"report_package": {"json": {}, "quality": {}}}

    wrapped = wrap_report_builder_with_ci_reliability(delegate)
    result = wrapped(stage_results={
        "ci_cd_reliability": {
            "workflow_runs": [{"id": "1", "name": "NICO CI", "conclusion": "success"}],
            "requested_workflows": ["NICO CI"],
            "coverage_window_days": 30,
        }
    })
    evidence = result["ci_reliability_evidence"]
    assert evidence["status"] == "complete"
    assert result["report_package"]["ci_reliability_evidence"] == evidence
    assert result["report_package"]["json"]["ci_reliability_evidence"] == evidence
    assert result["report_package"]["quality"]["ci_expected_cancellations_excluded"] is True


def test_wrapper_is_idempotent() -> None:
    def delegate(*args, **kwargs):
        return {}

    once = wrap_report_builder_with_ci_reliability(delegate)
    twice = wrap_report_builder_with_ci_reliability(once)
    assert once is twice
