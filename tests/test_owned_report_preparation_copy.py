from copy import deepcopy
import pytest

from nico import production_report_truth_gate_v1 as truth
from nico import v2_report_quality_repairs as quality
from nico import phase17_canonical_artifact_rebuild_v1 as phase17
from nico.report_json_copy import copy_with_tree_ownership

CONSUMERS = [(truth, 'reconcile_production_report_truth'),
             (quality, 'repair_canonical_truth'),
             (phase17, '_populate_premium_stage_summaries')]


def legacy_copy(value):
    return deepcopy(value), False


@pytest.mark.parametrize('module,name', CONSUMERS)
@pytest.mark.parametrize('shape', ['tree', 'alias', 'empty', 'missing', 'opaque'])
def test_consumer_equivalence_and_source_isolation(monkeypatch, module, name, shape):
    from tests.test_v2_premium_report_renderer import _package
    source = _package('en')
    raw = {'items': [{'text': 'retained candidate evidence', 'value': 7}]}
    source['json']['assessment']['raw_evidence'] = raw
    if shape == 'alias':
        source['other_evidence'] = raw
    elif shape == 'empty':
        source['json'] = {}
    elif shape == 'missing':
        source.pop('json')
    elif shape == 'opaque':
        source['opaque'] = bytearray(b'retained')
    before = deepcopy(source)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        expected = getattr(module, name)(source)
    actual = getattr(module, name)(source)
    from tests.test_report_json_copy import _graph
    assert _graph(actual) == _graph(expected)
    assert actual == expected and source == before
    actual['json'].setdefault('assessment', {})['output_only'] = []
    assert source == before


@pytest.mark.parametrize('module,name', CONSUMERS)
def test_owned_path_removes_full_subtree_copy_calls(monkeypatch, module, name):
    from tests.test_v2_premium_report_renderer import _package
    source = _package('en')
    source['json']['assessment']['owned_copy_probe'] = [{'raw': 'evidence'}]
    calls = []
    original = module.deepcopy
    def observed(value, *args):
        if isinstance(value, dict) and ('owned_copy_probe' in value or 'owned_copy_probe' in (value.get('assessment') or {})):
            calls.append(True)
        return original(value, *args)
    monkeypatch.setattr(module, 'deepcopy', observed)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        getattr(module, name)(source)
    previous = len(calls)
    calls.clear()
    getattr(module, name)(source)
    assert previous - len(calls) == (1 if module is phase17 else 2)


@pytest.fixture(scope='module', params=['en', 'es-MX'])
def finalized_source(request):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    package = {'json': _fixed_status(request.param)['reports']['json']}
    register = _install_finalized_scanner_register(package['json'])
    exemplar = register['findings'][0]
    register['findings'] = [
        {**exemplar, 'candidate_id': f'OWNED-{i}', 'finding_id': f'OWNED-{i}',
         'raw_payload': {'items': [{'text': f'original evidence {i}:{j}', 'index': j} for j in range(8)]}}
        for i in range(16)
    ]
    register['candidate_record_count'] = 16
    register['totals'] = {'raw': 16, 'review_required': 16, 'source_path': 16}
    register['summary_by_category'] = {'static': dict(register['totals'])}
    return phase17.rebuild_client_artifacts(package)


def test_complete_artifacts_and_evidence_equal_legacy_copies(finalized_source, monkeypatch):
    before = deepcopy(finalized_source)
    with monkeypatch.context() as patch:
        for module, _ in CONSUMERS:
            patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        expected = phase17.rebuild_client_artifacts(finalized_source)
    actual = phase17.rebuild_client_artifacts(finalized_source)
    assert actual == expected  # Every format body, manifest, hash and lifecycle field.
    assert finalized_source == before
    assert len(actual['json']['assessment']['canonical_scanner_finding_register']['findings']) == 16
    assert actual['human_review_required'] is True
    assert actual['client_delivery_allowed'] is False


@pytest.mark.parametrize('corruption', ['duplicate_id', 'missing_id', 'raw_total'])
def test_candidate_rejections_preserved(finalized_source, monkeypatch, corruption):
    package = deepcopy(finalized_source)
    register = package['json']['assessment']['canonical_scanner_finding_register']
    if corruption == 'duplicate_id':
        register['findings'][1]['candidate_id'] = register['findings'][0]['candidate_id']
    elif corruption == 'missing_id':
        register['findings'][0].pop('candidate_id')
    else:
        register['totals']['raw'] += 1
    before = deepcopy(package)
    with monkeypatch.context() as patch:
        for module, _ in CONSUMERS:
            patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        with pytest.raises(ValueError) as old:
            phase17.rebuild_client_artifacts(package)
    with pytest.raises(ValueError) as new:
        phase17.rebuild_client_artifacts(package)
    assert str(new.value) == str(old.value)
    assert package == before


def test_stage_population_keeps_falsy_mapping_fallback():
    class FalsyMapping(dict):
        def __bool__(self):
            return False
    source = {'json': FalsyMapping(private_marker='must use historical empty fallback')}
    result = phase17._populate_premium_stage_summaries(source)
    assert 'private_marker' not in result['json']
    assert source['json']['private_marker'] == 'must use historical empty fallback'
