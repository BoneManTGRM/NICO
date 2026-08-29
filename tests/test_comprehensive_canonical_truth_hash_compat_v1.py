from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

from nico import comprehensive_canonical_truth_hash_compat_v1 as compat
from nico.comprehensive_canonical_truth_hash_compat_v1 import (
    reconcile_known_post_render_hash_drift,
    synchronize_report_package_hash,
)
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_report_package import _canonical_hash


_TRUE_KEYS = (
    "finding_register_deduplicated",
    "scanner_state_reconciled",
    "cross_format_score_truth_synchronized",
    "pre_render_truth_reconciliation",
)
_COUNT_KEYS = (
    "unique_finding_count",
    "exact_source_finding_count",
    "operational_finding_count",
)


def _canonical() -> dict:
    return {
        "service_id": "comprehensive",
        "report_language": "en",
        "identity": {
            "run_id": "comprun_hash_compat_1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_hash_compat_1",
            "customer_id": "customer_hash_compat_1",
            "project_id": "project_hash_compat_1",
            "report_language": "en",
        },
        "assessment": {
            "report_language": "en",
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
    pdf = b"%PDF-1.4\nfrozen"
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
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        },
    }
    return status, original, expected


def test_future_report_hash_is_bound_to_final_persisted_canonical_json() -> None:
    canonical = _canonical()
    canonical["pre_render_truth_reconciliation"] = True
    canonical["nested_render_metadata"] = {"markdown": "exact retained value"}
    result = {
        "canonical_truth_sha256": "stale",
        "report_package": {
            "canonical_truth_sha256": "stale",
            "json": canonical,
        },
    }
    before = deepcopy(result)

    synchronized = synchronize_report_package_hash(result)
    expected = canonical_sha256(canonical)

    assert synchronized["canonical_truth_sha256"] == expected
    assert synchronized["report_package"]["canonical_truth_sha256"] == expected
    assert synchronized["report_package"]["json"] == canonical
    assert result == before
    assert expected != _canonical_hash(canonical)


def test_legacy_hash_without_exact_manifest_cannot_ignore_nested_rendered_field_tamper() -> None:
    from nico.comprehensive_api_controller import (
        _canonical_truth_hash_integrity_bound,
        _final_report_package_integrity_bound,
    )

    canonical = _canonical()
    canonical["nested_render_metadata"] = {"markdown": "original retained value"}
    pdf = b"%PDF-1.4\n%%EOF\n"
    report = {
        "report_id": "comprehensive_report_unbound_legacy_hash",
        "report_language": "en",
        "markdown": "# frozen source report",
        "html": "<article>frozen source report</article>",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "json": canonical,
        "canonical_truth_sha256": _canonical_hash(canonical),
    }
    assert report["canonical_truth_sha256"] != canonical_sha256(canonical)
    assert _canonical_truth_hash_integrity_bound(report) is False
    assert _final_report_package_integrity_bound(report) is False

    report["json"]["nested_render_metadata"]["markdown"] = (
        "tampered retained value"
    )

    # The historical digest deliberately ignored keys named ``markdown``. Without
    # the complete exact-artifact manifest family, that compatibility digest cannot
    # authorize current artifact recovery or publication.
    assert report["canonical_truth_sha256"] == _canonical_hash(report["json"])
    assert _canonical_truth_hash_integrity_bound(report) is False
    assert _final_report_package_integrity_bound(report) is False


def test_known_historical_post_render_metadata_drift_recovers_exact_stored_truth() -> None:
    status, original, expected = _historically_drifted_status()
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is True
    assert recovered["reports"]["json"] == original
    assert recovered["reports"]["canonical_truth_sha256"] == expected
    assert _canonical_hash(recovered["reports"]["json"]) == expected
    assert status == before


def test_partial_known_historical_metadata_signature_recovers() -> None:
    status, original, expected = _historically_drifted_status()
    keep = {"scanner_state_reconciled", "unique_finding_count"}
    for key in (*_TRUE_KEYS, *_COUNT_KEYS):
        if key not in keep:
            status["reports"]["json"].pop(key, None)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is True
    assert recovered["reports"]["json"] == original
    assert _canonical_hash(recovered["reports"]["json"]) == expected


def test_single_known_historical_metadata_field_recovers() -> None:
    status, original, expected = _historically_drifted_status()
    keep = {"pre_render_truth_reconciliation"}
    for key in (*_TRUE_KEYS, *_COUNT_KEYS):
        if key not in keep:
            status["reports"]["json"].pop(key, None)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is True
    assert recovered["reports"]["json"] == original
    assert _canonical_hash(recovered["reports"]["json"]) == expected


def test_recovery_removes_only_the_subset_needed_for_exact_stored_hash() -> None:
    original = _canonical()
    original["finding_register_deduplicated"] = True
    expected = _canonical_hash(original)
    drifted = deepcopy(original)
    drifted["scanner_state_reconciled"] = True
    status = {
        "reports": {
            "canonical_truth_sha256": expected,
            "json": drifted,
        }
    }

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is True
    assert recovered["reports"]["json"] == original
    assert recovered["reports"]["json"]["finding_register_deduplicated"] is True


def test_unknown_canonical_truth_mismatch_remains_fail_closed() -> None:
    status, _, _ = _historically_drifted_status()
    status["reports"]["canonical_truth_sha256"] = "0" * 64

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == status
    assert _canonical_hash(recovered["reports"]["json"]) != "0" * 64


def test_partial_known_drift_plus_unknown_field_remains_fail_closed() -> None:
    status, _, _ = _historically_drifted_status()
    keep = {"scanner_state_reconciled", "unique_finding_count"}
    for key in (*_TRUE_KEYS, *_COUNT_KEYS):
        if key not in keep:
            status["reports"]["json"].pop(key, None)
    status["reports"]["json"]["assessor_only_flag"] = True
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == before


def test_known_field_with_unexpected_value_remains_fail_closed() -> None:
    status, _, _ = _historically_drifted_status()
    status["reports"]["json"]["scanner_state_reconciled"] = False
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == before


def test_invalid_count_value_is_not_removed() -> None:
    status, _, _ = _historically_drifted_status()
    status["reports"]["json"]["unique_finding_count"] = "0"
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == before


def test_mismatch_without_known_post_render_metadata_remains_fail_closed() -> None:
    original = _canonical()
    status = {
        "reports": {
            "canonical_truth_sha256": "0" * 64,
            "json": original,
        }
    }
    before = deepcopy(status)

    recovered, reconciled = reconcile_known_post_render_hash_drift(status)

    assert reconciled is False
    assert recovered == before


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
