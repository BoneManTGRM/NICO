import pytest
from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
from nico.decision_grade_cost_engine_v1 import apply_cost_of_inaction_inputs
from nico.decision_grade_report_view_v1 import _cost_text
from tests.test_decision_grade_cost_engine_v1 import _contract

@pytest.mark.parametrize('case', ['zero','positive','unknown','qualitative'])
def test_actual_generated_cost_translation(case):
    contract = _contract()
    before = contract.model_dump(mode='json')
    if case == 'qualitative':
        adjusted = contract
    else:
        estimate = {'engineering_hours_low':1,'engineering_hours_base':2,'engineering_hours_high':3} if case == 'unknown' else {'direct_cost_low':0 if case == 'zero' else 100,'direct_cost_base':0 if case == 'zero' else 200,'direct_cost_high':0 if case == 'zero' else 300}
        adjusted, _ = apply_cost_of_inaction_inputs(contract, {'mode':'client_input','source':'Requires review','currency':'USD','assumptions':['Requires review'],'finding_estimates':{contract.findings[0].finding_id:estimate}})
    cost = adjusted.findings[0].cost_of_inaction
    saved = adjusted.model_dump(mode='json')
    english = _cost_text(cost)
    spanish = _translate_presentation_field(english, 'recommendation')
    if case == 'zero':
        assert 'bajo USD 0.00, base USD 0.00, alto USD 0.00' in spanish
    elif case == 'positive':
        assert 'bajo USD 100.00, base USD 200.00, alto USD 300.00' in spanish
    elif case == 'unknown':
        assert 'No se calculó un total monetario' in spanish
        assert 'USD 0.00' not in spanish
        assert '1.0–3.0 horas' in spanish
    else:
        assert 'Exposición cualitativa' in spanish
        assert 'USD' not in spanish
    assert 'durante 90 días' in spanish
    assert 'The unresolved condition' not in spanish
    assert adjusted.model_dump(mode='json') == saved
    assert contract.model_dump(mode='json') == before
    assert _cost_text(cost) == english

@pytest.mark.parametrize('text', [
 'low USD 0.00 over 90 days. The unsupported workflow requires mysterious external processing.',
 'Material qualitative exposure over 90 days. The unsupported workflow requires mysterious external processing.',
 'The unsupported workflow requires mysterious external processing.',
])
def test_unsupported_prose_still_fails(text):
    with pytest.raises(ValueError, match='missing Spanish presentation translation'):
        _translate_presentation_field(text, 'recommendation')

@pytest.mark.parametrize('hours', [1e16, 1e-7, 1.25e20, 2.5])
def test_generated_engineering_hours_are_localized_without_changing_values(hours):
    from nico.decision_grade_cost_engine_v1 import CostOfInactionInputs
    contract = _contract()
    before = contract.model_dump(mode='json')
    inputs = CostOfInactionInputs.model_validate({
        'mode': 'client_input', 'source': 'Requires review',
        'assumptions': ['Requires review'],
        'default_estimate': dict(engineering_hours_low=hours,
                                engineering_hours_base=hours,
                                engineering_hours_high=hours),
    })
    adjusted, summary = apply_cost_of_inaction_inputs(contract, inputs)
    assert summary['status'] == 'complete'
    saved = adjusted.model_dump(mode='json')
    cost = adjusted.findings[0].cost_of_inaction
    english = _cost_text(cost)
    # Resolve after production bootstrap so installed translator wrappers run.
    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    spanish = canonical._translate_presentation_field(english, 'recommendation')
    # Preserve the calculated tokens; the engine rounds tiny hours to two decimals.
    tokens = f'{cost.engineering_hours_low}–{cost.engineering_hours_high}'
    assert f'Exposición de ingeniería: {tokens} horas.' in spanish
    assert 'Engineering exposure:' not in spanish
    assert ' hours.' not in spanish
    assert 'No se calculó un total monetario' in spanish
    assert cost.amount_base is None and cost.currency is None
    assert adjusted.model_dump(mode='json') == saved
    assert contract.model_dump(mode='json') == before
    assert _cost_text(cost) == english
