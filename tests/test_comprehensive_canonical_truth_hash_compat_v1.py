from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

import pytest

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


def _current_hash_status() -> dict:
    status, canonical, _ = _historically_drifted_status()
    canonical["rendered"] = {"html": "<p>retained</p>", "markdown": "retained", "pdf_base64": "retained"}
    canonical["findings"] = [{"id": "finding-1", "severity": "low"}]
    canonical["scanner_state_reconciled"] = True
    status["reports"]["json"] = canonical
    status["reports"]["canonical_truth_sha256"] = canonical_sha256(canonical)
    assert canonical_sha256(canonical) != _canonical_hash(canonical)
    return status


@pytest.mark.parametrize("digest_form", ["exact", "uppercase", "whitespace"])
def test_current_digest_skips_historical_reconstruction(monkeypatch, digest_form) -> None:
    status = _current_hash_status()
    digest = status["reports"]["canonical_truth_sha256"]
    status["reports"]["canonical_truth_sha256"] = {
        "exact": digest, "uppercase": digest.upper(), "whitespace": " \n" + digest + "\t",
    }[digest_form]
    before = deepcopy(status)
    calls = []
    def counted(value):
        calls.append(value)
        return deepcopy(value)
    def unexpected(*args):
        pytest.fail("already-valid current digest entered historical reconstruction")
    monkeypatch.setattr(compat, "deepcopy", counted)
    monkeypatch.setattr(compat, "_reconstruct_exact_stored_truth", unexpected)
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False and output == before and status == before
    assert len(calls) == 3  # Preserve all original defensive-copy transformations.
    assert list(output) == list(status)
    assert list(output["reports"]) == list(status["reports"])
    assert list(output["reports"]["json"]) == list(status["reports"]["json"])
    output["reports"]["json"]["findings"][0]["severity"] = "high"
    assert status == before


@pytest.mark.parametrize("path,value", [
    (("rendered", "html"), "tampered"),
    (("rendered", "markdown"), "tampered"),
    (("rendered", "pdf_base64"), "tampered"),
    (("identity", "commit_sha"), "b" * 40),
    (("findings",), []),
    (("assessment", "technical_score"), 100),
    (("human_review_required",), False),
    (("client_delivery_allowed",), True),
    (("unknown_field",), "tampered"),
])
def test_current_digest_does_not_accept_tampered_truth(path, value) -> None:
    from nico.comprehensive_api_controller import _canonical_truth_hash_integrity_bound
    status = _current_hash_status()
    node = status["reports"]["json"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    before = deepcopy(status)
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False and output == before and status == before
    assert _canonical_truth_hash_integrity_bound(output["reports"]) is False


@pytest.mark.parametrize("digest", [None, "", "not-a-hash", "f" * 63, "g" * 64, "0" * 64])
def test_current_shortcut_does_not_repair_invalid_digest(digest) -> None:
    from nico.comprehensive_api_controller import _canonical_truth_hash_integrity_bound
    status = _current_hash_status()
    if digest is None:
        status["reports"].pop("canonical_truth_sha256")
    else:
        status["reports"]["canonical_truth_sha256"] = digest
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False and output == status
    assert _canonical_truth_hash_integrity_bound(output["reports"]) is False


@pytest.mark.parametrize("field,value", [
    ("pdf_sha256", "0" * 64),
    ("pdf_base64", "invalid-base64"),
    ("evidence_manifest_sha256", "0" * 64),
    ("artifact_manifest", {"manifest_id": "incomplete-tampered-manifest"}),
])
def test_current_digest_does_not_bypass_artifact_integrity(field, value) -> None:
    from nico.comprehensive_api_controller import (
        _canonical_truth_hash_integrity_bound, _final_report_package_integrity_bound,
    )
    status = _current_hash_status()
    assert _final_report_package_integrity_bound(status["reports"]) is True
    status["reports"][field] = value
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False and output == status
    assert _canonical_truth_hash_integrity_bound(output["reports"]) is True
    assert _final_report_package_integrity_bound(output["reports"]) is False


def test_current_digest_shortcut_preserves_copy_hooks_and_aliases(monkeypatch) -> None:
    class ChangingDict(dict):
        def __deepcopy__(self, memo):
            result = type(self)(generation=self["generation"] + 1)
            memo[id(self)] = result
            return result
    status = _current_hash_status()
    canonical = status["reports"]["json"]
    canonical["changing"] = ChangingDict(generation=0)
    shared = ["retained"]
    canonical["left"] = canonical["right"] = shared
    status["shared"] = shared
    observed = []
    original = compat._canonical_hash
    def record(value):
        observed.append(value["changing"]["generation"])
        return original(value)
    monkeypatch.setattr(compat, "_canonical_hash", record)
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False
    assert set(observed) == {3, 5}  # Initial hash, then recovery's two copies.
    assert output["reports"]["json"]["changing"]["generation"] == 1
    assert canonical["changing"]["generation"] == 0
    assert output["shared"] is output["reports"]["json"]["left"]
    assert output["shared"] is output["reports"]["json"]["right"]
    output["shared"].append("changed")
    assert shared == ["retained"]


def test_current_digest_probe_does_not_stringify_opaque_values(monkeypatch) -> None:
    calls = []
    class Opaque:
        def __str__(self):
            calls.append("str")
            return "opaque"
    status = {"reports": {"json": {"opaque": Opaque()}, "canonical_truth_sha256": "0" * 64}}
    def unexpected(*args):
        pytest.fail("opaque canonical value entered current-hash probe")
    monkeypatch.setattr(compat, "canonical_sha256", unexpected)
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False and calls == ["str"]
    assert output["reports"]["json"]["opaque"] is not status["reports"]["json"]["opaque"]


@pytest.mark.parametrize("kind", ["mapping", "tuple", "cycle", "alias"])
def test_non_tree_canonical_values_keep_legacy_path(monkeypatch, kind) -> None:
    from collections import UserDict
    value = {"retained": [1]}
    if kind == "mapping":
        value = UserDict(value)
    elif kind == "tuple":
        value = ([1],)
    elif kind == "cycle":
        value["self"] = value
    else:
        value["alias"] = value["retained"]
    # The legacy hash skips this subtree, including the cycle. The new probe must
    # not traverse it through a different serializer or introduce new exceptions.
    status = {"reports": {"json": {"html": value}, "canonical_truth_sha256": "0" * 64}}
    def unexpected(*args):
        pytest.fail("non-tree canonical graph entered current-hash probe")
    monkeypatch.setattr(compat, "canonical_sha256", unexpected)
    output, recovered = reconcile_known_post_render_hash_drift(status)
    assert recovered is False
    result = output["reports"]["json"]["html"]
    assert result is not value and type(result) is type(value)
    if kind == "cycle":
        assert result["self"] is result
    elif kind == "alias":
        assert result["alias"] is result["retained"]
    else:
        assert result == value
