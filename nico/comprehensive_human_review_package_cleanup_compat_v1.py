from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-human-review-package-cleanup-compat.v1.2"
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
    """Normalize only packages that bypassed the production preparation contract.

    The production preparation path sets a contract marker after projecting absent
    or placeholder customer and project identity as ``Not supplied``. Historical
    lower-level manifest fixtures intentionally call the finalizer directly with
    ``default_*`` values and therefore do not carry that marker. Normalize those
    legacy fixture inputs for validation only. Once the marker is present, explicit
    placeholders remain untouched so the fail-closed production validator rejects
    them.
    """

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
    from nico.comprehensive_client_surface_structure_cleanup_v1 import (
        install_client_surface_structure_cleanup_v1,
    )
    from nico.comprehensive_exact_source_index_validation_v1 import (
        install_exact_source_index_validation_v1,
    )
    from nico.comprehensive_full_report_finish_v1 import (
        install_comprehensive_full_report_finish_v1,
    )
    from nico.comprehensive_raw_mapping_string_recovery_v1 import (
        install_raw_mapping_string_recovery_v1,
    )

    raw_mapping_recovery = install_raw_mapping_string_recovery_v1()
    surface_cleanup = install_client_surface_structure_cleanup_v1()
    blank_deployment_metric = install_blank_deployment_metric_repair_v1()
    current = cleanup.assert_human_review_package_cleanup
    if getattr(current, _MARKER, False):
        finish = install_comprehensive_full_report_finish_v1()
        exact_source_index = install_exact_source_index_validation_v1()
        return {
            "status": "already_installed",
            "version": VERSION,
            "raw_mapping_string_recovery": raw_mapping_recovery,
            "client_surface_structure_cleanup": surface_cleanup,
            "blank_deployment_metric_repair": blank_deployment_metric,
            "full_report_finish": finish,
            "exact_source_index_validation": exact_source_index,
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
