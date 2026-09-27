from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType

import pytest

from nico import client_assessment_truth_v3 as client_truth
from nico import comprehensive_assessment_hardening_v1 as hardening

MODULES = (client_truth, hardening)
FLAG = "final_report_input_scores_synchronized"


def _historical(module, canonical):
    return any(item.get(FLAG) is True for item in module._iter_mappings(deepcopy(dict(canonical))))


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("flag", [True, False, 1, "true", None])
def test_readonly_score_sync_keeps_strict_boolean_semantics(module, flag) -> None:
    canonical = {"assessment": {FLAG: flag}, "retained": {"findings": [{"id": "finding", "status": "failed"}]}}
    before = deepcopy(canonical)
    assert module._contains_score_sync(canonical) == _historical(module, canonical)
    assert canonical == before


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("depth", [0, 9, 10, 11, 20])
def test_readonly_score_sync_keeps_depth_boundary(module, depth) -> None:
    canonical = {FLAG: True}
    for _ in range(depth):
        canonical = {"nested": canonical}
    assert module._contains_score_sync(canonical) == _historical(module, canonical)
    assert module._contains_score_sync(canonical) is (depth <= 10)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("key", ["pdf_base64", "markdown", "html", "RAW_OUTPUT", "stdout", "stderr", "secret", "match"])
def test_readonly_score_sync_preserves_module_specific_skipped_keys(module, key) -> None:
    canonical = {key: {FLAG: True}}
    assert module._contains_score_sync(canonical) == _historical(module, canonical)


@pytest.mark.parametrize("module", MODULES)
def test_plain_evidence_graph_does_not_deepcopy_or_mutate(module, monkeypatch) -> None:
    register = {
        "findings": [{"candidate_id": str(i), "status": "failed", "raw_payload": "retained"} for i in range(100)],
        "canonical_digest_sha256": "a" * 64,
        "totals": {"raw": 100},
    }
    canonical = {"assessment": {FLAG: True, "canonical_scanner_finding_register": register}}
    before = deepcopy(canonical)

    def forbid_copy(*args, **kwargs):
        raise AssertionError("read-only score predicate copied the evidence graph")

    monkeypatch.setattr(client_truth, "deepcopy", forbid_copy)
    monkeypatch.setattr(hardening, "deepcopy", forbid_copy)
    assert module._contains_score_sync(canonical) is True
    assert canonical == before
    assert canonical["assessment"]["canonical_scanner_finding_register"] is register


class _CopyProjected(dict):
    def __deepcopy__(self, memo):
        return {FLAG: True}


@pytest.mark.parametrize("module", MODULES)
def test_custom_container_deepcopy_projection_is_preserved(module) -> None:
    canonical = {"custom": _CopyProjected({FLAG: False})}
    assert module._contains_score_sync(canonical) is True
    assert module._contains_score_sync(canonical) == _historical(module, canonical)
    assert canonical["custom"][FLAG] is False


@pytest.mark.parametrize("module", MODULES)
def test_root_mapping_list_aliases_and_cycles_keep_historical_result(module) -> None:
    shared = {FLAG: True}
    canonical = {"stages": [shared, shared], "tuple_is_not_traversed": ({FLAG: True},)}
    canonical["cycle"] = canonical
    assert module._contains_score_sync(MappingProxyType(canonical)) == _historical(module, canonical)


@pytest.mark.parametrize("module", MODULES)
def test_non_string_mapping_key_keeps_historical_projection(module) -> None:
    canonical = {1: {FLAG: True}}
    assert module._contains_score_sync(canonical) == _historical(module, canonical)
