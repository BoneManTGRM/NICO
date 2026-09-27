"""Projection copies retain evidence and isolation while avoiding throw-away clones."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nico import client_finding_remediation_register_v4 as register_projection
from nico import comprehensive_canonical_projection_truth_v55 as final_projection


def _project(module, report):
    if module is register_projection:
        return module.synchronize_canonical_finding_surfaces(
            report, {"code_findings": [], "operational_findings": [], "summary": {}}
        )
    return module.normalize_final_projection(report)


@pytest.mark.parametrize("module", [register_projection, final_projection])
def test_plain_projection_matches_retained_deepcopy_path_without_source_aliases(module, monkeypatch):
    evidence = {"raw": [{"text": "Exact source literal", "unknown": [1, None, False, 1.25]}]}
    shared = {"evidence": evidence}
    source = {
        "left": shared, "right": shared,
        "assessment": {"same_evidence": evidence, "retained_unavailable": True},
        "human_review_required": True, "client_delivery_allowed": False,
        "scanner_execution_records": [{
            "scanner_name": "eslint", "status": "unavailable", "completed": False,
            "failure_reason": "eslint is not installed in the worker image.",
        }],
    }
    original = deepcopy(source)
    actual = _project(module, source)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_plain_report_containers", lambda value: False)
        expected = _project(module, source)
    assert actual == expected
    assert source == original
    assert actual["left"] is not actual["right"]
    assert actual["left"]["evidence"] is not actual["assessment"]["same_evidence"]
    actual["left"]["evidence"]["raw"][0]["unknown"].append("output only")
    assert actual["right"]["evidence"] == evidence
    assert actual["assessment"]["same_evidence"] == evidence
    assert source == original
    assert actual["human_review_required"] is True
    assert actual["client_delivery_allowed"] is False
    assert actual["scanner_execution_records"][0]["completed"] is False


class _Opaque:
    def __init__(self):
        self.values = ["retained"]


class _CustomDict(dict):
    pass


@pytest.mark.parametrize("module", [register_projection, final_projection])
@pytest.mark.parametrize("leaf", [
    _Opaque(), ([], "tuple"), {"set-value"}, bytearray(b"bytes"), _CustomDict(raw=[]),
])
def test_non_json_graphs_keep_historical_copy_and_alias_boundaries(module, leaf):
    source = {"left": leaf, "right": leaf, "assessment": {"leaf": leaf}}
    assert not register_projection._plain_report_containers(source)
    actual = _project(module, source)
    if not isinstance(leaf, dict):
        # Opaque leaves bypass recursive projection. The original initial clone
        # preserves top-level sharing and the second assessment clone separates it.
        assert actual["left"] is actual["right"]
        assert actual["left"] is not leaf
        assert actual["assessment"]["leaf"] is not actual["left"]
    else:
        # Mapping projection historically produces independent plain dictionaries.
        assert type(actual["left"]) is dict
        assert actual["left"] is not actual["right"]
        assert actual["left"]["raw"] is not leaf["raw"]


@pytest.mark.parametrize("source", [{1: []}, {"nested": {1: []}}, _CustomDict(raw=[])])
def test_non_plain_keys_and_mappings_use_legacy_copy(source):
    assert not register_projection._plain_report_containers(source)


@pytest.mark.parametrize("module", [register_projection, final_projection])
def test_cyclic_graph_still_fails_without_mutating_source(module):
    source = {}
    source["cycle"] = source
    with pytest.raises(RecursionError):
        _project(module, source)
    assert list(source) == ["cycle"] and source["cycle"] is source
