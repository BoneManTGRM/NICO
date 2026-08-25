from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_canonical_truth_hash_compat_v1 import (
    reconcile_known_post_render_hash_drift,
    synchronize_report_package_hash,
)
from nico.comprehensive_report_package import _canonical_hash


def _canonical() -> dict:
    return {
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_hash_compat_1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_hash_compat_1",
            "customer_id": "customer_hash_compat_1",
            "project_id": "project_hash_compat_1",
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _historically_drifted_status() -> tuple[dict, dict, str]:
    original = _canonical()
    expected = _canonical_hash(original)
    drifted = deepcopy(original)
    drifted.update(
        {
            "unique_finding_count": 0,
            "exact_source_finding_count": 0,
            "operational_finding_count": 0,
            "finding_register_deduplicated": True,
            "scanner_state_reconciled": True,
            "cross_format_score_truth_synchronized": True,
            "pre_render_truth_reconciliation": True,
        }
    )
    status = {
        "run_id": original["identity"]["run_id"],
        "terminal": True,
        "reports": {
            "canonical_truth_sha256": expected,
            "json": drifted,
        },
    }
    return status, original, expected


def test_future_report_hash_is_bound_to_final_persisted_canonical_json() -> None:
    canonical = _canonical()
    canonical["pre_render_truth_reconciliation"] = True
    result = {
        "canonical_truth_sha256": "stale",
        "report_package": {
            "canonical_truth_sha256": "stale",
            "json": canonical,
        },
    }
    before = deepcopy(result)

    synchronized = synchronize_report_package_hash(result)
    expected = _canonical_hash(canonical)

    assert synchronized["canonical_truth_sha256"] == expected
    assert synchronized["report_package"]["canonical_truth_sha256"] == expected
    assert synchronized["report_package"]["json"] == canonical
    assert result == before


def test_known_historical_post_render_metadata_drift_recovers_exact_stored_truth() -> None:
    status, original, expected = _historically_drifted_status()
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is True
    assert recovered["reports"]["json"] == original
    assert recovered["reports"]["canonical_truth_sha256"] == expected
    assert _canonical_hash(recovered["reports"]["json"]) == expected
    assert status == before


def test_unknown_canonical_truth_mismatch_remains_fail_closed() -> None:
    status, _, _ = _historically_drifted_status()
    status["reports"]["canonical_truth_sha256"] = "0" * 64

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == status
    assert _canonical_hash(recovered["reports"]["json"]) != "0" * 64


def test_recovery_requires_complete_exact_known_metadata_signature() -> None:
    status, _, _ = _historically_drifted_status()
    del status["reports"]["json"]["scanner_state_reconciled"]

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == status
