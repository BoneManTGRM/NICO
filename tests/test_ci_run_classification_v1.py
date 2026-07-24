from __future__ import annotations

from copy import deepcopy

from nico.ci_run_classification_v1 import (
    classify_ci_runs,
    reconcile_assessment_ci_classification,
)


SNAPSHOT_SHA = "a" * 40


def _run(
    run_id: int,
    conclusion: str,
    *,
    name: str = "NICO CI",
    head_sha: str = SNAPSHOT_SHA,
    reason: str = "",
) -> dict:
    return {
        "id": run_id,
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "head_sha": head_sha,
        "reason": reason,
        "created_at": "2026-07-24T12:00:00Z",
        "updated_at": "2026-07-24T12:10:00Z",
    }


def _assessment() -> dict:
    return {
        "maturity_signal": {"score": 85, "source_score": 85, "presented_score": 85},
        "sections": [
            {
                "id": "code_audit",
                "presented_score": 86,
                "score_value": 86,
                "exclude_from_maturity": False,
            },
            {
                "id": "ci_cd",
                "presented_score": 71,
                "score_value": 71,
                "findings": ["Raw non-success count was previously unclassified."],
                "unavailable": [],
                "exclude_from_maturity": False,
            },
        ],
        "findings_register": [
            {
                "id": "ci-historical-non-success",
                "category": "ci_cd",
                "title": "Historical non-success runs",
            }
        ],
    }


def test_expected_cancellation_is_excluded_from_release_reliability_denominator() -> None:
    result = classify_ci_runs(
        [
            _run(1, "success"),
            _run(2, "cancelled", reason="Superseded by newer run due to concurrency"),
            _run(3, "failure", name="NICO CI test failure"),
        ],
        snapshot_sha=SNAPSHOT_SHA,
    )

    assert result["successful_runs"] == 1
    assert result["expected_or_informational_non_success_runs"] == 1
    assert result["actionable_non_success_runs"] == 1
    assert result["unclassified_non_success_runs"] == 0
    assert result["release_reliability_denominator"] == 2
    assert result["classified_release_success_rate"] == 0.5
    assert result["exact_sha_release_success_rate"] == 0.5
    cancelled = next(item for item in result["ledger"] if item["run_id"] == "2")
    assert cancelled["classification"] == "expected_cancellation"
    assert cancelled["requires_human_cause_review"] is False


def test_unknown_failure_remains_unclassified_and_review_limited() -> None:
    result = classify_ci_runs(
        [_run(1, "success"), _run(2, "failure", name="Unknown workflow")],
        snapshot_sha=SNAPSHOT_SHA,
    )

    assert result["status"] == "review_limited"
    assert result["classification_complete"] is False
    assert result["unclassified_non_success_runs"] == 1
    unknown = next(item for item in result["ledger"] if item["run_id"] == "2")
    assert unknown["classification"] == "unclassified_failure"
    assert unknown["classification_confidence"] == "low"
    assert unknown["requires_human_cause_review"] is True


def test_infrastructure_and_code_failures_are_separated_from_each_other() -> None:
    result = classify_ci_runs(
        [
            _run(1, "failure", name="Install hosted scanner binaries"),
            _run(2, "failure", name="Run pytest test suite"),
        ],
        snapshot_sha=SNAPSHOT_SHA,
    )

    classes = {item["run_id"]: item["classification"] for item in result["ledger"]}
    assert classes == {"1": "infrastructure_failure", "2": "code_or_test_failure"}
    assert result["actionable_non_success_runs"] == 2
    assert result["unclassified_non_success_runs"] == 0


def test_reconciliation_replaces_raw_ci_penalty_with_classified_evidence() -> None:
    classification = classify_ci_runs(
        [
            _run(1, "success"),
            _run(2, "cancelled", reason="Superseded by newer run due to concurrency"),
            _run(3, "failure", name="Run pytest test suite"),
        ],
        snapshot_sha=SNAPSHOT_SHA,
    )
    workflow = {
        "explicit_permissions_present": True,
        "ci_run_classification": classification,
    }
    reconciled = reconcile_assessment_ci_classification(deepcopy(_assessment()), workflow)
    ci = next(item for item in reconciled["sections"] if item["id"] == "ci_cd")

    assert ci["presented_score"] == 84
    assert ci["score_band_label"] == "STRONG"
    assert ci["assurance_label"] == "VERIFIED"
    assert any("Expected or informational" in item for item in ci["evidence"])
    assert ci["ci_run_classification"]["classification_complete"] is True
    assert "Every retained non-success run" in ci["verified_green_exit_criteria"]
    ids = {item["id"] for item in reconciled["findings_register"]}
    assert "ci-historical-non-success" not in ids
    assert "ci-actionable-non-success" in ids
    assert "ci-unclassified-non-success" not in ids


def test_unclassified_ci_cannot_receive_verified_assurance() -> None:
    classification = classify_ci_runs(
        [_run(1, "success"), _run(2, "failure", name="Unknown workflow")],
        snapshot_sha=SNAPSHOT_SHA,
    )
    reconciled = reconcile_assessment_ci_classification(
        _assessment(),
        {"explicit_permissions_present": True, "ci_run_classification": classification},
    )
    ci = next(item for item in reconciled["sections"] if item["id"] == "ci_cd")

    assert ci["assurance_label"] == "REVIEW LIMITED"
    assert ci["unavailable"]
    assert "ci-unclassified-non-success" in {item["id"] for item in reconciled["findings_register"]}
