from __future__ import annotations

import re
import unicodedata
from typing import Any


_TEXT_LIST_KEYS = (
    "evidence",
    "findings",
    "unavailable",
    "verified_claims",
    "unverified_claims",
)
_TOP_LEVEL_TEXT_LIST_KEYS = (
    "unavailable_data_notes",
    "findings",
    "repairs",
    "next_steps",
)
_WHITESPACE_RE = re.compile(r"\s+")


def _display_text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _display_text(value))
    return _WHITESPACE_RE.sub(" ", text).casefold()


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def deduplicate_text_items(value: Any) -> tuple[list[Any], int]:
    """Deduplicate exact presentation-equivalent text while preserving first-seen wording.

    This is intentionally conservative. It collapses case, Unicode compatibility,
    and whitespace-only repetition, but it does not merge semantically related or
    causally linked limitations. Distinct evidence remains distinct.
    """

    if value is None:
        return [], 0
    items = value if isinstance(value, list) else [value]
    output: list[Any] = []
    seen: set[str] = set()
    removed = 0
    for item in items:
        key = _dedupe_key(item)
        if not key:
            removed += 1
            continue
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        output.append(item)
    return output, removed


def _normalize_section(section: dict[str, Any]) -> int:
    removed = 0
    for key in _TEXT_LIST_KEYS:
        if key not in section:
            continue
        normalized, count = deduplicate_text_items(section.get(key))
        section[key] = normalized
        removed += count
    return removed


def _normalize_document(document: dict[str, Any]) -> dict[str, int]:
    removed_top_level = 0
    removed_sections = 0
    for key in _TOP_LEVEL_TEXT_LIST_KEYS:
        if key not in document:
            continue
        normalized, count = deduplicate_text_items(document.get(key))
        document[key] = normalized
        removed_top_level += count

    for section in document.get("sections", []) or []:
        if isinstance(section, dict):
            removed_sections += _normalize_section(section)

    return {
        "top_level_items_removed": removed_top_level,
        "section_items_removed": removed_sections,
    }


def normalize_report_presentation_lists(result: dict[str, Any]) -> dict[str, Any]:
    """Remove duplicate client-visible list lines without changing evidence meaning.

    Raw scanner artifacts, ledgers, hashes, scores, trust state, review state, and
    delivery state are not modified. Only client-visible presentation lists on the
    result and nested assessment document are normalized. Repeated passes are
    idempotent and keep cumulative instrumentation from earlier final-gate passes.
    """

    if not isinstance(result, dict):
        return result

    totals = _normalize_document(result)
    nested = result.get("assessment")
    if isinstance(nested, dict) and nested is not result:
        nested_totals = _normalize_document(nested)
        totals = {
            key: totals[key] + nested_totals[key]
            for key in totals
        }

    guards = result.setdefault("report_quality_guards", {})
    previous = guards.get("presentation_list_normalization")
    previous = previous if isinstance(previous, dict) else {}
    cumulative = {
        "top_level_items_removed": _count(previous.get("top_level_items_removed")) + totals["top_level_items_removed"],
        "section_items_removed": _count(previous.get("section_items_removed")) + totals["section_items_removed"],
    }
    removed = cumulative["top_level_items_removed"] + cumulative["section_items_removed"]
    guards["presentation_list_normalization"] = {
        "status": "normalized" if removed else "no_duplicates_found",
        "duplicates_removed": removed,
        "passes": _count(previous.get("passes")) + 1,
        **cumulative,
        "last_pass_duplicates_removed": totals["top_level_items_removed"] + totals["section_items_removed"],
        "scope": "Client-visible top-level and section presentation lists only.",
        "guardrail": "Semantically distinct limitations are preserved; raw evidence artifacts, scores, trust, approval, and delivery state are unchanged.",
    }
    return result


__all__ = [
    "deduplicate_text_items",
    "normalize_report_presentation_lists",
]
