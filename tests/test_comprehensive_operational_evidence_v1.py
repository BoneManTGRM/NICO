from __future__ import annotations

import inspect

import pytest

from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
from nico.comprehensive_operational_evidence_v1 import (
    attach_canonical_deployment_population,
    deployment_population_from_context,
    format_deployment_classification,
    reconcile_deployment_population,
)


class _Renderer:
    @staticmethod
    def _stage(
        stage_id: str,
        title: str,
        summary: str,
        *,
        evidence: list[str] | None = None,
        findings: list[str] | None = None,
        unavailable: list[str] | None = None,
        status: str = "complete",
    ) -> dict:
        return {
            "stage_id": stage_id,
            "title": title,
            "summary": summary,
            "evidence": list(evidence or []),
            "findings": list(findings or []),
            "unavailable": list(unavailable or []),
            "status": status,
        }


def _context(**updates: object) -> dict:
    context = {
        "successful_runs": 76,
        "workflow_outcome_classes": {
            "success": 76,
            "failure": 19,
            "unknown": 5,
        },
        "jobs_observed": 38,
        "job_success_rate": 1.0,
        "deployments_observed": 10,
        "successful_deployments": 7,
    }
    context.update(updates)
    return context


def test_arithmetic_remainder_is_authoritative_when_classification_is_missing() -> None:
    population = reconcile_deployment_population(_context())

    assert population["deployments_observed"] == 10
    assert population["successful_deployments"] == 7
    assert population["non_success_or_unresolved_deployments"] == 3
    assert population["classification_status"] == "not_available"
    assert population["classification_breakdown"] == {}
    assert population["arithmetic_reconciliation"] == "10 - 7 = 3"
    assert population["score_effect"] == "none"


def test_stale_partial_legacy_value_never_replaces_arithmetic_remainder() -> None:
    population = reconcile_deployment_population(
        _context(non_success_deployments=1)
    )

    assert population["non_success_or_unresolved_deployments"] == 3
    assert population["classification_status"] == "not_available"
    assert any(
        "non_success_deployments:stale_or_partial" in error
        for error in population["validation_errors"]
    )


def test_complete_classification_is_exposed_only_when_it_reconciles() -> None:
    population = reconcile_deployment_population(
        _context(
            non_success_deployments=3,
            deployment_outcome_classes={
                "failed": 1,
                "cancelled": 1,
                "unknown": 1,
            },
        )
    )

    assert population["classification_status"] == "complete"
    assert population["classification_breakdown"] == {
        "cancelled": 1,
        "failed": 1,
        "unknown": 1,
    }
    assert format_deployment_classification(population) == (
        "Cancelled: 1; Failed: 1; Unknown: 1"
    )


def test_partial_classification_is_reported_unavailable_without_inventing_categories() -> None:
    population = reconcile_deployment_population(
        _context(deployment_outcome_classes={"failed": 1})
    )

    assert population["non_success_or_unresolved_deployments"] == 3
    assert population["classification_status"] == "not_available"
    assert population["classification_breakdown"] == {}
    assert format_deployment_classification(population) == "Not available"
    assert any(
        "classification_breakdown:does_not_reconcile" in error
        for error in population["validation_errors"]
    )


def test_successful_deployments_cannot_exceed_observed_population() -> None:
    with pytest.raises(
        ValueError,
        match="successful_deployments:exceeds_observed",
    ):
        reconcile_deployment_population(
            _context(deployments_observed=6, successful_deployments=7)
        )


def test_attached_population_is_verified_against_its_source_context() -> None:
    canonical = attach_canonical_deployment_population(
        {"ci_operational_context": _context(non_success_deployments=1)}
    )
    context = canonical["ci_operational_context"]

    assert context["non_success_or_unresolved_deployments"] == 3
    assert deployment_population_from_context(context)[
        "non_success_or_unresolved_deployments"
    ] == 3

    context["deployment_population"]["successful_deployments"] = 6
    with pytest.raises(ValueError, match="successful_deployments:canonical_mismatch"):
        deployment_population_from_context(context)


def test_unpatched_source_builder_renders_canonical_remainder_and_limitation() -> None:
    # Import-time compatibility installers wrap this function. Unwrapping it
    # exercises the source producer itself and prevents a late wrapper from
    # masking a regression in the canonical producer.
    source_builder = inspect.unwrap(cleanup.build_ci_operational_stage)
    canonical = attach_canonical_deployment_population(
        {"ci_operational_context": _context(non_success_deployments=1)}
    )

    stage = source_builder(canonical, _Renderer)

    assert stage is not None
    evidence = "\n".join(stage["evidence"])
    assert "Deployments: 7 successful of 10 observed (70%)." in evidence
    assert "Non-success or unresolved deployment observations: 3." in evidence
    assert "Outcome classification breakdown: Not available." in evidence
    assert "Non-success deployment classification:" not in evidence


def test_captured_source_callable_cannot_be_changed_by_later_module_patching() -> None:
    captured = inspect.unwrap(cleanup.build_ci_operational_stage)
    original_public = cleanup.build_ci_operational_stage
    cleanup.build_ci_operational_stage = lambda *_args, **_kwargs: None
    try:
        stage = captured(
            attach_canonical_deployment_population(
                {"ci_operational_context": _context()}
            ),
            _Renderer,
        )
    finally:
        cleanup.build_ci_operational_stage = original_public

    assert stage is not None
    assert "Non-success or unresolved deployment observations: 3." in "\n".join(
        stage["evidence"]
    )
