import pytest
from nico.decision_grade_cost_engine_v1 import CostOfInactionInputs, apply_cost_of_inaction_inputs
from nico.decision_grade_report_view_v1 import _cost_text
from tests.test_decision_grade_cost_engine_v1 import _contract

@pytest.mark.parametrize("currency", ["USD", "usd", "UsD"])
@pytest.mark.parametrize("case", ["zero", "positive", "unknown"])
def test_typed_currency_case_preserves_calculated_report_facts(currency, case):
    original = _contract()
    before = original.model_dump(mode="json")
    estimate = ({"engineering_hours_low": 1, "engineering_hours_base": 2, "engineering_hours_high": 3}
                if case == "unknown" else dict(zip(
                    ["direct_cost_low", "direct_cost_base", "direct_cost_high"],
                    [0, 0, 0] if case == "zero" else [12.25, 25.5, 1000])))
    inputs = CostOfInactionInputs.model_validate(dict(mode="client_input", source="Requires review",
        assumptions=["Requires review"], currency=currency, default_estimate=estimate))
    input_before = inputs.model_dump(mode="json")
    adjusted, summary = apply_cost_of_inaction_inputs(original, inputs)
    saved = adjusted.model_dump(mode="json")
    cost = adjusted.findings[0].cost_of_inaction
    english = _cost_text(cost)
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    spanish = canonical._translate_presentation_field(english, "recommendation")
    if case == "unknown":
        assert cost.currency is None and cost.amount_base is None
        assert "No se calculó un total monetario" in spanish
        assert "1.0–3.0 horas" in spanish
        assert currency not in spanish
    else:
        assert cost.currency == currency
        for label, amount in zip(["bajo", "base", "alto"], [cost.amount_low,cost.amount_base,cost.amount_high]):
            assert f"{label} {currency} {amount:,.2f}" in spanish
        assert f"low {currency}" in english
    assert "durante 90 días" in spanish
    assert adjusted.model_dump(mode="json") == saved
    assert original.model_dump(mode="json") == before
    assert inputs.model_dump(mode="json") == input_before
    assert _cost_text(cost) == english

@pytest.mark.parametrize("currency", ["usd", "UsD", "US dollars", "ÜSD", "USD extra"])
def test_currency_case_does_not_admit_unsupported_prose(currency):
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    with pytest.raises(ValueError, match="missing Spanish presentation translation"):
        canonical._translate_presentation_field(
            f"low {currency} 0.00 over 90 days. The unsupported workflow requires mysterious external processing.", "recommendation")

@pytest.mark.parametrize("currency", ["US dollars", "ÜSD", "USD extra"])
def test_unsupported_currency_labels_are_not_added(currency):
    from nico.monetary_report_presentation import generated_cost_spanish
    assert generated_cost_spanish(f"low {currency} 0.00 over 90 days. Requires review") is None

def test_amount_label_projection_never_rewrites_currency_token():
    # Lexical grammar is not a currency registry; preserve tokens even at label collisions.
    from nico.monetary_report_presentation import generated_cost_spanish
    assert generated_cost_spanish("low low 0.00, high low 1.00 over 90 days. Requires review").startswith(
        "bajo low 0.00, alto low 1.00 durante 90 días.")
