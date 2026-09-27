"""Describe large source tables without changing their retained evidence rows.

Only the PDF presentation changes. Complete title/columns/rows remain in the
same-edition canonical evidence JSON and in the existing Markdown/HTML views.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any


VERSION = "nico.comprehensive-source-table-presentation.v1"
MAX_INLINE_SOURCE_TABLE_ROWS = 48


def _require_json_value(value: Any, active: set[int] | None = None) -> None:
    """Reject coercion of opaque values or non-string keys in evidence digests."""
    kind = type(value)
    if value is None or kind is str or kind is bool or kind is int or kind is float:
        return
    if kind is not dict and kind is not list:
        raise ValueError("source table digest requires JSON-safe values")
    active = active if active is not None else set()
    identity = id(value)
    if identity in active:
        raise ValueError("source table digest cannot contain cyclic values")
    active.add(identity)
    try:
        if kind is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("source table digest requires string object keys")
            children = value.values()
        else:
            children = value
        for child in children:
            _require_json_value(child, active)
    finally:
        active.remove(identity)


def source_table_summary(table: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return an exact descriptor when a structured table exceeds the PDF limit.

    The threshold concerns inline PDF rows only. No table, row, column, ordering,
    source identity or value is removed from its retained canonical evidence.
    Call this only for structured source tables, not generated coverage tables.
    """
    rows = table.get("rows")
    columns = table.get("columns")
    if not isinstance(rows, list) or len(rows) <= MAX_INLINE_SOURCE_TABLE_ROWS or not columns:
        return None
    payload = {"title": table["title"], "columns": columns, "rows": rows}
    _require_json_value(payload)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return {
        "version": VERSION,
        "title": deepcopy(payload["title"]),
        "columns": deepcopy(columns),
        "row_count": len(rows),
        "sha256": digest,
        "reference_token": f"NICO-TABLE-{digest}-{len(rows)}",
        "digest_scope": "exact_title_columns_rows",
        "full_rows_artifact": "canonical_json",
    }


def source_table_summaries(stages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Describe large structured source tables in stage order, once per digest."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stage in stages:
        if not isinstance(stage, Mapping):
            continue
        for table in stage.get("structured_tables") or []:
            if not isinstance(table, Mapping):
                continue
            summary = source_table_summary(table)
            if summary is None or summary["sha256"] in seen:
                continue
            seen.add(summary["sha256"])
            output.append(summary)
    return output


__all__ = ["VERSION", "MAX_INLINE_SOURCE_TABLE_ROWS", "source_table_summary", "source_table_summaries"]
