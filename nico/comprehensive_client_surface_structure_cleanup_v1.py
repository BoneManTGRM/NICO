from __future__ import annotations

import re
from functools import wraps
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-client-surface-structure-cleanup.v1"
_MARKER = "__nico_comprehensive_client_surface_structure_cleanup_v1__"
_PREMIUM_MARKER = "__nico_premium_structured_line_cleanup_v1__"
_PREMIUM_ENTRYPOINT_MARKER = "__nico_premium_structured_entrypoint_cleanup_v1__"
_DIAGNOSTIC_MARKER = "__nico_raw_mapping_surface_diagnostic_v1__"
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
    """Render structured evidence as readable prose without changing canonical JSON."""

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
        item = humanize_client_surface_value(raw, item_limit=1200)
        if not item or not re.search(r"[A-Za-z0-9]", item):
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


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


def _install_premium_renderer_entrypoint_cleanup() -> bool:
    """Bind the repaired helper at the exact renderer entrypoint used by imports."""

    from nico import v2_premium_evidence_appendix as appendix
    from nico import v2_premium_report_renderer as premium

    current = premium.rebuild_premium_client_artifacts
    if getattr(current, _PREMIUM_ENTRYPOINT_MARKER, False):
        appendix.rebuild_premium_client_artifacts = current
        return appendix.rebuild_premium_client_artifacts is current

    @wraps(current)
    def rebuild(package: Mapping[str, Any]) -> dict[str, Any]:
        # The appendix module captures this renderer by direct import. Rebind the
        # original function's global helper at call time so every imported alias
        # uses the same structured-value renderer without changing canonical JSON.
        current.__globals__["_clean_lines"] = premium_renderer_clean_lines
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

    premium_bound = _install_premium_renderer_structured_line_cleanup()
    premium_entrypoint_bound = _install_premium_renderer_entrypoint_cleanup()
    diagnostic_bound = _install_raw_mapping_surface_diagnostic()
    current = companion._values
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "premium_renderer_clean_lines_bound": premium_bound,
            "premium_renderer_entrypoint_bound": premium_entrypoint_bound,
            "review_companion_values_bound": True,
            "raw_mapping_surface_diagnostic_bound": diagnostic_bound,
            "canonical_json_unchanged": True,
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
        "premium_renderer_clean_lines_bound": premium_bound,
        "premium_renderer_entrypoint_bound": premium_entrypoint_bound,
        "review_companion_values_bound": companion._values is values,
        "raw_mapping_surface_diagnostic_bound": diagnostic_bound,
        "nested_mappings_rendered_as_labels": True,
        "canonical_json_unchanged": True,
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
]
