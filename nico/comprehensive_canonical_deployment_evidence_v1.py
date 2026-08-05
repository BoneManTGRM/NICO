from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive_canonical_deployment_evidence.v1"

_OBSERVED = re.compile(r"^deployments\s+observed:\s*(\d+)\.?$", re.I)
_SUCCESSFUL = re.compile(
    r"^successful\s+deployments:\s*(\d+|not\s+available)\.?$", re.I
)
_RATIO = re.compile(
    r"^deployments:\s*(\d+)\s+successful\s+of\s+(\d+)\s+observed"
    r"(?:\s*\([^)]*\))?\.?$",
    re.I,
)
_NON_SUCCESS = re.compile(
    r"^(?:non-success\s+deployments|"
    r"non-success\s+or\s+unresolved\s+deployment\s+observations|"
    r"non-success\s+deployment\s+classification):\s*"
    r"(?:\d+|not\s+available)\.?$",
    re.I,
)
_BREAKDOWN = re.compile(
    r"^(?:outcome\s+classification\s+breakdown|"
    r"detailed\s+outcome\s+classification):\s*.*$",
    re.I,
)
_BREAKDOWN_KEYS = (
    "deployment_outcome_classes",
    "deployment_outcome_classification",
    "deployment_classification_breakdown",
    "non_success_deployment_classes",
)
_SUCCESS_NAMES = {"success", "successful", "succeeded"}


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _population_from_evidence(values: list[Any]) -> tuple[int | None, int | None]:
    observed: int | None = None
    successful: int | None = None
    for raw in values:
        text = _text(raw)
        match = _OBSERVED.fullmatch(text)
        if match:
            observed = int(match.group(1))
            continue
        match = _SUCCESSFUL.fullmatch(text)
        if match and not match.group(1).casefold().startswith("not"):
            successful = int(match.group(1))
            continue
        match = _RATIO.fullmatch(text)
        if match:
            successful = int(match.group(1))
            observed = int(match.group(2))
    return observed, successful


def _breakdown(context: Mapping[str, Any]) -> dict[str, int]:
    for key in _BREAKDOWN_KEYS:
        raw = context.get(key)
        if not isinstance(raw, Mapping):
            continue
        result: dict[str, int] = {}
        for name, value in raw.items():
            normalized = _text(name).casefold().replace(" ", "_")
            count = _integer(value)
            if (
                not normalized
                or normalized in _SUCCESS_NAMES
                or count is None
                or count < 0
            ):
                continue
            result[normalized] = count
        if result:
            return result
    return {}


def _format_breakdown(values: Mapping[str, int]) -> str:
    return "; ".join(
        f"{name.replace('_', ' ').title()}: {values[name]}"
        for name in sorted(values)
    )


def _is_metric_line(value: Any) -> bool:
    text = _text(value)
    return bool(
        _OBSERVED.fullmatch(text)
        or _SUCCESSFUL.fullmatch(text)
        or _RATIO.fullmatch(text)
        or _NON_SUCCESS.fullmatch(text)
        or _BREAKDOWN.fullmatch(text)
    )


def _reconcile_context(
    context: Mapping[str, Any], evidence: list[Any] | None
) -> dict[str, Any]:
    result = deepcopy(dict(context))
    observed = _integer(result.get("deployments_observed"))
    successful = _integer(result.get("successful_deployments"))
    if evidence and (observed is None or successful is None):
        evidence_observed, evidence_successful = _population_from_evidence(evidence)
        observed = evidence_observed if observed is None else observed
        successful = evidence_successful if successful is None else successful

    if observed is None:
        return result
    if observed < 0:
        raise ValueError("deployment_observed_population_negative")
    if successful is not None and successful < 0:
        raise ValueError("deployment_success_population_negative")
    if successful is not None and successful > observed:
        raise ValueError("deployment_success_exceeds_observed_population")

    result["deployments_observed"] = observed
    result["successful_deployments"] = successful
    classification = _breakdown(result)

    population: dict[str, Any] = {
        "artifact_schema": VERSION,
        "deployments_observed": observed,
        "successful_deployments": successful,
        "non_success_or_unresolved_deployments": None,
        "arithmetic_remainder_verified": False,
        "outcome_classification_status": "not_available",
        "outcome_classification_breakdown": None,
        "source_fields_reconciled": True,
    }

    if successful is None:
        result["non_success_deployments"] = None
        result["non_success_or_unresolved_deployments"] = None
        result["deployment_outcome_classification_complete"] = False
        result["deployment_outcome_classification"] = None
        result["deployment_population"] = population
        return result

    remainder = observed - successful
    result["non_success_deployments"] = remainder
    result["non_success_or_unresolved_deployments"] = remainder
    population["non_success_or_unresolved_deployments"] = remainder
    population["arithmetic_remainder_verified"] = True

    classified_total = sum(classification.values()) if classification else None
    if classification and classified_total == remainder:
        population["outcome_classification_status"] = "complete"
        population["outcome_classification_breakdown"] = deepcopy(classification)
        result["deployment_outcome_classification_complete"] = True
        result["deployment_outcome_classification"] = deepcopy(classification)
        result.pop("deployment_outcome_classification_discrepancy", None)
    else:
        result["deployment_outcome_classification_complete"] = False
        result["deployment_outcome_classification"] = None
        if classification:
            result["deployment_outcome_classification_discrepancy"] = {
                "classified_non_success_total": classified_total,
                "arithmetic_non_success_or_unresolved_total": remainder,
                "classification_used_for_client_claims": False,
            }

    result["deployment_population"] = population
    return result


