from __future__ import annotations

from nico.post_release_hardening import (
    HardeningObservation,
    HardeningScenario,
    PerformanceBudget,
    evaluate_matrix,
    evaluate_observation,
)


def test_adverse_scenario_must_fail_closed() -> None:
    observation = HardeningObservation(
        scenario=HardeningScenario.PROVIDER_OUTAGE,
        exact_sha="a" * 40,
        status="complete",
        terminal=True,
        human_review_required=True,
        client_delivery_allowed=False,
    )
    verdict = evaluate_observation(observation, expected_sha="a" * 40)
    assert verdict.passed is False
    assert "hardening_adverse_scenario_must_fail_closed" in verdict.issues


def test_interrupted_run_requires_restart_and_idempotency_proof() -> None:
    observation = HardeningObservation(
        scenario=HardeningScenario.INTERRUPTED_RUN,
        exact_sha="a" * 40,
        status="interrupted",
        terminal=False,
        human_review_required=True,
        client_delivery_allowed=False,
        evidence={"restart_identity_preserved": True, "idempotent_continuation": False},
    )
    verdict = evaluate_observation(observation, expected_sha="a" * 40)
    assert "hardening_idempotent_continuation_required" in verdict.issues


def test_accessibility_requires_all_named_proof_families() -> None:
    observation = HardeningObservation(
        scenario=HardeningScenario.ACCESSIBILITY,
        exact_sha="a" * 40,
        status="passed",
        terminal=True,
        human_review_required=True,
        client_delivery_allowed=False,
        evidence={
            "keyboard": True,
            "screen_reader": True,
            "contrast": True,
            "reduced_motion": True,
            "semantic_headings": True,
            "focus_order": False,
        },
    )
    verdict = evaluate_observation(observation, expected_sha="a" * 40)
    assert verdict.passed is False
    assert "hardening_accessibility_missing:focus_order" in verdict.issues


def test_performance_budgets_are_enforced() -> None:
    observation = HardeningObservation(
        scenario=HardeningScenario.LARGE_REPOSITORY,
        exact_sha="a" * 40,
        status="passed",
        terminal=True,
        human_review_required=True,
        client_delivery_allowed=False,
        runtime_seconds=101,
        peak_memory_mb=500,
        artifact_bytes=2_000,
    )
    verdict = evaluate_observation(
        observation,
        expected_sha="a" * 40,
        budget=PerformanceBudget(100, 600, 3_000),
    )
    assert "hardening_runtime_budget_exceeded" in verdict.issues


def test_matrix_fails_when_any_required_scenario_is_missing() -> None:
    matrix = evaluate_matrix(
        [
            HardeningObservation(
                scenario=HardeningScenario.CLEAN,
                exact_sha="a" * 40,
                status="passed",
                terminal=True,
                human_review_required=True,
                client_delivery_allowed=False,
            )
        ],
        expected_sha="a" * 40,
    )
    assert matrix["status"] == "failed"
    assert "vulnerable" in matrix["missing_scenarios"]
    assert matrix["human_review_required"] is True
    assert matrix["client_delivery_allowed"] is False
