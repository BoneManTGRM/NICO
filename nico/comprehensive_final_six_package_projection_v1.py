from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from nico.comprehensive_final_six_client_report_cleanup_v1 import (
    expose_candidate_penalty_basis,
)

VERSION = "nico.comprehensive-final-six-package-projection.v1"
_MARKER = "__nico_comprehensive_final_six_package_projection_v1__"


def _eligible(canonical: Mapping[str, Any]) -> bool:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    contract = (
        assessment.get("score_contract")
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    register = assessment.get("canonical_scanner_finding_register")
    return (
        "candidate_volume_penalty" in contract
        and isinstance(register, Mapping)
        and isinstance(register.get("summary_by_category"), Mapping)
    )


def project_final_six_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Expose existing score arithmetic before final client rendering."""

    result = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(result.get("json") or {}))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
    if _eligible(canonical):
        result["json"] = expose_candidate_penalty_basis(canonical)
    return result


def install_final_six_package_projection_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current = completion.prepare_client_report_package
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "prepare_projection_bound": True,
        }

    @wraps(current)
    def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
        return project_final_six_package(current(package))

    setattr(prepare, _MARKER, True)
    setattr(prepare, "_nico_previous", current)
    completion.prepare_client_report_package = prepare
    return {
        "status": "installed",
        "version": VERSION,
        "prepare_projection_bound": completion.prepare_client_report_package is prepare,
        "score_values_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_final_six_package_projection_v1",
    "project_final_six_package",
]
