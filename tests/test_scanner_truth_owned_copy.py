"""Private-tree reuse must preserve evidence, alias isolation and artifact bytes."""
from copy import deepcopy
import pytest
from nico import scanner_applicability_v1 as applicability
from nico import comprehensive_authoritative_scanner_truth_v62 as authority
from tests.test_report_json_copy import _graph

CONSUMERS = [(applicability, 'normalize_scanner_applicability_canonical'),
             (authority, 'reconcile_authoritative_scanner_truth')]

def legacy_copy(value):
    return deepcopy(value), False

@pytest.mark.parametrize('module,name', CONSUMERS)
@pytest.mark.parametrize('shape', ['tree', 'alias', 'opaque', 'empty', 'missing'])
def test_evidence_and_alias_isolation_match_legacy(monkeypatch, module, name, shape):
    from tests.test_v2_premium_report_renderer import _package
    source = _package('es-MX')['json']
    raw = {'items': [{'text': 'évidence retained', 'value': 7}]}
    source['assessment']['raw_evidence'] = raw
    if shape == 'alias':
        source['external_alias'] = raw
    elif shape == 'opaque':
        source['opaque'] = bytearray(b'evidence')
    elif shape == 'empty':
        source['assessment'] = {}
    elif shape == 'missing':
        source.pop('assessment')
    before = deepcopy(source)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        expected = getattr(module, name)(source)
    actual = getattr(module, name)(source)
    assert _graph(actual) == _graph(expected)
    assert source == before
    actual['assessment']['output_only'] = []
    assert source == before

@pytest.mark.parametrize('module,name', CONSUMERS)
def test_one_redundant_assessment_copy_removed(monkeypatch, module, name):
    from tests.test_v2_premium_report_renderer import _package
    source = _package('es-MX')['json']
    source['assessment']['owned_probe'] = [{'evidence': 'unchanged'}]
    calls = []
    original = module.deepcopy
    def observe(value, *args):
        if isinstance(value, dict) and 'owned_probe' in value:
            calls.append(True)
        return original(value, *args)
    monkeypatch.setattr(module, 'deepcopy', observe)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        getattr(module, name)(source)
    old = len(calls)
    calls.clear()
    getattr(module, name)(source)
    assert old - len(calls) == 1

@pytest.mark.parametrize('locale', ['en', 'es-MX'])
def test_installed_artifacts_identical(monkeypatch, locale):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    source = {'json': _fixed_status(locale)['reports']['json']}
    register = _install_finalized_scanner_register(source['json'])
    register['totals'] = {'raw': 1, 'review_required': 1, 'source_path': 1}
    register['summary_by_category'] = {'static': dict(register['totals'])}
    before = deepcopy(source)
    with monkeypatch.context() as patch:
        for module, _ in CONSUMERS:
            patch.setattr(module, 'copy_with_tree_ownership', legacy_copy)
        expected = phase17.rebuild_client_artifacts(source)
    actual = phase17.rebuild_client_artifacts(source)
    assert actual == expected  # All artifact bytes, hashes, canonical evidence and gates.
    assert source == before
    assert actual['human_review_required'] is True
    assert actual['client_delivery_allowed'] is False
