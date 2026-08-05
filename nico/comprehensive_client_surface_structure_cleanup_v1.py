from __future__ import annotations

from functools import wraps
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-client-surface-structure-cleanup.v1"
_MARKER = "__nico_comprehensive_client_surface_structure_cleanup_v1__"
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


def install_client_surface_structure_cleanup_v1() -> dict[str, Any]:
    """Patch the shared review-companion value renderer, not canonical evidence."""

    from nico import comprehensive_client_review_companion_v2 as companion

    current = companion._values
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "review_companion_values_bound": True,
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
        "review_companion_values_bound": companion._values is values,
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
]
