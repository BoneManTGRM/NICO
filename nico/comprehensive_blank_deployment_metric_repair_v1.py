from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-blank-deployment-metric-repair.v1"
_MARKER = "__nico_blank_deployment_metric_repair_v1__"
_STAGE_MARKER = "__nico_blank_deployment_metric_stage_repair_v1__"

_BLANK_NON_SUCCESS_METRIC = re.compile(
    r"^(?P<prefix>[ \t]*[-*]?[ \t]*)"
    r"(?:non-success deployments|non-success deployment classification)"
    r"[ \t]*:[ \t]*[.\-–—_:;|/\\]*[ \t]*$",
    re.IGNORECASE,
)
_REPLACEMENT = "Non-success deployment classification: Not available."
_STAGE_FIELDS = ("summary", "evidence", "findings", "unavailable", "limitations")


def normalize_blank_non_success_deployment_metric(value: Any) -> Any:
    """Replace only an explicitly blank client-facing deployment metric.

    Missing deployment outcome evidence remains missing. The renderer states that
    boundary as ``Not available`` instead of publishing an empty label. Numeric or
    descriptive values are preserved byte-for-byte, and the final publication gate
    still rejects any blank metric that bypasses this projection.
    """

    if not isinstance(value, str):
        return value
    candidate = " ".join(value.split()) if "\n" in value or "\r" in value else value
    match = _BLANK_NON_SUCCESS_METRIC.fullmatch(candidate)
    if not match:
        return value
    return f"{match.group('prefix')}{_REPLACEMENT}"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_blank_non_success_deployment_metric(value)
    if isinstance(value, Mapping):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    if isinstance(value, set):
        return {_normalize_value(item) for item in value}
    return value


def sanitize_blank_deployment_metric_stage(
    stage: Mapping[str, Any],
) -> dict[str, Any]:
    """Repair the known blank label only on client-facing stage fields."""

    result = deepcopy(dict(stage))
    for field in _STAGE_FIELDS:
        if field in result:
            result[field] = _normalize_value(result[field])
    return result


def project_blank_deployment_metrics(package: Mapping[str, Any]) -> dict[str, Any]:
    """Project repaired stage summaries without changing raw scanner evidence."""

    result = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(result.get("json") or {}))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )

    sources = (
        canonical.get("stage_summaries"),
        assessment.get("stage_summaries"),
    )
    stages: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, list):
            continue
        stages = [
            sanitize_blank_deployment_metric_stage(item)
            for item in source
            if isinstance(item, Mapping)
        ]
        if stages:
            break
    if stages:
        canonical["stage_summaries"] = deepcopy(stages)
        assessment["stage_summaries"] = deepcopy(stages)

    sections = assessment.get("sections")
    if isinstance(sections, list):
        assessment["sections"] = [
            sanitize_blank_deployment_metric_stage(item)
            for item in sections
            if isinstance(item, Mapping)
        ]

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "blank_deployment_metric_repair_version": VERSION,
            "blank_non_success_deployment_metric_renders_not_available": True,
            "known_values_preserved": True,
            "raw_scanner_evidence_unchanged": True,
            "scores_unchanged": True,
            "candidate_dispositions_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    canonical["assessment"] = assessment
    result["json"] = canonical
    return result


def install_blank_deployment_metric_repair_v1() -> dict[str, Any]:
    """Bind the repair to every shared client-surface stage projection."""

    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current_humanize = surface.humanize_client_surface_value
    if not getattr(current_humanize, _MARKER, False):
        @wraps(current_humanize)
        def humanize(value: Any, *, item_limit: int = 700) -> str:
            rendered = current_humanize(value, item_limit=item_limit)
            return str(normalize_blank_non_success_deployment_metric(rendered))

        setattr(humanize, _MARKER, True)
        setattr(humanize, "_nico_previous", current_humanize)
        surface.humanize_client_surface_value = humanize

    current_surface_stage = surface.sanitize_client_rendered_stage
    if not getattr(current_surface_stage, _STAGE_MARKER, False):
        @wraps(current_surface_stage)
        def surface_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
            return sanitize_blank_deployment_metric_stage(current_surface_stage(stage))

        setattr(surface_stage, _STAGE_MARKER, True)
        setattr(surface_stage, "_nico_previous", current_surface_stage)
        surface.sanitize_client_rendered_stage = surface_stage

    current_cleanup_stage = cleanup.sanitize_rendered_stage
    if not getattr(current_cleanup_stage, _STAGE_MARKER, False):
        @wraps(current_cleanup_stage)
        def cleanup_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
            return sanitize_blank_deployment_metric_stage(current_cleanup_stage(stage))

        setattr(cleanup_stage, _STAGE_MARKER, True)
        setattr(cleanup_stage, "_nico_previous", current_cleanup_stage)
        cleanup.sanitize_rendered_stage = cleanup_stage

    return {
        "status": "installed",
        "version": VERSION,
        "shared_humanizer_bound": getattr(
            surface.humanize_client_surface_value, _MARKER, False
        ),
        "surface_stage_projection_bound": getattr(
            surface.sanitize_client_rendered_stage, _STAGE_MARKER, False
        ),
        "cleanup_stage_projection_bound": getattr(
            cleanup.sanitize_rendered_stage, _STAGE_MARKER, False
        ),
        "blank_metric_validator_preserved": True,
        "known_values_preserved": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_blank_deployment_metric_repair_v1",
    "normalize_blank_non_success_deployment_metric",
    "project_blank_deployment_metrics",
    "sanitize_blank_deployment_metric_stage",
]
