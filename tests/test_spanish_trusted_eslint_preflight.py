"""Fresh diagnostic failure reproduced from synthetic retained scanner data."""
from copy import deepcopy
import hashlib
import json

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_spanish_publication_preflight_v93 import inspect_spanish_canonical_publication_preflight
from nico.trusted_global_eslint_v1 import PROJECT_DENIAL
from nico.v2_premium_report_renderer import _scanner_stages

REASON = ('Trusted global ESLint identity, source boundary or complete output could not be verified. '
          + PROJECT_DENIAL)
TRANSLATION = ('No se pudieron verificar la identidad de ESLint global de confianza, los límites de la fuente '
               'o la integridad de la salida. ESLint con conocimiento del proyecto sigue deshabilitado '
               'sin NICO_ALLOW_PROJECT_COMMANDS=true.')


def report(reason=REASON):
    return {'report_language': 'es-MX', 'scanner_execution_records': [{
        'tool': 'eslint', 'status': 'unavailable', 'completed': False,
        'failure_reason': reason, 'exact_commit_match': True, 'artifact_hash': 'a'*64,
        'findings': [], 'project_commands_executed': False,
    }], 'assessment': {'technical_score': 92, 'execution_score': 88},
        'canonical_findings': [{'finding_id': 'synthetic-preserved'}],
        'human_review_required': True, 'client_delivery_allowed': False}


def test_exact_trusted_eslint_reason_translates_and_preflight_matches_publication():
    from nico.comprehensive_spanish_exit_criteria_v88 import install_comprehensive_spanish_exit_criteria_v88
    install_comprehensive_spanish_exit_criteria_v88()
    value = report()
    before = deepcopy(value)
    digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    for prefix in ('', 'eslint: '):
        assert canonical._translate_presentation_field(prefix+REASON, 'unavailable') == prefix+TRANSLATION
    result = inspect_spanish_canonical_publication_preflight(value)
    assert result['status'] == 'complete', result
    assert result['checked_presentation_values'] > 0
    for stage in _scanner_stages(value):
        assert [canonical._translate_presentation_field(item, 'unavailable')
                for item in stage['unavailable']] == ['eslint: '+TRANSLATION]
    assert value == before
    assert hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() == digest
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False


def test_unknown_derived_scanner_reason_is_rejected_by_preflight_and_publication():
    value = report(REASON+' Future untranslated scanner claim requires human review before delivery.')
    before = deepcopy(value)
    result = inspect_spanish_canonical_publication_preflight(value)
    assert result['status'] == 'blocked', result
    assert any(item['field'] == 'unavailable' and 'derived_scanner_stages' in item['path']
               for item in result['failure_details'])
    with pytest.raises(ValueError, match='Spanish presentation'):
        canonical._translate_presentation_field(_scanner_stages(value)[0]['unavailable'][0], 'unavailable')
    assert value == before
