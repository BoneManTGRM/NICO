from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-client-surface-structure-cleanup.v1"
_MARKER = "__nico_comprehensive_client_surface_structure_cleanup_v1__"
_FINAL_TRUTH_EVIDENCE_MARKER = "__nico_final_truth_structured_evidence_v1__"
_STAGE_SANITIZER_MARKER = "__nico_structured_stage_sanitizer_v1__"
_PREMIUM_MARKER = "__nico_premium_structured_line_cleanup_v1__"
_PREMIUM_STAGE_MARKER = "__nico_premium_structured_stage_population_v1__"
_PREMIUM_ENTRYPOINT_MARKER = "__nico_premium_structured_entrypoint_cleanup_v1__"
_DIAGNOSTIC_MARKER = "__nico_raw_mapping_surface_diagnostic_v1__"
_CLIENT_STAGE_FIELDS = ("evidence", "findings", "unavailable", "limitations")
_CLIENT_SURFACE_ITEM_LIMIT = 100_000
_INTERNAL_DOTTED_LINE = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}(?::|\s*$)",
    re.IGNORECASE,
)
_COMPLEXITY_FINDING = re.compile(r"\breduce complexity in\b", re.IGNORECASE)
_OUTCOME_LABELS = {
    "success": "Successful",
    "successful": "Successful",
    "failure": "Failed",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "skipped": "Skipped",
    "timed_out": "Timed out",
    "timeout": "Timed out",
    "unknown": "Unknown",
    "in_progress": "In progress",
    "queued": "In progress",
    "pending": "In progress",
}


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _label(value: Any) -> str:
    raw = _text(value, 180)
    key = raw.casefold().replace("-", "_").replace(" ", "_")
    return _OUTCOME_LABELS.get(
        key,
        raw.replace("_", " ").replace("-", " ").strip().title() or "Value",
    )


def humanize_client_surface_value(value: Any, *, item_limit: int = 700) -> str:
    """Render structured evidence as readable prose without changing source data."""

    if isinstance(value, Mapping):
        parts: list[str] = []
        for key, raw in value.items():
            if raw in (None, "", [], {}):
                continue
            rendered = humanize_client_surface_value(raw, item_limit=item_limit)
            if rendered:
                parts.append(f"{_label(key)}: {rendered}")
        return _text("; ".join(parts) or "Not available", item_limit)
    if isinstance(value, (list, tuple, set)):
        rendered = [
            humanize_client_surface_value(item, item_limit=item_limit)
            for item in value
            if item not in (None, "", [], {})
        ]
        return _text(", ".join(item for item in rendered if item), item_limit)
    return _text(value, item_limit)


