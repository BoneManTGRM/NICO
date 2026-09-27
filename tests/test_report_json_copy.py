from __future__ import annotations

import copy
from collections import OrderedDict
from decimal import Decimal

import pytest

from nico import report_json_copy as report_copy


def _graph(value):
    """Compare container identity relationships without relying on equality cycles."""
    visited = {}

    def visit(item):
        if type(item) not in (dict, list):
            return (type(item), item)
        identity = id(item)
        if identity in visited:
            return ("reference", visited[identity])
        ordinal = len(visited)
        visited[identity] = ordinal
        if type(item) is dict:
            return (dict, ordinal, [(key, visit(child)) for key, child in item.items()])
        return (list, ordinal, [visit(child) for child in item])

    return visit(value)


@pytest.mark.parametrize("value", [None, True, False, 0, 2**100, -42, 1.25, float("inf"), "é 東京", ""])
def test_exact_immutable_scalars_keep_standard_identity(value):
    assert report_copy.deepcopy(value) is copy.deepcopy(value)


def test_nan_identity_is_preserved_without_equality_comparison():
    value = float("nan")
    assert report_copy.deepcopy(value) is value


def test_dict_list_aliases_cycles_order_and_source_isolation():
    evidence = ["literal", {"unicode": "á", "number": 3}]
    shared = {"evidence": evidence}
    source = {"z": shared, "a": shared, "children": [shared, shared]}
    source["self"] = source
    source["children"].append(source["children"])
    expected = copy.deepcopy(source)
    actual = report_copy.deepcopy(source)
    assert _graph(actual) == _graph(expected)
    assert list(actual) == ["z", "a", "children", "self"]
    assert actual is not source
    actual["z"]["evidence"][1]["number"] = 7
    assert evidence[1]["number"] == 3
    assert actual["a"]["evidence"][1]["number"] == 7
    assert actual["self"] is actual
    assert actual["children"][-1] is actual["children"]


class _Dict(dict):
    pass


class _List(list):
    pass


class _String(str):
    pass


class _Integer(int):
    pass


class _Hook:
    calls = 0

    def __init__(self):
        self.children = []

    def __deepcopy__(self, memo):
        type(self).calls += 1
        result = type(self)()
        memo[id(self)] = result
        result.children = copy.deepcopy(self.children, memo)
        return result


@pytest.mark.parametrize("value", [
    _Dict(value=[]), _List([[]]), _String("text"), _Integer(5),
    ([], []), {"set"}, bytearray(b"bytes"), Decimal("1.25"),
    OrderedDict([("b", []), ("a", [])]), {1: []}, {_String("custom-key"): []},
])
def test_unsupported_graph_delegates_original_once_preserving_types(value, monkeypatch):
    source = {"first": {"already": [1, 2]}, "late": value, "alias": value}
    calls = []

    def legacy(original, *args):
        calls.append((original, args))
        return copy.deepcopy(original, *args)

    monkeypatch.setattr(report_copy, "_legacy_deepcopy", legacy)
    actual = report_copy.deepcopy(source)
    expected = copy.deepcopy(source)
    assert len(calls) == 1 and calls[0][0] is source and calls[0][1] == ()
    assert type(actual["late"]) is type(expected["late"])
    assert actual == expected
    assert actual["late"] is actual["alias"]
    if isinstance(value, dict):
        assert [type(key) for key in actual["late"]] == [type(key) for key in expected["late"]]


def test_late_custom_hook_runs_once_and_preserves_back_references():
    _Hook.calls = 0
    custom = _Hook()
    source = {"ordinary": [1, 2], "custom": custom, "alias": custom}
    custom.children = [source]
    actual = report_copy.deepcopy(source)
    assert _Hook.calls == 1
    assert actual["custom"] is actual["alias"]
    assert actual["custom"] is not custom
    assert actual["custom"].children[0] is actual
    assert custom.children[0] is source


def test_optimistic_type_checks_do_not_invoke_custom_metaclass_equality():
    class Meta(type):
        comparisons = 0

        def __eq__(cls, other):
            Meta.comparisons += 1
            return super().__eq__(other)

        __hash__ = type.__hash__

    class Custom(metaclass=Meta):
        calls = 0

        def __deepcopy__(self, memo):
            type(self).calls += 1
            return type(self)()

    source = {"late": Custom()}
    actual = report_copy.deepcopy(source)
    assert type(actual["late"]) is Custom
    assert Custom.calls == 1
    assert Meta.comparisons == 0


@pytest.mark.parametrize("memo", [None, {}])
def test_any_explicit_memo_is_delegated_unchanged(memo, monkeypatch):
    source = {"value": []}
    calls = []

    def legacy(value, provided):
        calls.append((value, provided))
        return copy.deepcopy(value, provided)

    monkeypatch.setattr(report_copy, "_legacy_deepcopy", legacy)
    actual = report_copy.deepcopy(source, memo)
    assert actual == source
    assert calls == [(source, memo)]
    assert calls[0][0] is source and calls[0][1] is memo
    if memo is not None:
        assert memo[id(source)] is actual


def test_prepopulated_memo_returns_standard_override():
    source = []
    replacement = {"preserved": True}
    assert report_copy.deepcopy(source, {id(source): replacement}) is replacement


def test_deep_valid_graph_uses_standard_recursion_path(monkeypatch):
    source = []
    for _ in range(100):
        source = {"nested": source}
    calls = []

    def legacy(value):
        calls.append(value)
        return copy.deepcopy(value)

    monkeypatch.setattr(report_copy, "_legacy_deepcopy", legacy)
    actual = report_copy.deepcopy(source)
    assert actual == copy.deepcopy(source)
    assert len(calls) == 1 and calls[0] is source


def test_excessive_depth_preserves_standard_error_without_source_mutation():
    source = []
    for _ in range(2000):
        source = [source]
    for duplicate in (copy.deepcopy, report_copy.deepcopy):
        with pytest.raises(RecursionError):
            duplicate(source)
    item = source
    count = 0
    while item:
        assert len(item) == 1
        item = item[0]
        count += 1
    assert count == 2000


def test_custom_copy_error_is_propagated_once():
    class Broken:
        calls = 0

        def __deepcopy__(self, memo):
            self.calls += 1
            raise RuntimeError("original copy failure")

    custom = Broken()
    with pytest.raises(RuntimeError, match="original copy failure"):
        report_copy.deepcopy({"ordinary": {"a": [1]}, "late": custom})
    assert custom.calls == 1


def test_invalid_explicit_memo_keeps_standard_error():
    for duplicate in (copy.deepcopy, report_copy.deepcopy):
        with pytest.raises(AttributeError):
            duplicate({"value": []}, 123)
