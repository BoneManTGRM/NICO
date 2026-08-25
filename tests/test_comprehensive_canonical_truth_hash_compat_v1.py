from __future__ import annotations

import base64
from copy import deepcopy

from nico import comprehensive_canonical_truth_hash_compat_v1 as compat
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
        "repository": original["identity"]["repository"],
        "commit_sha": original["identity"]["commit_sha"],
        "report_language": "en",
        "terminal": True,
        "integrity_sha256": "run-integrity",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "comprehensive_report_hash_compat_1",
            "canonical_truth_sha256": expected,
            "json": drifted,
            "markdown": "# frozen source report",
            "html": "<article>frozen source report</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nfrozen").decode("ascii"),
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


def test_installed_compat_restores_affected_frozen_pdf_without_weakening_truth(monkeypatch) -> None:
    from nico import comprehensive_decision_grade_report_v5 as report_builder
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_same_run_locale_report_v1 as same_run

    # Record every mutable production binding so pytest restores the process after
    # this integration check even when other report wrappers are already installed.
    monkeypatch.setattr(
        report_builder,
        "build_comprehensive_report_package",
        report_builder.build_comprehensive_report_package,
    )
    monkeypatch.setattr(
        providers,
        "build_comprehensive_report_package",
        providers.build_comprehensive_report_package,
    )
    monkeypatch.setattr(
        same_run,
        "build_same_run_locale_report",
        same_run.build_same_run_locale_report,
    )

    installation = compat.install_canonical_truth_hash_compat()
    assert installation["builder_hash_sync_bound"] is True
    assert installation["same_run_legacy_recovery_bound"] is True
    assert installation["unknown_hash_mismatch_fails_closed"] is True

    status, original, expected = _historically_drifted_status()
    before = deepcopy(status)
    projection = same_run.build_same_run_locale_report(status, "en")

    assert status == before
    assert projection["canonical_truth_hash_reconciled"] is True
    assert projection["canonical_truth_sha256"] == expected
    assert projection["report"]["json"] == original
    assert projection["report"]["pdf_base64"] == status["reports"]["pdf_base64"]
    assert projection["assessment_rerun"] is False
    assert projection["human_review_required"] is True
    assert projection["client_delivery_allowed"] is False
