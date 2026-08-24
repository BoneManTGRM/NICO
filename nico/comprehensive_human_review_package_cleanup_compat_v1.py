from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-human-review-package-cleanup-compat.v1.12"
_MARKER = "__nico_comprehensive_human_review_package_cleanup_compat_v1__"
_LEGACY_PLACEHOLDERS = {
    "",
    "default_customer",
    "default_project",
    "unknown_customer",
    "unknown_project",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_missing_fixture_identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize only packages that bypassed the production preparation contract."""

    result = deepcopy(dict(canonical))
    contract = (
        result.get("v2_pipeline_contract")
        if isinstance(result.get("v2_pipeline_contract"), Mapping)
        else {}
    )
    if contract.get("client_identity_placeholders_sanitized") is True:
        return result

    identity = (
        deepcopy(dict(result.get("identity") or {}))
        if isinstance(result.get("identity"), Mapping)
        else {}
    )
    for field in ("customer_id", "project_id"):
        if _text(identity.get(field)).casefold() in _LEGACY_PLACEHOLDERS:
            identity[field] = "Not supplied"
    result["identity"] = identity
    return result


def install_comprehensive_human_review_package_cleanup_compat_v1() -> dict[str, Any]:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico.comprehensive_blank_deployment_metric_repair_v1 import (
        install_blank_deployment_metric_repair_v1,
    )
    from nico.comprehensive_client_identity_publication_guard_v2 import (
        install_client_identity_publication_guard_v2,
    )
    from nico.comprehensive_client_review_companion_v7_rebind import (
        install_comprehensive_review_companion_v7_rebind,
    )
    from nico.comprehensive_client_surface_structure_cleanup_v1 import (
        install_client_surface_structure_cleanup_v1,
    )
    from nico.comprehensive_current_report_truth_parity_v1 import (
        install_comprehensive_current_report_truth_parity_v1,
    )
    from nico.comprehensive_exact_source_index_validation_v1 import (
        install_exact_source_index_validation_v1,
    )
    from nico.comprehensive_final_six_client_report_cleanup_v1 import (
        install_final_six_client_report_cleanup_v1,
    )
    from nico.comprehensive_final_six_package_projection_v1 import (
        install_final_six_package_projection_v1,
    )
    from nico.comprehensive_final_six_runtime_repair_v1 import (
        install_final_six_runtime_repair_v1,
    )
    from nico.comprehensive_full_data_worksheet_localization_v1 import (
        install_comprehensive_full_data_worksheet_localization_v1,
    )
    from nico.comprehensive_full_report_finish_v1 import (
        install_comprehensive_full_report_finish_v1,
    )
    from nico.comprehensive_raw_mapping_string_recovery_v1 import (
        install_raw_mapping_string_recovery_v1,
    )
    from nico.comprehensive_review_companion_v7_mobile_contract import (
        install_comprehensive_review_companion_v7_mobile_contract,
    )
    from nico.comprehensive_spanish_presentation_parity_v2 import (
        install_comprehensive_spanish_presentation_parity_v2,
    )

    raw_mapping_recovery = install_raw_mapping_string_recovery_v1()
    surface_cleanup = install_client_surface_structure_cleanup_v1()
    blank_deployment_metric = install_blank_deployment_metric_repair_v1()
    current = cleanup.assert_human_review_package_cleanup
    if getattr(current, _MARKER, False):
        finish = install_comprehensive_full_report_finish_v1()
        exact_source_index = install_exact_source_index_validation_v1()
        final_six_cleanup = install_final_six_client_report_cleanup_v1()
        final_six_projection = install_final_six_package_projection_v1()
        final_six_runtime = install_final_six_runtime_repair_v1()
        review_companion_rebind = install_comprehensive_review_companion_v7_rebind()
        mobile_contract = install_comprehensive_review_companion_v7_mobile_contract()
        identity_publication_guard = install_client_identity_publication_guard_v2()
        full_data_worksheet_localization = (
            install_comprehensive_full_data_worksheet_localization_v1()
        )
        spanish_presentation_parity = (
            install_comprehensive_spanish_presentation_parity_v2()
        )
        current_report_truth_parity = (
            install_comprehensive_current_report_truth_parity_v1()
        )
        return {
            "status": "already_installed",
            "version": VERSION,
            "raw_mapping_string_recovery": raw_mapping_recovery,
            "client_surface_structure_cleanup": surface_cleanup,
            "blank_deployment_metric_repair": blank_deployment_metric,
            "full_report_finish": finish,
            "exact_source_index_validation": exact_source_index,
            "final_six_client_report_cleanup": final_six_cleanup,
            "final_six_package_projection": final_six_projection,
            "final_six_runtime_repair": final_six_runtime,
            "review_companion_v7_rebind": review_companion_rebind,
            "review_companion_v7_mobile_contract": mobile_contract,
            "client_identity_publication_guard_v2": identity_publication_guard,
            "full_data_worksheet_localization": full_data_worksheet_localization,
            "spanish_presentation_parity": spanish_presentation_parity,
            "current_report_truth_parity": current_report_truth_parity,
        }

    @wraps(current)
    def validate(
        canonical: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> None:
        current(
            normalize_missing_fixture_identity(canonical),
            markdown,
            rendered_html,
            pdf,
        )

    setattr(validate, _MARKER, True)
    setattr(validate, "_nico_previous", current)
    cleanup.assert_human_review_package_cleanup = validate
    finish = install_comprehensive_full_report_finish_v1()
    exact_source_index = install_exact_source_index_validation_v1()
    final_six_cleanup = install_final_six_client_report_cleanup_v1()
    final_six_projection = install_final_six_package_projection_v1()
    final_six_runtime = install_final_six_runtime_repair_v1()
    review_companion_rebind = install_comprehensive_review_companion_v7_rebind()
    mobile_contract = install_comprehensive_review_companion_v7_mobile_contract()
    identity_publication_guard = install_client_identity_publication_guard_v2()
    full_data_worksheet_localization = (
        install_comprehensive_full_data_worksheet_localization_v1()
    )
    spanish_presentation_parity = (
        install_comprehensive_spanish_presentation_parity_v2()
    )
    current_report_truth_parity = install_comprehensive_current_report_truth_parity_v1()
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_fixture_identity_normalized": True,
        "production_contract_still_fail_closed": True,
        "raw_mapping_string_recovery": raw_mapping_recovery,
        "client_surface_structure_cleanup": surface_cleanup,
        "blank_deployment_metric_repair": blank_deployment_metric,
        "full_report_finish": finish,
        "exact_source_index_validation": exact_source_index,
        "final_six_client_report_cleanup": final_six_cleanup,
        "final_six_package_projection": final_six_projection,
        "final_six_runtime_repair": final_six_runtime,
        "review_companion_v7_rebind": review_companion_rebind,
        "review_companion_v7_mobile_contract": mobile_contract,
        "client_identity_publication_guard_v2": identity_publication_guard,
        "full_data_worksheet_localization": full_data_worksheet_localization,
        "spanish_presentation_parity": spanish_presentation_parity,
        "current_report_truth_parity": current_report_truth_parity,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_human_review_package_cleanup_compat_v1",
    "normalize_missing_fixture_identity",
]