def _evidence_lines(context: Mapping[str, Any]) -> list[str]:
    observed = _integer(context.get("deployments_observed"))
    successful = _integer(context.get("successful_deployments"))
    if observed is None:
        return []

    lines = [f"Deployments observed: {observed}."]
    if successful is None:
        return lines + [
            "Successful deployments: Not available.",
            "Non-success or unresolved deployment observations: Not available.",
            "Outcome classification breakdown: Not available.",
        ]

    remainder = observed - successful
    lines.extend(
        [
            f"Successful deployments: {successful}.",
            f"Non-success or unresolved deployment observations: {remainder}.",
        ]
    )
    population = context.get("deployment_population")
    breakdown = (
        population.get("outcome_classification_breakdown")
        if isinstance(population, Mapping)
        else None
    )
    if (
        isinstance(population, Mapping)
        and population.get("outcome_classification_status") == "complete"
        and isinstance(breakdown, Mapping)
    ):
        lines.append(f"Outcome classification breakdown: {_format_breakdown(breakdown)}.")
    else:
        lines.append("Outcome classification breakdown: Not available.")
    return lines


def _already_canonical(value: Mapping[str, Any]) -> bool:
    return (
        value.get("artifact_schema") == VERSION
        and value.get("source_fields_reconciled") is True
        and "deployments_observed" in value
        and "arithmetic_remainder_verified" in value
    )


def _reconcile_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if _already_canonical(value):
        return deepcopy(dict(value))

    result = {
        key: reconcile_deployment_populations(child)
        for key, child in value.items()
    }
    evidence = result.get("evidence")
    evidence_list = evidence if isinstance(evidence, list) else None

    nested_context = result.get("ci_operational_context")
    if isinstance(nested_context, Mapping):
        context = _reconcile_context(nested_context, evidence_list)
        result["ci_operational_context"] = context
    else:
        contains_population = (
            "deployments_observed" in result
            or "successful_deployments" in result
            or any(_is_metric_line(item) for item in evidence_list or [])
        )
        if not contains_population:
            return result
        context = _reconcile_context(result, evidence_list)
        result.update(context)

    if evidence_list is not None and context.get("deployments_observed") is not None:
        retained = [item for item in evidence_list if not _is_metric_line(item)]
        retained.extend(_evidence_lines(context))
        result["evidence"] = retained
    return result


def reconcile_deployment_populations(value: Any) -> Any:
    """Create one bounded deployment population before report rendering.

    Observed minus successful is the authoritative non-success-or-unresolved
    remainder. Detailed outcome categories are client-facing only when a retained
    category mapping reconciles exactly. Missing classification is an evidence
    limitation rather than an internal report-generation failure.
    """

    if isinstance(value, list):
        return [reconcile_deployment_populations(item) for item in value]
    if isinstance(value, Mapping):
        return _reconcile_mapping(value)
    return value


def assert_deployment_population_reconciled(value: Any) -> None:
    """Reject contradictory arithmetic, while allowing unavailable classification."""

    if isinstance(value, list):
        for item in value:
            assert_deployment_population_reconciled(item)
        return
    if not isinstance(value, Mapping):
        return

    population = value.get("deployment_population")
    if isinstance(population, Mapping):
        observed = _integer(population.get("deployments_observed"))
        successful = _integer(population.get("successful_deployments"))
        remainder = _integer(
            population.get("non_success_or_unresolved_deployments")
        )
        if observed is not None and successful is not None:
            if remainder != observed - successful:
                raise ValueError("deployment_population_arithmetic_mismatch")
            if population.get("arithmetic_remainder_verified") is not True:
                raise ValueError("deployment_population_remainder_not_verified")
        breakdown = population.get("outcome_classification_breakdown")
        if population.get("outcome_classification_status") == "complete":
            if not isinstance(breakdown, Mapping):
                raise ValueError("deployment_classification_claim_missing_breakdown")
            if remainder is not None and sum(
                _integer(item) or 0 for item in breakdown.values()
            ) != remainder:
                raise ValueError("deployment_classification_breakdown_mismatch")

    for child in value.values():
        assert_deployment_population_reconciled(child)


__all__ = [
    "VERSION",
    "assert_deployment_population_reconciled",
    "reconcile_deployment_populations",
]
