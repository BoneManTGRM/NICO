from __future__ import annotations

import inspect
from typing import Any

REPORT_TRUTH_GUARD_VERSION = "final-hosted-truth-gate-v2"
REPORT_TRUTH_GUARD_EXPECTED_BUILD_MARKER = "nico-final-hosted-truth-gate"
REQUIRED_REPORT_TRUTH_MARKERS = [
    "dependency_truth_guard_before_exports",
    "markdown_html_pdf_rebuilt_after_truth_guard",
    "malformed_pyjwt_extra_not_accepted_as_confirmed_vulnerability",
    "green_90_blocked_when_osv_or_malformed_osv_unresolved",
    "project_trend_score_refreshed_after_recompute",
    "final_client_acceptance_delivery_gate",
]


def _function_source_contains(function: Any, marker: str) -> bool:
    try:
        return marker in inspect.getsource(function)
    except (OSError, TypeError):
        return False


def build_report_truth_status() -> dict[str, Any]:
    from nico import client_acceptance, final_report_consistency, report_truth_runtime_patch
    from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate

    finalize = final_report_consistency.finalize_express_result_consistency
    patched_original = getattr(final_report_consistency, "_nico_original_finalize_express_result_consistency", None)
    client_gate_original = getattr(client_acceptance, "_nico_original_attach_client_acceptance_gate", None)
    has_runtime_patch = patched_original is not None
    has_client_delivery_gate = client_gate_original is not None
    uses_runtime_rebuild = _function_source_contains(
        report_truth_runtime_patch.rebuild_reports,
        "_rebuild_reports",
    )
    final_gate_uses_rebuild = _function_source_contains(apply_final_hosted_truth_gate, "rebuild_reports")
    has_dependency_guard = hasattr(report_truth_runtime_patch, "apply_dependency_score_consistency")
    has_malformed_extra_guard = hasattr(report_truth_runtime_patch, "MALFORMED_EXTRA_OSV_RE")
    guard_active = bool(
        has_runtime_patch
        and has_client_delivery_gate
        and uses_runtime_rebuild
        and final_gate_uses_rebuild
        and has_dependency_guard
        and has_malformed_extra_guard
    )
    return {
        "status": "ok" if guard_active else "stale_or_incomplete",
        "version": REPORT_TRUTH_GUARD_VERSION,
        "expected_build_marker": REPORT_TRUTH_GUARD_EXPECTED_BUILD_MARKER,
        "required_markers": REQUIRED_REPORT_TRUTH_MARKERS,
        "guard_active": guard_active,
        "checks": {
            "finalizer_runtime_patch_installed": has_runtime_patch,
            "client_acceptance_delivery_gate_installed": has_client_delivery_gate,
            "report_rebuild_uses_core_rebuild_reports": uses_runtime_rebuild,
            "final_delivery_gate_rebuilds_reports": final_gate_uses_rebuild,
            "dependency_score_consistency_guard_available": has_dependency_guard,
            "malformed_python_extra_osv_guard_available": has_malformed_extra_guard,
            "active_finalizer_name": getattr(finalize, "__name__", "unknown"),
            "active_client_acceptance_gate_name": getattr(client_acceptance.attach_client_acceptance_gate, "__name__", "unknown"),
        },
        "rule": "If this status is missing or stale_or_incomplete, the hosted backend has not loaded the final hosted report truth gate and new reports should not be trusted for score-change testing.",
    }
