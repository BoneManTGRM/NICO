from copy import deepcopy
from collections import OrderedDict

import pytest

from nico.report_json_copy import copy_with_tree_ownership


def test_owned_tree_is_fully_isolated_and_keeps_immutable_leaves():
    text = 'retained evidence'
    source = {'assessment': {'candidates': [{'raw': [text, None, 3, True]}]}}
    result, owned = copy_with_tree_ownership(source)
    assert owned is True and result == source
    assert result['assessment']['candidates'][0]['raw'][0] is text
    result['assessment']['candidates'][0]['raw'].append('output only')
    assert len(source['assessment']['candidates'][0]['raw']) == 4


def test_aliases_and_cycles_copy_correctly_without_ownership_guarantee():
    shared = {'raw': []}
    source = {'a': shared, 'b': shared}
    result, owned = copy_with_tree_ownership(source)
    assert owned is False and result['a'] is result['b']
    assert result['a'] is not shared
    source['self'] = source
    result, owned = copy_with_tree_ownership(source)
    assert owned is False and result['self'] is result


@pytest.mark.parametrize('opaque', [([],), bytearray(b'raw'), OrderedDict(a=[]), {1: []}])
def test_unsupported_values_keep_legacy_copy_semantics(opaque):
    source = {'payload': opaque}
    result, owned = copy_with_tree_ownership(source)
    assert owned is False and result == deepcopy(source)
    assert type(result['payload']) is type(opaque)
    assert result['payload'] is not opaque


def test_custom_hook_runs_once_and_is_not_certified():
    class Custom:
        calls = 0
        def __deepcopy__(self, memo):
            type(self).calls += 1
            return {'copied': True}
    result, owned = copy_with_tree_ownership({'payload': Custom()})
    assert result == {'payload': {'copied': True}}
    assert owned is False and Custom.calls == 1


def test_deep_plain_tree_falls_back_without_ownership_guarantee():
    source = {}
    for _ in range(70):
        source = {'child': source}
    result, owned = copy_with_tree_ownership(source)
    assert result == deepcopy(source) and owned is False
