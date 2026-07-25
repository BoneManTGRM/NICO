from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Literal

from pydantic import Field, model_validator

from nico.decision_grade_contract_v1 import (
    Assumption,
    ContractModel,
    CostOfInaction,
    DecisionGradeContract,
    Finding,
    Priority,
    ReadinessStatus,
    ValidationIssue,
)

VERSION = "nico.decision_grade_cost_engine.v1"
_MARKER = "__nico_decision_grade_cost_engine_v1__"


class ExposureRange(ContractModel):
    engineering_hours_low: float | None = Field(default=None, ge=0)
    engineering_hours_base: float | None = Field(default=None, ge=0)
    engineering_hours_high: float | None = Field(default=None, ge=0)
    direct_cost_low: float | None = Field(default=None, ge=0)
    direct_cost_base: float | None = Field(default=None, ge=0)
    direct_cost_high: float | None = Field(default=None, ge=0)
    release_delay_days_low: float | None = Field(default=None, ge=0)
    release_delay_days_base: float | None = Field(default=None, ge=0)
    release_delay_days_high: float | None = Field(default=None, ge=0)
    assumptions: list[str] = Field(default_factory=list)
    confidence: str = "moderate"

    @model_validator(mode="after")
    def validate_ranges(self) -> "ExposureRange":
        groups = (
            ("engineering_hours", self.engineering_hours_low, self.engineering_hours_base, self.engineering_hours_high),
            ("direct_cost", self.direct_cost_low, self.direct_cost_base, self.direct_cost_high),
            ("release_delay_days", self.release_delay_days_low, self.release_delay_days_base, self.release_delay_days_high),
        )
        if not any(value is not None for _, *values in groups for value in values):
            raise ValueError("exposure estimate requires at least one numeric input")
        for label, low, base, high in groups:
            values = [value for value in (low, base, high) if value is not None]
            if not values:
                continue
            if low is not None and base is not None and base < low:
                raise ValueError(f"{label}_base must be greater than or equal to {label}_low")
            if base is not None and high is not None and high < base:
                raise ValueError(f"{label}_high must be greater than or equal to {label}_base")
            if low is not None and high is not None and high < low:
                raise ValueError(f"{label}_high must be greater than or equal to {label}_low")
        return self


class CostOfInactionInputs(ContractModel):
    mode: Literal["client_input", "scenario", "qualitative"] = "qualitative"
    timeframe_days: int = Field(default=90, ge=1, le=3650)
    currency: str | None = None
    blended_engineering_cost_per_hour: float | None = Field(default=None, ge=0)
    release_delay_cost_per_day: float | None = Field(default=None, ge=0)
    source: str = "system_default"
    assumptions: list[str] = Field(default_factory=list)
    scenario_profile: Literal["conservative", "balanced", "stress"] = "balanced"
    finding_estimates: dict[str, ExposureRange] = Field(default_factory=dict)
    category_estimates: dict[str, ExposureRange] = Field(default_factory=dict)
    default_estimate: ExposureRange | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> "CostOfInactionInputs":
        estimates = [*self.finding_estimates.values(), *self.category_estimates.values()]
        if self.default_estimate is not None:
            estimates.append(self.default_estimate)
        has_direct_cost = any(
            value is not None
            for estimate in estimates
            for value in (estimate.direct_cost_low, estimate.direct_cost_base, estimate.direct_cost_high)
        )
        has_monetary_input = bool(
            self.blended_engineering_cost_per_hour is not None
            or self.release_delay_cost_per_day is not None
            or has_direct_cost
        )
        if has_monetary_input and not self.currency:
            raise ValueError("monetary conversion inputs require a currency")
        if self.mode == "client_input":
            if not self.assumptions:
                raise ValueError("client-input estimates require disclosed assumptions")
            if not estimates:
                raise ValueError("client-input mode requires at least one finding, category, or default estimate")
            if not self.source or self.source == "system_default":
                raise ValueError("client-input mode requires a client-supplied source reference")
        if self.mode == "qualitative" and (estimates or has_monetary_input):
            raise ValueError("qualitative mode cannot contain quantitative inputs")
        return self


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _range_value(low: float | None, base: float | None, high: float | None) -> tuple[float, float, float]:
    low_value = float(low or 0)
    high_value = float(high if high is not None else (base if base is not None else low_value))
    base_value = float(base if base is not None else ((low_value + high_value) / 2))
    return low_value, base_value, high_value


