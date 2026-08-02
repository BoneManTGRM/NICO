from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth,
)

VERSION = "nico.comprehensive_final_register_scanner_truth.v62"
_MARKER = "_nico_comprehensive_final_register_scanner_truth_v62"


def install_comprehensive_final_register_scanner_truth_v62() -> dict[str, Any]:
    """Bind exact-run scanner truth to the last canonical register installation.

    The premium finalizer invokes ``client_report_completion_v2._install_register``
    after legacy rendering and normalization passes. Binding here prevents those late
    passes from reintroducing stale analyzer coverage or incomplete-scanner aliases
    into the canonical JSON that is used for final cross-format verification.
    """

    from nico import client_report_completion_v2 as completion

    current: Callable[[dict[str, Any]], dict[str, Any]] = completion._install_register
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def install_register(canonical: dict[str, Any]) -> dict[str, Any]:
        registered = current(canonical)
        return reconcile_authoritative_scanner_truth(registered)

    setattr(install_register, _MARKER, True)
    setattr(install_register, "_nico_previous", current)
    completion._install_register = install_register
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion._install_register is install_register,
        "final_register_uses_exact_run_scanner_records": True,
        "live_requested_tool_manifest_is_coverage_denominator": True,
        "late_stale_coverage_aliases_reconciled": True,
        "failed_requested_scanners_remain_incomplete": True,
        "report_renderer_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_register_scanner_truth_v62",
]
