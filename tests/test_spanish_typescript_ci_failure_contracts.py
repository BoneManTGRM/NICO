"""Local consumer failures stay unavailable while their authored copy localizes."""
from copy import deepcopy
from dataclasses import asdict
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

from tests.test_spanish_retained_candidate_contracts import _isolated_preflight_test


@pytest.mark.parametrize('failure,reason,translated', [
    ('exception', 'Authenticated current-main CI TypeScript evidence is unavailable.',
     'La evidencia autenticada de TypeScript en CI para el commit actual de main no está disponible.'),
    ('invalid', 'Retained CI TypeScript evidence is incomplete or invalid.',
     'La evidencia conservada de TypeScript en CI está incompleta o no es válida.'),
    ('incomplete', 'Retained CI TypeScript capture did not complete.',
     'La captura conservada de TypeScript en CI no se completó.'),
])
@_isolated_preflight_test
def test_real_consumer_failure_localizes_without_granting_execution_credit(failure, reason, translated):
    from nico.api import final_report_worker_bootstrap  # noqa: F401
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    from nico import nico_ci_typescript_consumer_v1 as consumer
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.v2_assessment_pipeline import normalize_scanner_result
    from nico.phase17_canonical_artifact_rebuild_v1 import _populate_premium_stage_summaries
    from nico.comprehensive_spanish_canonical_report_v87 import _render_inputs

    install_spanish_publication_preflight_v93()
    spec = next(item for item in pipeline.TOOL_SPECS if item.name == 'typescript')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w'):
        pass
    capture = ({'side_effect': ValueError('PRIVATE owned fixture failure')}
               if failure == 'exception' else {'return_value': (
                   {'metadata_authenticated': failure != 'invalid', 'status': 'incomplete'},
                   archive.getvalue())})
    with tempfile.TemporaryDirectory() as temp, \
            patch.object(pipeline, '_git_text', return_value='a' * 40), \
            patch.object(consumer, '_capture_bounded', **capture), \
            patch.object(consumer.requests, 'get', side_effect=AssertionError('network forbidden')):
        payload = consumer.run(spec, SimpleNamespace(root=Path(temp)))
    assert payload['status'] == 'unavailable'
    assert payload['reason'] == reason
    assert payload['execution_observed_for_this_report'] is False
    assert payload['verified_for_this_report'] is False
    assert payload['findings'] == []
    original = deepcopy(payload)
    record = asdict(normalize_scanner_result(payload, 'a' * 40))
    record['state'] = record['state'].value
    assert record['completed'] is False
    package = {'json': {'report_language': 'es-MX',
        'identity': {'report_language': 'es-MX'}, 'assessment': {},
        'scanner_execution_records': [record]}}
    canonical = _populate_premium_stage_summaries(package)['json']
    _, assessment, stages, _ = _render_inputs(canonical)
    for collection in (assessment['stage_summaries'], stages):
        stage = next(item for item in collection
                     if item['stage_id'] == 'dependency_security_static_analysis')
        assert stage['unavailable'] == ['typescript: ' + translated]
        assert stage['status'] == 'review_required'
    assert payload == original
    assert canonical['scanner_execution_records'][0] == record


@pytest.mark.parametrize('value', [
    'typescript: Authenticated current-main CI TypeScript evidence is unavailable. PRIVATE',
    'semgrep: Authenticated current-main CI TypeScript evidence is unavailable.',
    'typescript: Unknown scanner evidence requires human verification.',
])
@_isolated_preflight_test
def test_unknown_failure_copy_remains_rejected(value):
    from nico.api import final_report_worker_bootstrap  # noqa: F401
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    from nico.spanish_scanner_unavailable_contracts import translate_scanner_unavailable_contract

    install_spanish_publication_preflight_v93()
    assert translate_scanner_unavailable_contract(value) is None
    with pytest.raises(ValueError, match='missing Spanish presentation translation'):
        _localize_tree({'unavailable': [value]})
