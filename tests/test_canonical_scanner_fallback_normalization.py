"""Legacy canonical scanner fallback retains normalized evidence at publication."""
from copy import deepcopy

import pytest

from nico.v2_production_authority import _inject_live_runtime_truth

SHA = "a" * 40
RAW_DIGEST = "b" * 64


def _record():
    return {
        "tool": "bandit", "status": "completed", "returncode": 1,
        "commit_sha": SHA, "snapshot_commit_sha": SHA,
        "artifact_hash": "c" * 64, "raw_artifact_sha256": RAW_DIGEST,
        "raw_artifact_retention_complete": True,
        "verified_for_this_report": True,
        "findings": [{"test_id": "B101"}],
    }


def _inject(record, *, context_commit=SHA):
    source = {"report_package": {"json": {
        "identity": {"commit_sha": SHA, "run_id": "comprun_fallback"},
        "assessment": {}, "scanner_execution_records": [record],
        "human_review_required": True, "client_delivery_allowed": False,
    }}}
    context = {"commit_sha": context_commit, "report_language": "en", "prior_stage_results": {}}
    original_source, original_context = deepcopy(source), deepcopy(context)
    result = _inject_live_runtime_truth(source, context)
    assert source == original_source and context == original_context
    canonical = result["report_package"]["json"]
    populations = [container[key] for container in (canonical, canonical["assessment"])
                   for key in ("requested_scanner_records", "scanner_execution_records")]
    assert all(population == populations[0] for population in populations)
    assert canonical["human_review_required"] is True
    assert canonical["client_delivery_allowed"] is False
    assert result["retained_scanner_evidence"]["source"] == "canonical_source_scanner_records"
    return populations[0][0]


def test_fallback_normalizes_legacy_exit_alias_before_requested_population_is_shared():
    result = _inject(_record())
    assert result["exit_code"] == 1
    assert result["status"] == "completed_with_findings"
    assert result["verified_complete"] is True
    assert result["raw_artifact_sha256"] == RAW_DIGEST


def test_fallback_uses_immutable_canonical_commit_not_a_stale_runtime_projection():
    result = _inject(_record(), context_commit="d" * 40)
    assert result["exit_code"] == 1
    assert result["commit_sha"] == SHA
    assert result["exact_commit_match"] is True


@pytest.mark.parametrize("defect", ["wrong_source", "not_retained", "not_applicable"])
def test_fallback_normalization_does_not_restore_invalid_verification(defect):
    raw = _record()
    if defect == "wrong_source":
        raw["commit_sha"] = "d" * 40
        raw["snapshot_commit_sha"] = "d" * 40
    elif defect == "not_retained":
        raw["raw_artifact_retention_complete"] = False
    else:
        raw.update(status="not_applicable", applicable=False,
                   applicability_reason="No Python source was present.")
    result = _inject(raw)
    assert result["exit_code"] == 1
    assert result["completed"] is False
    assert result["verified_complete"] is False
    if defect == "wrong_source":
        assert result["commit_sha"] == "d" * 40
        assert result["exact_commit_match"] is False
    elif defect == "not_retained":
        assert result["raw_artifact_retention_complete"] is False
    else:
        assert result["status"] == "not_applicable"
        assert result["verified_for_this_report"] is False


def test_fallback_does_not_invent_a_missing_native_output_digest():
    raw = _record()
    raw.pop("raw_artifact_sha256")
    result = _inject(raw)
    assert result["exit_code"] == 1
    assert "raw_artifact_sha256" not in result