def _scenario_hours(priority: Priority, profile: str, category: str) -> ExposureRange:
    base_ranges = {
        Priority.P0: (80.0, 160.0, 320.0),
        Priority.P1: (40.0, 80.0, 120.0),
        Priority.P2: (16.0, 32.0, 60.0),
        Priority.P3: (4.0, 12.0, 24.0),
    }
    profile_multiplier = {"conservative": 0.75, "balanced": 1.0, "stress": 1.5}[profile]
    category_multiplier = {
        "secret": 1.5,
        "dependency": 1.25,
        "ci_cd": 1.25,
        "architecture": 1.0,
        "static": 1.0,
        "code": 1.0,
        "evidence": 0.75,
    }.get(category, 1.0)
    low, base, high = base_ranges[priority]
    multiplier = profile_multiplier * category_multiplier
    return ExposureRange(
        engineering_hours_low=round(low * multiplier, 2),
        engineering_hours_base=round(base * multiplier, 2),
        engineering_hours_high=round(high * multiplier, 2),
        assumptions=[
            f"NICO {profile} planning profile applied to {priority.value} {category or 'technical'} work.",
            "Scenario hours are planning ranges, not observed client labor or a quoted implementation price.",
        ],
        confidence="low",
    )


def _select_estimate(inputs: CostOfInactionInputs, finding: Finding) -> ExposureRange | None:
    keys = [finding.finding_id]
    if finding.source_finding_id:
        keys.append(finding.source_finding_id)
    for key in keys:
        if key in inputs.finding_estimates:
            return inputs.finding_estimates[key]
    if finding.category in inputs.category_estimates:
        return inputs.category_estimates[finding.category]
    return inputs.default_estimate


def _input_description(estimate: ExposureRange, inputs: CostOfInactionInputs) -> str:
    hours = _range_value(
        estimate.engineering_hours_low,
        estimate.engineering_hours_base,
        estimate.engineering_hours_high,
    )
    direct = _range_value(estimate.direct_cost_low, estimate.direct_cost_base, estimate.direct_cost_high)
    delay = _range_value(
        estimate.release_delay_days_low,
        estimate.release_delay_days_base,
        estimate.release_delay_days_high,
    )
    return (
        f"Inputs: engineering hours low/base/high={hours[0]:g}/{hours[1]:g}/{hours[2]:g}; "
        f"direct cost low/base/high={direct[0]:g}/{direct[1]:g}/{direct[2]:g}; "
        f"release-delay days low/base/high={delay[0]:g}/{delay[1]:g}/{delay[2]:g}; "
        f"engineering rate={inputs.blended_engineering_cost_per_hour if inputs.blended_engineering_cost_per_hour is not None else 'not supplied'}; "
        f"release-delay cost/day={inputs.release_delay_cost_per_day if inputs.release_delay_cost_per_day is not None else 'not supplied'}."
    )


