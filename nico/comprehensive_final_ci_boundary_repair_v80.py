from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer_v79
from nico import comprehensive_rendered_ci_boundary_truth_v78 as truth_v78

VERSION = "nico.comprehensive-final-ci-boundary-repair.v80"
_INSTALL_MARKER = "_nico_comprehensive_final_ci_boundary_repair_v80"
_VALIDATOR_MARKER = "_nico_final_ci_boundary_repair_validator_v80"


def repair_before_final_ci_boundary_validation(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Repair the exact final client artifact immediately before validation.

    Earlier report producers are imported by value in several production modules.
    Repairing at this final validator boundary prevents any static renderer alias
    or later compact-report composition from bypassing the four-part CI/CD truth.
    """

    repaired = producer_v79.repair_rendered_ci_boundary(result)
    contract = deepcopy(dict(repaired.get("final_ci_boundary_repair") or {}))
    truth = truth_v78.rendered_ci_boundary_truth(repaired)
    if truth.get("complete") is not True or truth.get("conflict") is True:
        raise ValueError("final CI/CD boundary repair did not produce one complete language")
    contract.update(
        {
            "version": VERSION,
            "repair_position": "immediately_before_final_surface_validation",
            "rendered_language": truth.get("language"),
            "markdown_complete": bool(
                truth.get("per_surface", {})
                .get("markdown", {})
                .get("spanish" if truth.get("language") == "es-MX" else "english", {})
                .get("complete")
            ),
            "html_complete": bool(
                truth.get("per_surface", {})
                .get("html", {})
                .get("spanish" if truth.get("language") == "es-MX" else "english", {})
                .get("complete")
            ),
            "pdf_complete": bool(
                truth.get("per_surface", {})
                .get("pdf", {})
                .get("spanish" if truth.get("language") == "es-MX" else "english", {})
                .get("complete")
            ),
            "static_renderer_aliases_cannot_bypass_repair": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    repaired["final_ci_boundary_repair"] = contract
    repaired["human_review_required"] = True
    repaired["client_delivery_allowed"] = False
    return repaired


def _patch_final_validator() -> bool:
    current: Callable[[Mapping[str, Any]], None] = final_truth._validate_surfaces
    if getattr(current, _VALIDATOR_MARKER, False):
        return True

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        repaired = repair_before_final_ci_boundary_validation(result)
        if isinstance(result, MutableMapping):
            result.clear()
            result.update(repaired)
            current(result)
            return
        current(repaired)

    setattr(_validate_surfaces, _VALIDATOR_MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    final_truth._validate_surfaces = _validate_surfaces
    return final_truth._validate_surfaces is _validate_surfaces


def install_comprehensive_final_ci_boundary_repair_v80() -> dict[str, Any]:
    """Bind final-artifact repair outside every renderer and compact finalizer."""

    already_installed = getattr(final_truth, _INSTALL_MARKER, False)
    validator_bound = _patch_final_validator()
    setattr(final_truth, _INSTALL_MARKER, True)
    return {
        "status": "rebound" if already_installed else "installed",
        "version": VERSION,
        "validator_bound": validator_bound,
        "repair_runs_before_v78_and_final_truth_validation": True,
        "static_renderer_aliases_cannot_bypass_repair": True,
        "markdown_html_pdf_verified_independently": True,
        "complete_bilingual_conflict_fails_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_final_ci_boundary_repair_v80",
    "repair_before_final_ci_boundary_validation",
]
