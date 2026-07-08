from __future__ import annotations

import inspect
from typing import Any

REPORT_TRUTH_GUARD_VERSION = "pr145-report-rebuild-after-truth-guard-v1"
REPORT_TRUTH_GUARD_EXPECTED_BUILD_COMMIT = "4395fe0744c4219d4f27a1d80c53ca18886420f1"
REQUIRED_REPORT_TRUTH_MARKERS = [
    "dependency_truth_guard_before_exports",
    "markdown_html_pdf_rebuilt_after_truth_guard",
    "malformed_pyjwt_extra_not_accepted_as_confirmed_vulnerability",
    "green_90_blocked_when_osv_or_malformed_osv_unresolved",
    "project_trend_score_refreshed_after_recompute",
]


def _function_source_contains(function: Any, marker: str) -> bool:
    try:
        return marker in inspect.getsource(function)
    except (OSError, TypeError):
        return False


def build_report_truth_status() -> dict[str, Any]:
    from nico import final_report_consistency
    from nico import report_truth_runtime_patch

    finalize = final_report_consistency.finalize_express_result_consistency
    patched_original = getattr(final_report_consistency, "_nico_original_finalize_express_result_consistency", None)
    has_runtime_patch = patched_original is not None
    uses_runtime_rebuild = _function_source_contains(
        report_truth_runtime_patch.rebuild_reports,
        "_rebuild_reports",
    )
    has_dependency_guard = hasattr(report_truth_runtime_patch, "apply_dependency_score_consistency")
    has_malformed_extra_guard = hasattr(report_truth_runtime_patch, "MALFORMED_EXTRA_OSV_RE")
    guard_active = bool(has_runtime_patch and uses_runtime_rebuild and has_dependency_guard and has_malformed_extra_guard)
    return {
        "status": "ok" if guard_active else "stale_or_incomplete",
        "version": REPORT_TRUTH_GUARD_VERSION,
        "expected_build_commit": REPORT_TRUTH_GUARD_EXPECTED_BUILD_COMMIT,
        "required_markers": REQUIRED_REPORT_TRUTH_MARKERS,
        "guard_active": guard_active,
        "checks": {
            "finalizer_runtime_patch_installed": has_runtime_patch,
            "report_rebuild_uses_core_rebuild_reports": uses_runtime_rebuild,
            "dependency_score_consistency_guard_available": has_dependency_guard,
            "malformed_python_extra_osv_guard_available": has_malformed_extra_guard,
            "active_finalizer_name": getattr(finalize, "__name__", "unknown"),
        },
        "rule": "If this status is missing, stale_or_incomplete, or expected_build_commit does not match deployment diagnostics, the hosted backend has not redeployed the report truth guard and new reports should not be trusted for score changes.",
    }
