"""Repeated evidence must keep its values, paths and per-report truth."""
from collections import UserDict
from copy import deepcopy

import pytest
from nico import client_finding_remediation_register_v3 as register3
from nico import client_finding_remediation_register_v4 as register4
from nico import client_finding_remediation_register_v1 as register1
from nico import client_assessment_truth_v3 as assessment_truth
from nico import comprehensive_maturity_label_truth_v1 as maturity
from nico import v2_scanner_reconciliation as scanners

from nico import comprehensive_finding_count_truth_v66 as counts
from nico import comprehensive_decision_content_restoration_v66 as restoration


def test_count_rewrite_cache_is_local_and_preserves_complete_projection(monkeypatch):
    text = 'Canonical findings: 99; Exact-source findings: 99; Operational/context findings: 99'
    source = {
        'canonical_findings': [{'title': 'First finding', 'location': 'src/a.py:1'}],
        'stage_summaries': [{'rows': [[text, i] for i in range(200)],
                             'scanner_execution_records': [{'text': text}]}],
        'assessment': {'text': text},
    }
    original = deepcopy(source)
    rewrite = counts._replace_count_prose
    calls = []
    def observed(value, **kwargs):
        calls.append(value)
        return rewrite(value, **kwargs)
    monkeypatch.setattr(counts, '_replace_count_prose', observed)
    actual = counts.reconcile_finding_count_truth(source)
    assert calls.count(text) == 1
    with monkeypatch.context() as patch:
        patch.setattr(counts, 'lru_cache', lambda **kwargs: lambda function: function)
        expected = counts.reconcile_finding_count_truth(source)
    assert actual == expected
    assert source == original
    assert actual[0]['stage_summaries'][0]['scanner_execution_records'][0]['text'] == text
    source['canonical_findings'].append({'title': 'Second finding'})
    next_report, _ = counts.reconcile_finding_count_truth(source)
    assert 'Canonical findings: 2' in next_report['assessment']['text']
    actual[0]['stage_summaries'][0]['rows'][0].append('output only')
    assert source['stage_summaries'][0]['rows'][0] == [text, 0]


def test_count_rewrite_preserves_long_and_subclass_strings(monkeypatch):
    class Text(str):
        __hash__ = None
    text = Text('Canonical finding count: 19')
    long_text = 'x' * 5000 + ' Canonical findings: 19'
    source = {'assessment': {'a': text, 'b': long_text}, 'canonical_findings': []}
    actual = counts.reconcile_finding_count_truth(source)
    with monkeypatch.context() as patch:
        patch.setattr(counts, 'lru_cache', lambda **kwargs: lambda function: function)
        expected = counts.reconcile_finding_count_truth(source)
    assert actual == expected
    assert actual[0]['assessment']['a'] == 'Canonical finding count: 0'


@pytest.mark.parametrize("walker,limit", [(restoration._iter_mappings, 14), (register3._iter_mappings, 10), (register4._iter_mappings, 12)])
def test_mapping_walk_retains_order_duplicates_custom_mappings_and_depth_boundary(walker, limit):
    leaf = {'finding_id': 'retained'}
    custom = UserDict({'child': leaf})
    root = {'values': [None, True, 3, 1.5, 'source literal', custom, (leaf,)]}
    result = list(walker(root))
    assert [id(item) for item in result] == [id(root), id(custom), id(leaf), id(leaf)]
    assert list(walker(leaf, depth=limit)) == [leaf]
    assert list(walker(leaf, depth=limit + 1)) == []
    root['cycle'] = root
    # The established depth limit bounds cycles without deduplicating evidence.
    cycled = list(walker(root))
    assert sum(item is root for item in cycled) == limit + 1


class _ScalarEqualMeta(type):
    def __eq__(cls, other):
        return other is str or cls is other

    __hash__ = type.__hash__


class _ScalarEqualMapping(dict, metaclass=_ScalarEqualMeta):
    pass


@pytest.mark.parametrize("walker", [
    register1._iter_mappings, register3._iter_mappings,
    register4._iter_mappings, restoration._iter_mappings,
])
def test_mapping_type_equality_cannot_hide_nested_evidence(walker):
    child = _ScalarEqualMapping({"finding_id": "retained"})
    root = {"children": [child, (child,)]}
    assert [id(item) for item in walker(root)] == [id(root), id(child), id(child)]
    assert list(walker(child))[0] is child


def test_type_equality_cannot_hide_scanner_records_or_source_strings():
    child = _ScalarEqualMapping({"scanner_name": "eslint", "description": "retained"})
    assert list(scanners._records({"nested": [child]})) == [child]
    assert list(register1._iter_strings({"nested": child})) == ["eslint", "retained"]


def test_type_equality_cannot_bypass_truth_projection():
    source = _ScalarEqualMapping({"summary": "Canonical findings: 99"})
    result = counts._reconcile_value(
        source, canonical_count=2, exact_source_count=1,
        operational_count=1, top_title="Finding",
    )
    assert result == {"summary": "Canonical findings: 2"}
    assert type(result) is dict
    assert source["summary"] == "Canonical findings: 99"

    paths = _ScalarEqualMapping({"summary": "retained"})
    projected = assessment_truth._normalize_paths(paths)
    assert projected == {"summary": "retained"}
    assert type(projected) is dict
    assert projected is not paths

    labels = _ScalarEqualMapping({"client_readiness_contract": {"maturity_label": "High"}})
    assert maturity._contract_label(labels) == "High"
