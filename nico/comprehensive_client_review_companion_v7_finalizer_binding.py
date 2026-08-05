from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-client-review-companion.v7-finalizer-binding"
_MARKER = "__nico_comprehensive_review_companion_v7_finalizer_binding__"


def install_comprehensive_review_companion_v7_finalizer_binding() -> dict[str, Any]:
    """Reassert the paired renderer at the exact finalization boundary."""

    from nico import client_report_completion_v2 as completion
    from nico.comprehensive_client_review_companion_v7_rebind import (
        install_comprehensive_review_companion_v7_rebind,
    )

    current = completion.finalize_client_report_package
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "exact_finalizer_boundary_bound": True,
        }

    @wraps(current)
    def finalize(package: Mapping[str, Any]) -> dict[str, Any]:
        install_comprehensive_review_companion_v7_rebind()
        return dict(current(package))

    setattr(finalize, _MARKER, True)
    setattr(finalize, "_nico_previous", current)
    completion.finalize_client_report_package = finalize
    return {
        "status": "installed",
        "version": VERSION,
        "exact_finalizer_boundary_bound": (
            completion.finalize_client_report_package is finalize
        ),
        "paired_renderer_reasserted_per_finalization": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_review_companion_v7_finalizer_binding",
]