def client_surface_values(
    value: Any,
    *,
    limit: int,
    item_limit: int = 700,
) -> list[str]:
    """Return deduplicated renderer lines with no raw mapping representation."""

    if isinstance(value, Mapping):
        raw_values: Iterable[Any] = (
            f"{_label(key)}: {humanize_client_surface_value(item, item_limit=item_limit)}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        )
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    elif value not in (None, ""):
        raw_values = (value,)
    else:
        raw_values = ()

    output: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = humanize_client_surface_value(raw, item_limit=item_limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _line_capacity(value: Any) -> int:
    if isinstance(value, Mapping):
        return max(1, len(value))
    if isinstance(value, (list, tuple, set)):
        return max(1, len(value))
    return 1


def sanitize_client_rendered_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Humanize all shared stage fields before any client-facing renderer sees them."""

    item = deepcopy(dict(stage))
    stage_id = _text(item.get("stage_id")).casefold()
    for field in _CLIENT_STAGE_FIELDS:
        if field not in item:
            continue
        if (
            (
                stage_id == "client_evidence_summary"
                or stage_id.startswith("client_human_evidence_")
            )
            and field in {"evidence", "unavailable"}
        ):
            raw_values = item.get(field)
            if isinstance(raw_values, (list, tuple)):
                values = [str(value) for value in raw_values if str(value or "").strip()]
            elif raw_values not in (None, ""):
                values = [str(raw_values)]
            else:
                values = []
        else:
            values = client_surface_values(
                item.get(field),
                limit=_line_capacity(item.get(field)),
                item_limit=_CLIENT_SURFACE_ITEM_LIMIT,
            )
        if field == "evidence":
            values = [value for value in values if not _INTERNAL_DOTTED_LINE.match(value)]
        if field == "findings" and stage_id == "dependency_security_static_analysis":
            values = [value for value in values if not _COMPLEXITY_FINDING.search(value)]
        item[field] = values
    return item


def _project_stage_list(value: Any) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for raw in value or []:
        if not isinstance(raw, Mapping):
            continue
        projected.append(sanitize_client_rendered_stage(raw))
    return projected


def project_client_stage_summaries(package: Mapping[str, Any]) -> dict[str, Any]:
    """Humanize only client stage fields; retain complete structured JSON sources."""

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
    source = canonical.get("stage_summaries")
    if not isinstance(source, list):
        source = assessment.get("stage_summaries")
    stages = _project_stage_list(source if isinstance(source, list) else [])
    if stages:
        canonical["stage_summaries"] = deepcopy(stages)
        assessment["stage_summaries"] = deepcopy(stages)
    canonical["assessment"] = assessment
    result["json"] = canonical
    return result


def premium_renderer_clean_lines(values: Any) -> list[str]:
    """Match the premium renderer contract while humanizing nested evidence first."""

    if isinstance(values, Mapping):
        raw_values: Iterable[Any] = (values,)
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    elif values not in (None, ""):
        raw_values = (values,)
    else:
        raw_values = ()

    output: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        item = (
            str(raw).replace("\x7f", "-").strip()
            if isinstance(raw, str)
            else humanize_client_surface_value(raw, item_limit=1200)
        )
        if not item or not re.search(r"[A-Za-z0-9]", item):
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _install_final_truth_evidence_cleanup() -> bool:
    """Patch the last canonical truth pass that previously stringified mappings."""

    from nico import comprehensive_client_truth_final_v1 as final_truth

    current = final_truth._clean_evidence
    if getattr(current, _FINAL_TRUTH_EVIDENCE_MARKER, False):
        return True

    @wraps(current)
    def clean_evidence(values: Any) -> list[str]:
        readable = client_surface_values(
            values,
            limit=_line_capacity(values),
            item_limit=_CLIENT_SURFACE_ITEM_LIMIT,
        )
        return current(readable)

    setattr(clean_evidence, _FINAL_TRUTH_EVIDENCE_MARKER, True)
    setattr(clean_evidence, "_nico_previous", current)
    final_truth._clean_evidence = clean_evidence
    return final_truth._clean_evidence is clean_evidence


def _install_cleanup_stage_sanitizer() -> bool:
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current = cleanup.sanitize_rendered_stage
    if getattr(current, _STAGE_SANITIZER_MARKER, False):
        return True

    @wraps(current)
    def sanitize(stage: Mapping[str, Any]) -> dict[str, Any]:
        return sanitize_client_rendered_stage(stage)

    setattr(sanitize, _STAGE_SANITIZER_MARKER, True)
    setattr(sanitize, "_nico_previous", current)
    cleanup.sanitize_rendered_stage = sanitize
    return cleanup.sanitize_rendered_stage is sanitize


def _install_premium_renderer_structured_line_cleanup() -> bool:
    from nico import v2_premium_report_renderer as premium

    current = premium._clean_lines
    if getattr(current, _PREMIUM_MARKER, False):
        return True

    @wraps(current)
    def clean_lines(values: Any) -> list[str]:
        return premium_renderer_clean_lines(values)

    setattr(clean_lines, _PREMIUM_MARKER, True)
    setattr(clean_lines, "_nico_previous", current)
    premium._clean_lines = clean_lines
    return premium._clean_lines is clean_lines


def _install_premium_stage_population_cleanup() -> bool:
    """Normalize the complete derived stage population before every format renders."""

    from nico import v2_premium_report_renderer as premium

    current = premium._canonical_stages
    if getattr(current, _PREMIUM_STAGE_MARKER, False):
        return True

    @wraps(current)
    def canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            sanitize_client_rendered_stage(stage)
            for stage in current(canonical)
            if isinstance(stage, Mapping)
        ]

    setattr(canonical_stages, _PREMIUM_STAGE_MARKER, True)
    setattr(canonical_stages, "_nico_previous", current)
    premium._canonical_stages = canonical_stages
    return premium._canonical_stages is canonical_stages


def _install_premium_renderer_entrypoint_cleanup() -> bool:
    """Bind the repaired helpers at the exact renderer entrypoint used by imports."""

    from nico import v2_premium_evidence_appendix as appendix
    from nico import v2_premium_report_renderer as premium

    current = premium.rebuild_premium_client_artifacts
    if getattr(current, _PREMIUM_ENTRYPOINT_MARKER, False):
        appendix.rebuild_premium_client_artifacts = current
        return appendix.rebuild_premium_client_artifacts is current

    @wraps(current)
    def rebuild(package: Mapping[str, Any]) -> dict[str, Any]:
        current.__globals__["_clean_lines"] = premium_renderer_clean_lines
        current.__globals__["_canonical_stages"] = premium._canonical_stages
        return current(package)

    setattr(rebuild, _PREMIUM_ENTRYPOINT_MARKER, True)
    setattr(rebuild, "_nico_previous", current)
    premium.rebuild_premium_client_artifacts = rebuild
    appendix.rebuild_premium_client_artifacts = rebuild
    return (
        premium.rebuild_premium_client_artifacts is rebuild
        and appendix.rebuild_premium_client_artifacts is rebuild
    )


def _install_raw_mapping_surface_diagnostic() -> bool:
    from nico import comprehensive_full_report_finish_v1 as finish

    current = finish.assert_no_raw_mapping_presentation
    if getattr(current, _DIAGNOSTIC_MARKER, False):
        return True

    @wraps(current)
    def validate(markdown: str, rendered_html: str, pdf: bytes) -> None:
        surfaces = (
            ("Markdown", markdown or ""),
            ("HTML", finish._html_text(rendered_html)),
            ("PDF", finish._pdf_text(pdf)),
        )
        for surface_name, surface in surfaces:
            for raw_line in surface.splitlines():
                line = raw_line.strip()
                if line.startswith(("- ", "* ")):
                    line = line[2:].strip()
                if finish._mapping_tail(line)[1] is not None:
                    raise ValueError(
                        "client-facing artifact retained a raw mapping presentation "
                        f"in {surface_name}: {_text(line, 500)}"
                    )

    setattr(validate, _DIAGNOSTIC_MARKER, True)
    setattr(validate, "_nico_previous", current)
    finish.assert_no_raw_mapping_presentation = validate
    return finish.assert_no_raw_mapping_presentation is validate


def install_client_surface_structure_cleanup_v1() -> dict[str, Any]:
    """Patch shared render-only helpers while preserving canonical evidence."""

    from nico import comprehensive_client_review_companion_v2 as companion

    final_truth_bound = _install_final_truth_evidence_cleanup()
    stage_sanitizer_bound = _install_cleanup_stage_sanitizer()
    premium_bound = _install_premium_renderer_structured_line_cleanup()
    premium_stages_bound = _install_premium_stage_population_cleanup()
    premium_entrypoint_bound = _install_premium_renderer_entrypoint_cleanup()
    diagnostic_bound = _install_raw_mapping_surface_diagnostic()
    current = companion._values
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "final_truth_evidence_cleanup_bound": final_truth_bound,
            "structured_stage_sanitizer_bound": stage_sanitizer_bound,
            "premium_renderer_clean_lines_bound": premium_bound,
            "premium_stage_population_cleanup_bound": premium_stages_bound,
            "premium_renderer_entrypoint_bound": premium_entrypoint_bound,
            "review_companion_values_bound": True,
            "raw_mapping_surface_diagnostic_bound": diagnostic_bound,
            "canonical_structured_sources_retained": True,
        }

    @wraps(current)
    def values(value: Any, *, limit: int, item_limit: int = 700) -> list[str]:
        return client_surface_values(value, limit=limit, item_limit=item_limit)

    setattr(values, _MARKER, True)
    setattr(values, "_nico_previous", current)
    companion._values = values
    return {
        "status": "installed",
        "version": VERSION,
        "final_truth_evidence_cleanup_bound": final_truth_bound,
        "structured_stage_sanitizer_bound": stage_sanitizer_bound,
        "premium_renderer_clean_lines_bound": premium_bound,
        "premium_stage_population_cleanup_bound": premium_stages_bound,
        "premium_renderer_entrypoint_bound": premium_entrypoint_bound,
        "review_companion_values_bound": companion._values is values,
        "raw_mapping_surface_diagnostic_bound": diagnostic_bound,
        "nested_mappings_rendered_as_labels": True,
        "canonical_structured_sources_retained": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "client_surface_values",
    "humanize_client_surface_value",
    "install_client_surface_structure_cleanup_v1",
    "premium_renderer_clean_lines",
    "project_client_stage_summaries",
    "sanitize_client_rendered_stage",
]
