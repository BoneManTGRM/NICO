from __future__ import annotations

from copy import deepcopy

import pytest

from nico.comprehensive_canonical_deployment_evidence_v1 import (
    VERSION,
    assert_deployment_population_reconciled,
    reconcile_deployment_populations,
)
from nico.comprehensive_report_truth_v53 import prepare_report_stage_results


FAILED_PRODUCTION_RUNS = (
    "comprun_2a332709a43f484580d9e961f4592b2f",
    "comprun_1215e435d09a45f1ad28aead1ea0089a",
    "comprun_114fe9ac91954833b7333a0e14bcb1a9",
)


def _stage(non_success: int | None) -> dict:
    return {
        "stage_id": "ci_cd_operational_readiness",
        "status": "complete",
        "ci_operational_context": {
            "deployments_observed": 10,
            "successful_deployments": 7,
            "non_success_deployments": non_success,
        },
        "evidence": [
            "CI/CD configuration maturity remains the immutable scored control.",
            "Deployments: 7 successful of 10 observed (70%).",
            (
                f"Non-success deployment classification: {non_success}."
                if non_success is not None
                else "Non-success deployment classification: Not available."
            ),
        ],
    }


@pytest.mark.parametrize("run_id", FAILED_PRODUCTION_RUNS)
@pytest.mark.parametrize("stale_non_success", [None, 1, 2])
def test_failed_live_populations_reconcile_before_render(
    run_id: str,
    stale_non_success: int | None,
) -> None:
    source = {
        "identity": {"run_id": run_id},
        "ci_cd_operational_readiness": _stage(stale_non_success),
    }

    result = reconcile_deployment_populations(source)
    stage = result["ci_cd_operational_readiness"]
    context = stage["ci_operational_context"]
    population = context["deployment_population"]

    assert population["artifact_schema"] == VERSION
    assert population["deployments_observed"] == 10
    assert population["successful_deployments"] == 7
    assert population["non_success_or_unresolved_deployments"] == 3
    assert population["arithmetic_remainder_verified"] is True
    assert population["outcome_classification_status"] == "not_available"
    assert context["non_success_deployments"] == 3
    assert context["non_success_or_unresolved_deployments"] == 3
    assert stage["evidence"][-4:] == [
        "Deployments observed: 10.",
        "Successful deployments: 7.",
        "Non-success or unresolved deployment observations: 3.",
        "Outcome classification breakdown: Not available.",
    ]
    assert not any(
        line.startswith("Non-success deployment classification:")
        for line in stage["evidence"]
    )
    assert_deployment_population_reconciled(result)


def test_complete_classification_is_exposed_only_when_it_reconciles() -> None:
    source = _stage(3)
    source["ci_operational_context"]["deployment_outcome_classes"] = {
        "failed": 1,
        "cancelled": 2,
        "success": 7,
    }

    result = reconcile_deployment_populations(source)
    context = result["ci_operational_context"]
    population = context["deployment_population"]

    assert population["outcome_classification_status"] == "complete"
    assert population["outcome_classification_breakdown"] == {
        "failed": 1,
        "cancelled": 2,
    }
    assert result["evidence"][-1] == (
        "Outcome classification breakdown: Cancelled: 2; Failed: 1."
    )
    assert_deployment_population_reconciled(result)


def test_incomplete_classification_is_retained_as_a_limitation_not_a_claim() -> None:
    source = _stage(1)
    source["ci_operational_context"]["deployment_outcome_classes"] = {
        "failed": 1,
        "success": 7,
    }

    result = reconcile_deployment_populations(source)
    context = result["ci_operational_context"]

    assert context["non_success_deployments"] == 3
    assert context["deployment_outcome_classification_complete"] is False
    assert context["deployment_outcome_classification"] is None
    assert context["deployment_outcome_classification_discrepancy"] == {
        "classified_non_success_total": 1,
        "arithmetic_non_success_or_unresolved_total": 3,
        "classification_used_for_client_claims": False,
    }
    assert result["evidence"][-1] == "Outcome classification breakdown: Not available."
    assert_deployment_population_reconciled(result)


def test_reconciliation_is_idempotent() -> None:
    once = reconcile_deployment_populations(_stage(1))
    twice = reconcile_deployment_populations(deepcopy(once))

    assert twice == once
    population = twice["ci_operational_context"]["deployment_population"]
    assert "deployment_population" not in population
    assert_deployment_population_reconciled(twice)


def test_success_count_cannot_exceed_observed_population() -> None:
    source = _stage(1)
    source["ci_operational_context"]["successful_deployments"] = 11

    with pytest.raises(
        ValueError,
        match="deployment_success_exceeds_observed_population",
    ):
        reconcile_deployment_populations(source)


def test_report_truth_pre_render_path_uses_canonical_population() -> None:
    source = {
        "ci_cd_operational_readiness": _stage(1),
    }

    result = prepare_report_stage_results(source)
    stage = result["ci_cd_operational_readiness"]
    context = stage["ci_operational_context"]

    assert context["deployments_observed"] == 10
    assert context["successful_deployments"] == 7
    assert context["non_success_or_unresolved_deployments"] == 3
    assert context["deployment_population"]["arithmetic_remainder_verified"] is True
    assert "Non-success or unresolved deployment observations: 3." in stage[
        "evidence"
    ]
    assert "Outcome classification breakdown: Not available." in stage["evidence"]
    assert_deployment_population_reconciled(result)
