from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from nico.full_report_artifact_identity_v4 import build_full_artifact_manifest, validate_download_response
from nico.full_report_delivery_contract_v1 import attach_delivery_contract
from nico.full_report_download_response_v1 import attach_download_responses
from nico.full_report_production_release_v4 import build_full_release_manifest

VERSION = "full_report_release_pipeline_v1"
FORMATS = ("pdf", "html", "markdown")


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def build_full_release_pipeline(
    report: Mapping[str, Any],
    *,
    pages: Iterable[Any],
    exports: Mapping[str, Any],
    assessment_id: str,
    locale: str,
    human_review_complete: bool = False,
) -> dict[str, Any]:
    """Execute the Full report release chain and preserve every fail-closed gate."""

    result = build_full_release_manifest(
        deepcopy(dict(report)),
        pages=pages,
        locale=locale,
        exports=dict(exports),
        human_review_complete=human_review_complete,
    )
    result["full_artifact_manifest"] = build_full_artifact_manifest(
        result,
        exports,
        assessment_id=assessment_id,
        locale=locale,
    )
    attach_delivery_contract(result, assessment_id=assessment_id)
    attach_download_responses(result, assessment_id=assessment_id)

    response_issues: dict[str, list[str]] = {}
    artifact_records = _mapping(result.get("full_artifact_manifest")).get("artifacts") or {}
    response_records = _mapping(result.get("full_download_responses")).get("formats") or {}
    for report_format in FORMATS:
        artifact = _mapping(artifact_records.get(report_format))
        response = _mapping(response_records.get(report_format))
        validation = list(validate_download_response(artifact, _mapping(response.get("headers"))))
        if validation:
            response_issues[report_format] = validation

    prior_allowed = bool(result.get("client_delivery_allowed"))
    pipeline_allowed = prior_allowed and not response_issues
    result["full_release_pipeline"] = {
        "version": VERSION,
        "assessment_id": str(assessment_id),
        "locale": str(locale),
        "formats": list(FORMATS),
        "response_validation_issues": response_issues,
        "all_gates_passed": pipeline_allowed,
        "client_delivery_allowed": pipeline_allowed,
        "human_review_complete": bool(human_review_complete),
    }
    result["client_delivery_allowed"] = pipeline_allowed
    return result


__all__ = ["FORMATS", "VERSION", "build_full_release_pipeline"]
