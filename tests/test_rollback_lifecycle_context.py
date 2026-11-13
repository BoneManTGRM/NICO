"""Exact generated rollback guidance is evidence, never delivery authority."""
import base64
from copy import deepcopy
import io

import pytest
from reportlab.pdfgen import canvas
from nico import comprehensive_approved_lifecycle_consistency_v1 as lifecycle

GUIDANCE = ('Revert the isolated remediation change if targeted or full verification fails; '
            'retain the failed evidence and keep client delivery blocked.')


def pdf(text):
    buf = io.BytesIO()
    page = canvas.Canvas(buf, invariant=1)
    obj = page.beginText(42, 740)
    # Explicit wrapping exercises extracted PDF whitespace without clipping.
    for line in text.replace('; ', ';\n').splitlines():
        obj.textLine(line)
    page.drawText(obj)
    page.save()
    return base64.b64encode(buf.getvalue()).decode()


def package():
    return {'json': {'canonical_findings': [{'rollback': GUIDANCE}],
                     'client_delivery_allowed': False},
            'markdown': '- Rollback: ' + GUIDANCE,
            'html': '<p>Rollback: ' + GUIDANCE + '</p>',
            'pdf_base64': pdf('Rollback\n' + GUIDANCE)}


def test_exact_generated_guidance_all_surfaces_preserved():
    value = package()
    before = deepcopy(value)
    lifecycle.assert_approved_lifecycle_consistency(value)
    assert value == before


@pytest.mark.parametrize('surface', ['json', 'markdown', 'html', 'pdf'])
@pytest.mark.parametrize('contradiction', [
    'client delivery blocked', 'pending human approval', 'Decision: pending',
    GUIDANCE + ' Current state: client delivery blocked.',
    GUIDANCE.replace('if targeted or full verification fails', 'even when verification succeeds'),
])
def test_real_or_mixed_current_state_still_rejected(surface, contradiction):
    value = package()
    if surface == 'json':
        value['json']['approval_record'] = {'status_text': contradiction}
    elif surface == 'pdf':
        value['pdf_base64'] = pdf('Rollback\n' + GUIDANCE + '\n' + contradiction)
    else:
        value[surface] += '\n' + contradiction
    before = deepcopy(value)
    with pytest.raises(ValueError, match='lifecycle_inconsistent:' + surface):
        lifecycle.assert_approved_lifecycle_consistency(value)
    assert value == before


@pytest.mark.parametrize('kind', ['unbound', 'wrong_field', 'mixed_rollback', 'forbidden_key'])
def test_no_arbitrary_field_or_unbound_prose_exemption(kind):
    value = package()
    if kind == 'unbound':
        value['json'] = {'identity': 'synthetic'}
        surface = 'markdown'
    elif kind == 'wrong_field':
        value['json'] = {'approval_record': {'status_text': GUIDANCE}}
        surface = 'json'
    elif kind == 'mixed_rollback':
        value['json']['canonical_findings'][0]['rollback'] += ' Current state: client delivery blocked.'
        surface = 'json'
    else:
        value['json']['client delivery blocked'] = 1
        surface = 'json'
    with pytest.raises(ValueError, match='lifecycle_inconsistent:' + surface):
        lifecycle.assert_approved_lifecycle_consistency(value)
