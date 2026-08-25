from __future__ import annotations

from copy import deepcopy
from functools import wraps
from itertools import combinations
from typing import Any, Callable, Mapping


VERSION = "nico.comprehensive_canonical_truth_hash_compat.v1"
_BUILDER_MARKER = "_nico_canonical_truth_hash_compat_builder_v1"
_LOCALE_MARKER = "_nico_canonical_truth_hash_compat_locale_v1"
_RECONCILIATION = "known_post_render_stabilizer_metadata_v1"

# These fields are the bounded metadata that historical post-render stabilizers
# could add to report_package.json after the canonical truth hash had already been
# calculated. They are not assessment evidence and were not part of the frozen
# canonical object used to render the original Markdown/HTML/PDF artifacts.
_POST_RENDER_TRUE_KEYS = (
    "finding_register_deduplicated",
    "scanner_state_reconciled",
    "cross_format_score_truth_synchronized",
    "pre_render_truth_reconciliation",
)
_POST_RENDER_COUNT_KEYS = (
    "unique_finding_count",
    "exact_source_finding_count",
    "operational_finding_count",
)


def _canonical_hash(canonical: Mapping[str, Any]) -> str:
    from nico.comprehensive_report_package import _canonical_hash as report_hash

    return report_hash(canonical)


def synchronize_report_package_hash(result: dict[str, Any]) -> dict[str, Any]:
    """Bind the stored hash to the final canonical JSON that is actually persisted.

    The report builder can legitimately add deterministic presentation metadata after
    rendering. The persisted canonical JSON and its integrity hash must nevertheless
    describe the same object. This helper runs after the existing report-truth wrappers
    and changes no evidence, score, review, approval, or delivery state.
    """

    output = deepcopy(result)
    package = output.get("report_package")
    if not isinstance(package, dict):
        return output
    canonical = package.get("json")
    if not isinstance(canonical, Mapping) or not canonical:
        return output

    truth_sha256 = _canonical_hash(canonical)
    package["canonical_truth_sha256"] = truth_sha256
    output["canonical_truth_sha256"] = truth_sha256
    output["report_package"] = package
    return output


def _removable_known_post_render_keys(canonical: Mapping[str, Any]) -> tuple[str, ...]:
    """Return only known stabilizer fields whose values are valid for reconciliation."""

    removable: list[str] = []
    for key in _POST_RENDER_TRUE_KEYS:
        if canonical.get(key) is True:
            removable.append(key)

    for key in _POST_RENDER_COUNT_KEYS:
        value = canonical.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        removable.append(key)

    return tuple(removable)


def _reconstruct_exact_stored_truth(
    canonical: Mapping[str, Any], expected: str
) -> dict[str, Any] | None:
    """Find the unique exact-hash predecessor by removing only known metadata.

    Historical runs crossed more than one stabilizer revision, so an affected run may
    contain any non-empty subset of the seven known post-render fields. A field is
    removable only when its value matches the bounded stabilizer contract. Recovery is
    accepted only when exactly one candidate reproduces the immutable stored SHA-256.
    Unknown fields and known fields with unexpected values are never removed.
    """

    canonical_copy = deepcopy(dict(canonical))
    removable = _removable_known_post_render_keys(canonical_copy)
    if not removable:
        return None

    matches: list[dict[str, Any]] = []
    for count in range(1, len(removable) + 1):
        for keys in combinations(removable, count):
            candidate = deepcopy(canonical_copy)
            for key in keys:
                candidate.pop(key, None)
            if _canonical_hash(candidate) == expected:
                matches.append(candidate)
                if len(matches) > 1:
                    return None

    return matches[0] if len(matches) == 1 else None


def reconcile_known_post_render_hash_drift(
    status: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Recover bounded historical post-render canonical-hash drift.

    Older terminal runs may contain canonical JSON with a revision-dependent subset of
    seven deterministic metadata fields appended after the stored hash was calculated.
    We consider only removals of recognized stabilizer metadata with recognized values
    and accept recovery only when the reconstructed object exactly reproduces the
    immutable stored hash. Any unknown mismatch remains fail-closed.
    """

    output = deepcopy(dict(status))
    reports = output.get("reports")
    if not isinstance(reports, Mapping):
        return output, False
    reports_copy = deepcopy(dict(reports))
    canonical = reports_copy.get("json")
    if not isinstance(canonical, Mapping) or not canonical:
        return output, False

    expected = str(reports_copy.get("canonical_truth_sha256") or "").strip()
    if not expected:
        return output, False

    canonical_copy = deepcopy(dict(canonical))
    if _canonical_hash(canonical_copy) == expected:
        return output, False

    candidate = _reconstruct_exact_stored_truth(canonical_copy, expected)
    if candidate is None:
        return output, False

    reports_copy["json"] = candidate
    output["reports"] = reports_copy
    return output, True


def _install_builder_hash_sync() -> bool:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_native_providers as providers

    current: Callable[..., dict[str, Any]] = report.build_comprehensive_report_package
    if getattr(current, _BUILDER_MARKER, False):
        providers.build_comprehensive_report_package = current
        return providers.build_comprehensive_report_package is current

    @wraps(current)
    def build_package(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        return synchronize_report_package_hash(result) if isinstance(result, dict) else result

    setattr(build_package, _BUILDER_MARKER, True)
    setattr(build_package, "_nico_previous", current)
    report.build_comprehensive_report_package = build_package
    providers.build_comprehensive_report_package = build_package
    return (
        report.build_comprehensive_report_package is build_package
        and providers.build_comprehensive_report_package is build_package
    )


def _install_same_run_recovery() -> bool:
    from nico import comprehensive_same_run_locale_report_v1 as same_run

    current: Callable[[Mapping[str, Any], str], dict[str, Any]] = (
        same_run.build_same_run_locale_report
    )
    if getattr(current, _LOCALE_MARKER, False):
        return same_run.build_same_run_locale_report is current

    @wraps(current)
    def build_locale_report(
        status: Mapping[str, Any], report_language: str
    ) -> dict[str, Any]:
        reconciled_status, recovered = reconcile_known_post_render_hash_drift(status)
        result = current(reconciled_status, report_language)
        if not recovered:
            return result

        output = deepcopy(result)
        output["canonical_truth_hash_reconciled"] = True
        output["canonical_truth_hash_reconciliation"] = _RECONCILIATION
        report = output.get("report")
        if isinstance(report, dict):
            report["canonical_truth_hash_reconciled"] = True
            report["canonical_truth_hash_reconciliation"] = _RECONCILIATION
        return output

    setattr(build_locale_report, _LOCALE_MARKER, True)
    setattr(build_locale_report, "_nico_previous", current)
    same_run.build_same_run_locale_report = build_locale_report
    return same_run.build_same_run_locale_report is build_locale_report


def install_canonical_truth_hash_compat() -> dict[str, Any]:
    builder_bound = _install_builder_hash_sync()
    locale_recovery_bound = _install_same_run_recovery()
    return {
        "artifact_schema": VERSION,
        "builder_hash_sync_bound": builder_bound,
        "same_run_legacy_recovery_bound": locale_recovery_bound,
        "future_report_hash_synchronized": builder_bound,
        "legacy_post_render_hash_drift_recoverable": locale_recovery_bound,
        "reconciliation": _RECONCILIATION,
        "unknown_hash_mismatch_fails_closed": True,
        "assessment_rerun": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_canonical_truth_hash_compat",
    "reconcile_known_post_render_hash_drift",
    "synchronize_report_package_hash",
]
