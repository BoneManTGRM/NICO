"""Synthetic ordinary-assessment regression controls for supplied zero values."""
from copy import deepcopy

import pytest

from nico.decision_grade_contract_v1 import ReadinessStatus
from nico.decision_grade_cost_engine_v1 import apply_cost_of_inaction_inputs
from nico.decision_grade_report_view_v1 import build_report_view
from test_decision_grade_cost_engine_v1 import _contract


MONETARY_FIELDS = (
    "blended_engineering_cost_per_hour",
    "release_delay_cost_per_day",
    "direct_cost_low",
    "direct_cost_base",
    "direct_cost_high",
)


def _inputs(field=None, *, mode="client_input"):
    inputs = {
        "mode": mode,
        "source": "Synthetic owned zero-value fixture",
        "currency": "USD",
        "assumptions": ["Synthetic estimate; not observed client data."],
        "default_estimate": {
            "engineering_hours_low": 1,
            "engineering_hours_base": 2,
            "engineering_hours_high": 3,
            "release_delay_days_low": 1,
            "release_delay_days_base": 2,
            "release_delay_days_high": 3,
        },
    }
    if field is not None:
        target = inputs["default_estimate"] if field.startswith("direct_cost_") else inputs
        target[field] = 0
    return inputs


@pytest.mark.parametrize("field", MONETARY_FIELDS)
def test_explicit_zero_is_preserved_as_monetary_evidence(field):
    source = _contract()
    before = source.model_dump()
    inputs = _inputs(field)
    original_inputs = deepcopy(inputs)
    output, summary = apply_cost_of_inaction_inputs(source, inputs)
    cost = output.findings[0].cost_of_inaction
    assert (cost.amount_low, cost.amount_base, cost.amount_high) == (0.0, 0.0, 0.0)
    assert cost.currency == "USD"
    assert cost.engineering_hours_low == 1
    assert cost.engineering_hours_high == 3
    assert summary["monetary_conversion_performed"] is True
    assert summary["quantified_finding_count"] == 1
    assert all("no defensible monetary conversion rate" not in value for value in cost.assumptions)
    assert output.readiness_status == source.readiness_status
    assert output.validation_issues == source.validation_issues
    view = build_report_view(output.model_dump(mode="json"))
    rendered_cost = view["findings_register"][0]["cost_of_inaction"]
    assert "low USD 0.00, base USD 0.00, high USD 0.00" in rendered_cost
    assert "No monetary total calculated" not in rendered_cost
    assert view["delivery_status"] == source.readiness_status.value
    assert "CLIENT DELIVERY NOT AUTHORIZED" in view["how_to_use"][-1]
    assert source.model_dump() == before
    assert inputs == original_inputs


@pytest.mark.parametrize("field", MONETARY_FIELDS[:2])
def test_zero_rate_with_generated_scenario_hours_preserves_zero_amounts(field):
    inputs = _inputs(field, mode="scenario")
    del inputs["default_estimate"]
    output, summary = apply_cost_of_inaction_inputs(_contract(), inputs)
    cost = output.findings[0].cost_of_inaction
    assert cost.mode == "scenario"
    assert cost.engineering_hours_low == 40
    assert cost.engineering_hours_high == 120
    assert (cost.amount_low, cost.amount_base, cost.amount_high) == (0.0, 0.0, 0.0)
    assert cost.currency == "USD"
    assert summary["monetary_conversion_performed"] is True


@pytest.mark.parametrize("missing", ["omitted", "null", "currency_only"])
def test_missing_monetary_evidence_still_cannot_generate_zero_amounts(missing):
    inputs = _inputs()
    if missing != "currency_only":
        del inputs["currency"]
    if missing == "null":
        inputs.update(blended_engineering_cost_per_hour=None, release_delay_cost_per_day=None)
        inputs["default_estimate"].update(direct_cost_low=None, direct_cost_base=None, direct_cost_high=None)
    output, summary = apply_cost_of_inaction_inputs(_contract(), inputs)
    cost = output.findings[0].cost_of_inaction
    assert (cost.amount_low, cost.amount_base, cost.amount_high, cost.currency) == (None, None, None, None)
    assert summary["monetary_conversion_performed"] is False
    assert any("no defensible monetary conversion rate" in value for value in cost.assumptions)
    view = build_report_view(output)
    assert "No monetary total calculated" in view["findings_register"][0]["cost_of_inaction"]


@pytest.mark.parametrize("field", MONETARY_FIELDS)
def test_zero_still_requires_currency_and_disclosed_assumptions(field):
    for omitted in ("currency", "assumptions"):
        inputs = _inputs(field)
        del inputs[omitted]
        output, summary = apply_cost_of_inaction_inputs(_contract(), inputs)
        assert summary["status"] == "invalid"
        assert output.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
        assert any(issue.code == "cost_of_inaction_inputs_invalid" for issue in output.validation_issues)
        cost = output.findings[0].cost_of_inaction
        assert (cost.amount_low, cost.amount_base, cost.amount_high) == (None, None, None)


def test_zero_direct_estimate_does_not_promote_other_findings_to_monetary():
    source = _contract(record_count=2)
    first, second = (finding.finding_id for finding in source.findings)
    inputs = _inputs()
    hours_only = inputs.pop("default_estimate")
    inputs["finding_estimates"] = {
        first: {"direct_cost_low": 0, "direct_cost_base": 0, "direct_cost_high": 0},
        second: hours_only,
    }
    output, summary = apply_cost_of_inaction_inputs(source, inputs)
    first_cost, second_cost = (finding.cost_of_inaction for finding in output.findings)
    assert (first_cost.amount_low, first_cost.amount_base, first_cost.amount_high) == (0.0, 0.0, 0.0)
    assert first_cost.currency == "USD"
    assert (second_cost.amount_low, second_cost.amount_base, second_cost.amount_high, second_cost.currency) == (None, None, None, None)
    assert summary["quantified_finding_count"] == 2
    assert summary["monetary_conversion_performed"] is True


def test_qualitative_mode_with_zero_inputs_remains_blocked():
    inputs = _inputs("direct_cost_base", mode="qualitative")
    output, summary = apply_cost_of_inaction_inputs(_contract(), inputs)
    assert summary["status"] == "invalid"
    assert output.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
