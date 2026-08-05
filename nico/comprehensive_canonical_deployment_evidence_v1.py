from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive_canonical_deployment_evidence.v1"

_OBSERVED_LINE = re.compile(r"^deployments\s+observed:\s*(\d+)\.?$", re.IGNORECASE)
_SUCCESS_LINE = re.compile(r"^successful\s+deployments:\s*(\d+|not\s+available)\.?$", re.IGNORECASE)
_RATIO_LINE = re.compile(
    r"^deployments:\s*(\d+)\s+successful\s+of\s+(\d+)\s+observed(?:\s*\([^)]*\))?\.?$",
    re.IGNORECASE,
)
_NON_SUCCESS_LINE = re.compile(
    r"^(?:non-success\s+deployments|non-success\s+or\s+unresolved\s+deployment\s+observations|non-success\s+deployment\s+classification):\s*(\d+|not\s+available)\.?$",
    re.IGNORECASE,
)
_BREAKDOWN_LINE = re.compile(
    r"^(?:outcome\s+classification\s+breakdown|detailed\s+outcome\s+classification):\s*.*$",
    re.IGNORECASE,
)

_BREAKDOWN_KEYS = (
    "deployment_outcome_classes",
    "deployment_outcome_classification",
    "deployment_classification_breakdown",
    "non_success_deployment_classes",
)
_SUCCESS_CLASS_NAMES = {
    "success",
    "successful",
    "succeeded",
}


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _line_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _evidence_population(values: list[Any]) -> tuple[int | None, int | None]:
    observed: int | None = None
    successful: int | None = None
    for raw in values:
        text = _line_text(raw)
        match = _OBSERVED_LINE.fullmatch(text)
        if match:
            observed = int(match.group(1))
            continue
        match = _SUCCESS_LINE.fullmatch(text)
        if match and not match.group(1).casefold().startswith("not"):
            successful = int(match.group(1))
            continue
        match = _RATIO_LINE.fullmatch(text)
        if match:
            successful = int(match.group(1))
            observed = int(match.group(2))
    return observed, successful


def _classification_mapping(context: Mapping[str, Any]) -> dict[str, int]:
    for key in _BREAKDOWN_KEYS:
        raw = context.get(key)
        if not isinstance(raw, Mapping):
            continue
        output: dict[str, int] = {}
        for name, value in raw.items():
            normalized = _line_text(name).casefold().replace(" ", "_")
            count = _integer(value)
            if not normalized or normalized in _SUCCESS_CLASS_NAMES or count is None or count < 0:
                continue
            output[normalized] = count
        if output:
            return output
    return {}


def _format_breakdown(values: Mapping[str, int]) -> str:
    return "; ".join(
        f"{name.replace('_', ' ').title()}: {values[name]}"
        for name in sorted(values)
    )


def _reconcile_context(
    context: Mapping[str, Any],
    *,
    evidence: list[Any] | None = None,
) -> dict[str, Any]:
    output = deepcopy(dict(context))
    observed = _integer(output.get("deployments_observed"))
    successful = _integer(output.get("successful_deployments"))
    if (observed is None or successful is None) and evidence:
        evidence_observed, evidence_successful = _evidence_population(evidence)
        if observed is None:
            observed = evidence_observed
        if successful is None:
            successful = evidence_successful

    if observed is None:
        return output
    if observed < 0:
        raise ValueError("deployment_observed_population_negative")
    if successful is not None and successful < 0:
        raise ValueError("deployment_success_population_negative")
    if successful is not None and successful > observed:
        raise ValueError("deployment_success_exceeds_observed_population")

    output["deployments_observed"] = observed
    breakdown = _classification_mapping(output)
    breakdown_total = sum(breakdown.values()) if breakdown else None

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
        output["successful_deployments"] = None
        output["non_success_deployments"] = None
        output["non_success_or_unresolved_deployments"] = None
        output["deployment_outcome_classification_complete"] = False
        output["deployment_population"] = population
        return output

    remainder = observed - successful
    population.update(
        {
            "successful_deployments": successful,
            "non_success_or_unresolved_deployments": remainder,
            "arithmetic_remainder_verified": True,
        }
    )
    output["successful_deployments"] = successful
    output["non_success_deployments"] = remainder
    output["non_success_or_unresolved_deployments"] = remainder

    if breakdown and breakdown_total == remainder:
        population["outcome_classification_status"] = "complete"
        population["outcome_classification_breakdown"] = deepcopy(breakdown)
        output["deployment_outcome_classification_complete"] = True
        output["deployment_outcome_classification"] = deepcopy(breakdown)
        output.pop("deployment_outcome_classification_discrepancy", None)
    else:
        output["deployment_outcome_classification_complete"] = False
        output["deployment_outcome_classification"] = None
        if breakdown:
            output["deployment_outcome_classification_discrepancy"] = {
                "classified_non_success_total": breakdown_total,
                "arithmetic_non_success_or_unresolved_total": remainder,
                "classification_used_for_client_claims": False,
            }

    output["deployment_population"] = population
    return output


