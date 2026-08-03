from __future__ import annotations

from typing import Any, Mapping

from nico import v2_automated_draft_quality_compat_v1 as projection
from nico import v2_automated_draft_quality_compat_v2 as compatibility

VERSION = "nico.v2.automated-draft-quality-compat.v3"


def install_automated_draft_quality_compat() -> dict[str, Any]:
    """Bind lifecycle compatibility first and scorecard extraction safety last.

    The compatibility repair must replace obsolete finality copy before validation,
    but its installer also rebinds the legacy raw-substring scorecard validator.
    Production therefore has to reassert the extraction-order-safe, multi-page
    scorecard validator after every compatibility installation request.
    """

    compatibility_state = dict(compatibility.install_automated_draft_quality_compat())
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    scorecard_state = dict(install_scorecard_extraction_validation())
    return {
        **compatibility_state,
        "version": VERSION,
        "scorecard_extraction_validation": scorecard_state,
        "scorecard_extraction_validation_reasserted_last": True,
        "wrapped_label_normalization_enabled": (
            scorecard_state.get("wrapped_label_normalization_enabled") is True
        ),
        "multi_page_scorecard_supported": (
            scorecard_state.get("multi_page_scorecard_supported") is True
        ),
        "all_canonical_rows_and_scores_required": (
            scorecard_state.get("all_canonical_rows_and_scores_required") is True
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _project(delegate_result: Mapping[str, Any]) -> dict[str, Any]:
    result = projection._project_result(delegate_result)
    contract = dict(result.get("premium_report_renderer") or {})
    contract.update(
        {
            "automated_draft_quality_compat_version": VERSION,
            "scorecard_extraction_validation_reasserted_last": True,
            "wrapped_label_normalization_enabled": True,
            "multi_page_scorecard_supported": True,
            "all_canonical_rows_and_scores_required": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["premium_report_renderer"] = contract
    return result


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    # Call the runtime delegate directly. Calling the older compatibility wrapper
    # would reinstall its raw-substring validator after the scorecard validator.
    from nico.v2_report_quality_runtime_compat import repair_rendered_report as delegate

    return _project(delegate(package))


def repair_localized_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    from nico.v2_localized_report_quality_repairs import (
        repair_localized_rendered_report as delegate,
    )

    return _project(delegate(package))


__all__ = [
    "VERSION",
    "install_automated_draft_quality_compat",
    "repair_localized_rendered_report",
    "repair_rendered_report",
]
