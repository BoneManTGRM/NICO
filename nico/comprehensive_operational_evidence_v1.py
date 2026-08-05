from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive_operational_evidence.v1"
CANONICAL_KEY = "deployment_population"

_CLASSIFICATION_KEYS = (
    "deployment_outcome_classes",
    "deployment_outcome_classification",
    "deployment_classification",
    "non_success_deployment_classification",
)
_SUCCESS_CLASS_NAMES = {
    "success",
    "successful",
    "succeeded",
    "ready",
    "active",
}


def _nonnegative_int(value: Any, field: str, *, required: bool = False) -> int | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"deployment_population.{field}:required")
        return None
    if isinstance(value, bool):
        raise ValueError(f"deployment_population.{field}:invalid_integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"deployment_population.{field}:invalid_integer")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        if required:
            raise ValueError(f"deployment_population.{field}:invalid_integer") from exc
        return None
    if parsed < 0:
        raise ValueError(f"deployment_population.{field}:negative")
    return parsed


def _classification_source(context: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    for key in _CLASSIFICATION_KEYS:
        value = context.get(key)
        if isinstance(value, Mapping):
            return key, value
    return "", {}


def _normalize_breakdown(raw: Mapping[str, Any]) -> tuple[dict[str, int], list[str]]:
    breakdown: dict[str, int] = {}
    errors: list[str] = []
    for raw_name, raw_value in raw.items():
        name = str(raw_name or "").strip().casefold().replace(" ", "_")
        if not name:
            errors.append("empty_classification_name")
            continue
        if name in _SUCCESS_CLASS_NAMES:
            # The canonical breakdown covers the non-success remainder only.
            continue
        try:
            value = _nonnegative_int(
                raw_value,
                f"classification_breakdown.{name}",
                required=True,
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        assert value is not None
        breakdown[name] = value
    return dict(sorted(breakdown.items())), sorted(set(errors))


def reconcile_deployment_population(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return the one canonical deployment population for all report surfaces.

    Arithmetic population truth is authoritative. Detailed categories are exposed
    only when retained categories are complete and sum exactly to the arithmetic
    remainder. Stale or partial classifications are preserved as limitations and
    never replace the observed-minus-successful remainder.
    """

    observed = _nonnegative_int(context.get("deployments_observed"), "deployments_observed")
    successful = _nonnegative_int(
        context.get("successful_deployments"),
        "successful_deployments",
    )

    if observed is None:
        return {
            "artifact_schema": VERSION,
            "status": "not_available",
            "deployments_observed": None,
            "successful_deployments": successful,
            "non_success_or_unresolved_deployments": None,
            "classification_status": "not_available",
            "classification_breakdown": {},
            "classification_source": "",
            "validation_errors": [],
            "score_effect": "none",
        }
    if successful is None:
        return {
            "artifact_schema": VERSION,
            "status": "limited",
            "deployments_observed": observed,
            "successful_deployments": None,
            "non_success_or_unresolved_deployments": None,
            "classification_status": "not_available",
            "classification_breakdown": {},
            "classification_source": "",
            "validation_errors": ["successful_deployments:not_available"],
            "score_effect": "none",
        }
    if successful > observed:
        raise ValueError(
            "deployment_population.successful_deployments:exceeds_observed"
        )

    remainder = observed - successful
    source, raw_breakdown = _classification_source(context)
    breakdown, classification_errors = _normalize_breakdown(raw_breakdown)
    classification_total = sum(breakdown.values())

    legacy_non_success = _nonnegative_int(
        context.get("non_success_deployments"),
        "non_success_deployments",
    )
    legacy_matches = legacy_non_success is None or legacy_non_success == remainder
    complete_breakdown = (
        bool(source)
        and not classification_errors
        and classification_total == remainder
    )

    validation_errors = list(classification_errors)
    if legacy_non_success is not None and not legacy_matches:
        validation_errors.append(
            "non_success_deployments:stale_or_partial;"
            f"retained={legacy_non_success};arithmetic_remainder={remainder}"
        )
    if source and classification_total != remainder:
        validation_errors.append(
            "classification_breakdown:does_not_reconcile;"
            f"retained={classification_total};arithmetic_remainder={remainder}"
        )

    return {
        "artifact_schema": VERSION,
        "status": "complete" if complete_breakdown else "limited",
        "deployments_observed": observed,
        "successful_deployments": successful,
        "non_success_or_unresolved_deployments": remainder,
        "classification_status": "complete" if complete_breakdown else "not_available",
        "classification_breakdown": breakdown if complete_breakdown else {},
        "classification_source": source if complete_breakdown else "",
        "retained_legacy_non_success_deployments": legacy_non_success,
        "validation_errors": sorted(set(validation_errors)),
        "arithmetic_reconciliation": f"{observed} - {successful} = {remainder}",
        "score_effect": "none",
    }


def attach_canonical_deployment_population(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    context = (
        deepcopy(dict(result.get("ci_operational_context") or {}))
        if isinstance(result.get("ci_operational_context"), Mapping)
        else {}
    )
    if not context:
        return result

    population = reconcile_deployment_population(context)
    context[CANONICAL_KEY] = population
    # Preserve legacy keys for compatibility, but make the reconciled arithmetic
    # remainder explicit and authoritative for all new consumers.
    remainder = population.get("non_success_or_unresolved_deployments")
    if remainder is not None:
        context["non_success_or_unresolved_deployments"] = remainder
    result["ci_operational_context"] = context

    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "canonical_deployment_population_version": VERSION,
            "deployment_population_reconciled_at_canonical_producer": True,
            "deployment_remainder_uses_observed_minus_successful": True,
            "incomplete_classification_is_reported_unavailable": True,
            "deployment_history_has_no_technical_score_effect": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def deployment_population_from_context(context: Mapping[str, Any]) -> dict[str, Any]:
    embedded = context.get(CANONICAL_KEY)
    if isinstance(embedded, Mapping):
        expected = reconcile_deployment_population(context)
        for field in (
            "deployments_observed",
            "successful_deployments",
            "non_success_or_unresolved_deployments",
            "classification_status",
            "classification_breakdown",
        ):
            if embedded.get(field) != expected.get(field):
                raise ValueError(
                    f"deployment_population.{field}:canonical_mismatch"
                )
        return deepcopy(dict(embedded))
    return reconcile_deployment_population(context)


def format_deployment_classification(population: Mapping[str, Any]) -> str:
    if population.get("classification_status") != "complete":
        return "Not available"
    breakdown = population.get("classification_breakdown")
    if not isinstance(breakdown, Mapping) or not breakdown:
        return "Not available"
    return "; ".join(
        f"{str(name).replace('_', ' ').title()}: {int(value)}"
        for name, value in sorted(breakdown.items())
    )


__all__ = [
    "CANONICAL_KEY",
    "VERSION",
    "attach_canonical_deployment_population",
    "deployment_population_from_context",
    "format_deployment_classification",
    "reconcile_deployment_population",
]
