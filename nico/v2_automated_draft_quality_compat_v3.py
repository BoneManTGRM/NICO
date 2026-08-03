from __future__ import annotations

from typing import Any, Mapping

from nico import v2_automated_draft_quality_compat_v1 as projection
from nico import v2_automated_draft_quality_compat_v2 as compatibility

VERSION = "nico.v2.automated-draft-quality-compat.v3"
_MARKER = "__nico_automated_draft_scorecard_validation_v3__"


def validate_final_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    expected_sections: list[Mapping[str, Any]],
    spanish: bool,
) -> None:
    """Apply lifecycle/identity gates and extraction-safe scorecard parity.

    The automated-draft validator owns PDF validity, control-character, lifecycle,
    human-review, delivery, and immutable-identity checks. It is deliberately called
    without sections because its legacy scorecard check used exact substrings from
    only the title page. The existing scorecard validator then verifies the complete
    renderer-derived page range with order-independent token parity.
    """

    projection._validate_review_pdf(
        pdf,
        canonical,
        expected_sections=[],
        spanish=spanish,
    )
    if expected_sections:
        from nico.scorecard_extraction_validation_v1 import _verify_all_rows

        _verify_all_rows(pdf, canonical, expected_sections)


def install_automated_draft_quality_compat() -> dict[str, Any]:
    """Bind lifecycle compatibility first and the combined validator last."""

    compatibility_state = dict(compatibility.install_automated_draft_quality_compat())
    from nico import v2_localized_report_quality_repairs as localized
    from nico import v2_report_quality_repairs as quality
    from nico import v2_report_quality_runtime_compat as runtime_compat
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    scorecard_state = dict(install_scorecard_extraction_validation())
    setattr(validate_final_pdf, _MARKER, True)
    quality._validate_final_pdf = validate_final_pdf
    runtime_compat._validate_final_pdf = validate_final_pdf
    localized._validate_final_pdf = validate_final_pdf
    return {
        **compatibility_state,
        "version": VERSION,
        "scorecard_extraction_validation": scorecard_state,
        "combined_lifecycle_and_scorecard_validator_bound": True,
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
        "legacy_raw_substring_scorecard_validator_bypassed": True,
        "automated_draft_lifecycle_validator_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _project(delegate_result: Mapping[str, Any]) -> dict[str, Any]:
    result = projection._project_result(delegate_result)
    contract = dict(result.get("premium_report_renderer") or {})
    contract.update(
        {
            "automated_draft_quality_compat_version": VERSION,
            "combined_lifecycle_and_scorecard_validator_bound": True,
            "scorecard_extraction_validation_reasserted_last": True,
            "wrapped_label_normalization_enabled": True,
            "multi_page_scorecard_supported": True,
            "all_canonical_rows_and_scores_required": True,
            "legacy_raw_substring_scorecard_validator_bypassed": True,
            "automated_draft_lifecycle_validator_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["premium_report_renderer"] = contract
    return result


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    # Call the runtime delegate directly. Calling an older compatibility wrapper
    # would reinstall its raw-substring validator after the combined validator.
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
    "validate_final_pdf",
]