def _build_cost(
    *,
    finding: Finding,
    estimate: ExposureRange,
    inputs: CostOfInactionInputs,
) -> CostOfInaction:
    hours_low, hours_base, hours_high = _range_value(
        estimate.engineering_hours_low,
        estimate.engineering_hours_base,
        estimate.engineering_hours_high,
    )
    direct_low, direct_base, direct_high = _range_value(
        estimate.direct_cost_low,
        estimate.direct_cost_base,
        estimate.direct_cost_high,
    )
    delay_low, delay_base, delay_high = _range_value(
        estimate.release_delay_days_low,
        estimate.release_delay_days_base,
        estimate.release_delay_days_high,
    )
    hourly_rate = float(inputs.blended_engineering_cost_per_hour or 0)
    delay_rate = float(inputs.release_delay_cost_per_day or 0)
    monetary = bool(hourly_rate or delay_rate or direct_low or direct_base or direct_high)
    amounts = (
        direct_low + hours_low * hourly_rate + delay_low * delay_rate,
        direct_base + hours_base * hourly_rate + delay_base * delay_rate,
        direct_high + hours_high * hourly_rate + delay_high * delay_rate,
    )
    mode = "client_input" if inputs.mode == "client_input" else "scenario"
    formula = (
        "Formula: exposure = direct cost + engineering hours × blended engineering cost/hour "
        "+ release-delay days × release-delay cost/day."
    )
    assumptions = [*inputs.assumptions, *estimate.assumptions, formula]
    if not monetary:
        assumptions.append("Dollar conversion was not performed because no defensible monetary conversion rate was supplied.")
    rationale = (
        f"{finding.business_impact} {_input_description(estimate, inputs)} {formula} "
        f"Source: {inputs.source}."
    )
    return CostOfInaction(
        mode=mode,
        categories=list(finding.cost_of_inaction.categories),
        timeframe_days=inputs.timeframe_days,
        engineering_hours_low=_rounded(hours_low),
        engineering_hours_high=_rounded(hours_high),
        amount_low=_rounded(amounts[0]) if monetary else None,
        amount_base=_rounded(amounts[1]) if monetary else None,
        amount_high=_rounded(amounts[2]) if monetary else None,
        currency=inputs.currency if monetary else None,
        assumptions=assumptions,
        confidence=estimate.confidence,
        rationale=rationale,
    )


def _financial_assumptions(
    contract: DecisionGradeContract,
    inputs: CostOfInactionInputs,
    quantified_ids: list[str],
    unquantified_ids: list[str],
) -> list[Assumption]:
    retained = [item for item in contract.assumptions if item.category != "financial_exposure"]
    mode_label = "client-supplied" if inputs.mode == "client_input" else "scenario"
    retained.append(
        Assumption(
            assumption_id="ASM-FIN-ENGINE-001",
            category="financial_exposure",
            description=(
                f"Cost-of-inaction estimates use {mode_label} inputs from {inputs.source}; "
                "all low/base/high results follow the disclosed deterministic formula."
            ),
            source=inputs.source,
            user_supplied=inputs.mode == "client_input",
            confidence="high" if inputs.mode == "client_input" else "low",
            impacted_calculations=quantified_ids,
            sensitivity=(
                "Results change linearly with engineering rates, release-delay rates, direct-cost inputs, and exposure ranges."
            ),
            consequence_if_wrong=(
                "The financial or engineering-hour exposure must be recalculated; the underlying technical evidence and risk remain unchanged."
            ),
        )
    )
    if unquantified_ids:
        retained.append(
            Assumption(
                assumption_id="ASM-FIN-GAP-001",
                category="financial_exposure",
                description="No applicable quantitative input was supplied for some findings, so those findings remain qualitative.",
                source="system_boundary",
                user_supplied=False,
                confidence="high",
                impacted_calculations=unquantified_ids,
                sensitivity="Supplying finding-specific, category, or default ranges enables quantitative estimation.",
                consequence_if_wrong="No dollar amount is claimed for the affected findings; only the qualitative exposure classification remains.",
            )
        )
    return retained