def _is_deployment_line(value: Any) -> bool:
    text = _line_text(value)
    return bool(
        _OBSERVED_LINE.fullmatch(text)
        or _SUCCESS_LINE.fullmatch(text)
        or _RATIO_LINE.fullmatch(text)
        or _NON_SUCCESS_LINE.fullmatch(text)
        or _BREAKDOWN_LINE.fullmatch(text)
    )


def _canonical_evidence_lines(context: Mapping[str, Any]) -> list[str]:
    observed = _integer(context.get("deployments_observed"))
    successful = _integer(context.get("successful_deployments"))
    if observed is None:
        return []

    lines = [f"Deployments observed: {observed}."]
    if successful is None:
        lines.extend(
            [
                "Successful deployments: Not available.",
                "Non-success or unresolved deployment observations: Not available.",
                "Outcome classification breakdown: Not available.",
            ]
        )
        return lines

    remainder = observed - successful
    lines.extend(
        [
            f"Successful deployments: {successful}.",
            f"Non-success or unresolved deployment observations: {remainder}.",
        ]
    )
    population = (
        context.get("deployment_population")
        if isinstance(context.get("deployment_population"), Mapping)
        else {}
    )
    breakdown = population.get("outcome_classification_breakdown")
    if population.get("outcome_classification_status") == "complete" and isinstance(
        breakdown, Mapping
    ):
        lines.append(f"Outcome classification breakdown: {_format_breakdown(breakdown)}.")
    else:
        lines.append("Outcome classification breakdown: Not available.")
    return lines


def _reconcile_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    output = {
        key: reconcile_deployment_populations(child)
        for key, child in value.items()
    }
    evidence = output.get("evidence") if isinstance(output.get("evidence"), list) else None

    context = output.get("ci_operational_context")
    if isinstance(context, Mapping):
        canonical_context = _reconcile_context(context, evidence=evidence)
        output["ci_operational_context"] = canonical_context
        if evidence is not None and canonical_context.get("deployments_observed") is not None:
            retained = [item for item in evidence if not _is_deployment_line(item)]
            retained.extend(_canonical_evidence_lines(canonical_context))
            output["evidence"] = retained
        return output

    has_population = (
        "deployments_observed" in output
        or "successful_deployments" in output
        or any(_is_deployment_line(item) for item in evidence or [])
    )
    if has_population:
        canonical_context = _reconcile_context(output, evidence=evidence)
        output.update(canonical_context)
        if evidence is not None and canonical_context.get("deployments_observed") is not None:
            retained = [item for item in evidence if not _is_deployment_line(item)]
            retained.extend(_canonical_evidence_lines(canonical_context))
            output["evidence"] = retained
    return output


def reconcile_deployment_populations(value: Any) -> Any:
    """Reconcile deployment populations before any report surface is rendered.

    The observed and successful populations are authoritative for the bounded
    arithmetic remainder. Detailed failure categories are exposed only when a
    retained category mapping fully reconciles to that remainder. Incomplete
    classification is an evidence limitation, not an internal publication error.
    """

    if isinstance(value, list):
        return [reconcile_deployment_populations(item) for item in value]
    if isinstance(value, Mapping):
        return _reconcile_mapping(value)
    return value


def assert_deployment_population_reconciled(value: Any) -> None:
    """Fail closed only for internally contradictory deployment populations."""

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
        remainder = _integer(population.get("non_success_or_unresolved_deployments"))
        if observed is not None and successful is not None:
            if remainder != observed - successful:
                raise ValueError("deployment_population_arithmetic_mismatch")
            if population.get("arithmetic_remainder_verified") is not True:
                raise ValueError("deployment_population_remainder_not_verified")
        breakdown = population.get("outcome_classification_breakdown")
        if population.get("outcome_classification_status") == "complete":
            if not isinstance(breakdown, Mapping):
                raise ValueError("deployment_classification_claim_missing_breakdown")
            if remainder is not None and sum(_integer(item) or 0 for item in breakdown.values()) != remainder:
                raise ValueError("deployment_classification_breakdown_mismatch")

    for child in value.values():
        assert_deployment_population_reconciled(child)


__all__ = [
    "VERSION",
    "assert_deployment_population_reconciled",
    "reconcile_deployment_populations",
]