def apply_cost_of_inaction_inputs(
    contract: DecisionGradeContract,
    raw_inputs: dict[str, Any] | CostOfInactionInputs | None,
) -> tuple[DecisionGradeContract, dict[str, Any]]:
    output = contract.model_copy(deep=True)
    if not raw_inputs:
        return output, {
            "schema_version": VERSION,
            "status": "qualitative_default",
            "mode": "qualitative",
            "quantified_finding_count": 0,
            "unquantified_finding_count": len(output.findings),
            "monetary_conversion_performed": False,
        }
    try:
        inputs = raw_inputs if isinstance(raw_inputs, CostOfInactionInputs) else CostOfInactionInputs.model_validate(raw_inputs)
    except Exception as exc:
        output.validation_issues.append(
            ValidationIssue(
                code="cost_of_inaction_inputs_invalid",
                severity="critical",
                message=f"Cost-of-inaction inputs are invalid and were not used: {type(exc).__name__}",
            )
        )
        output.readiness_status = ReadinessStatus.DELIVERY_BLOCKED
        return output, {
            "schema_version": VERSION,
            "status": "invalid",
            "mode": "unknown",
            "quantified_finding_count": 0,
            "unquantified_finding_count": len(output.findings),
            "monetary_conversion_performed": False,
            "error_type": type(exc).__name__,
        }
    if inputs.mode == "qualitative":
        return output, {
            "schema_version": VERSION,
            "status": "qualitative_requested",
            "mode": "qualitative",
            "quantified_finding_count": 0,
            "unquantified_finding_count": len(output.findings),
            "monetary_conversion_performed": False,
        }

    quantified: list[str] = []
    unquantified: list[str] = []
    monetary = False
    for finding in output.findings:
        estimate = _select_estimate(inputs, finding)
        if estimate is None and inputs.mode == "scenario":
            estimate = _scenario_hours(finding.priority, inputs.scenario_profile, finding.category)
        if estimate is None:
            unquantified.append(finding.finding_id)
            continue
        finding.cost_of_inaction = _build_cost(finding=finding, estimate=estimate, inputs=inputs)
        quantified.append(finding.finding_id)
        monetary = monetary or finding.cost_of_inaction.amount_base is not None

    output.assumptions = _financial_assumptions(output, inputs, quantified, unquantified)
    return output, {
        "schema_version": VERSION,
        "status": "complete",
        "mode": inputs.mode,
        "source": inputs.source,
        "timeframe_days": inputs.timeframe_days,
        "currency": inputs.currency,
        "scenario_profile": inputs.scenario_profile if inputs.mode == "scenario" else None,
        "quantified_finding_count": len(quantified),
        "unquantified_finding_count": len(unquantified),
        "quantified_finding_ids": quantified,
        "unquantified_finding_ids": unquantified,
        "monetary_conversion_performed": monetary,
        "unsupported_dollar_amount_generated": False,
    }


def wrap_contract_builder(delegate: Callable[..., DecisionGradeContract]) -> Callable[..., DecisionGradeContract]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> DecisionGradeContract:
        contract = delegate(*args, **kwargs)
        identity = kwargs.get("identity") if isinstance(kwargs.get("identity"), dict) else {}
        assessment = kwargs.get("assessment") if isinstance(kwargs.get("assessment"), dict) else {}
        raw_inputs = assessment.get("cost_of_inaction_inputs") or identity.get("cost_of_inaction_inputs")
        adjusted, summary = apply_cost_of_inaction_inputs(contract, raw_inputs)
        if isinstance(assessment, dict):
            assessment["cost_of_inaction_engine"] = deepcopy(summary)
        return adjusted

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_decision_grade_cost_engine(report_module: Any) -> dict[str, Any]:
    current = report_module.build_decision_grade_contract
    wrapped = wrap_contract_builder(current)
    report_module.build_decision_grade_contract = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": report_module.build_decision_grade_contract is wrapped,
        "client_input_mode_supported": True,
        "scenario_mode_supported": True,
        "qualitative_mode_supported": True,
        "unsupported_dollar_amount_generated": False,
    }


__all__ = [
    "VERSION",
    "ExposureRange",
    "CostOfInactionInputs",
    "apply_cost_of_inaction_inputs",
    "wrap_contract_builder",
    "install_decision_grade_cost_engine",
]
