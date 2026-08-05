from __future__ import annotations

import ast
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-raw-mapping-string-recovery.v1.1"
_MARKER = "__nico_raw_mapping_string_recovery_v1__"
_MAX_LITERAL_LENGTH = 100_000


def _literal_and_label(text: str) -> tuple[str, str]:
    """Return a bounded container literal and an optional human-readable prefix."""

    if (
        (text.startswith("{") and text.endswith("}"))
        or (text.startswith("[") and text.endswith("]"))
        or (text.startswith("(") and text.endswith(")"))
    ):
        return text, ""

    opening = text.find("{")
    if opening <= 0 or not text.endswith("}"):
        return "", ""
    prefix = text[:opening].strip()
    if not prefix.endswith((":", "=")):
        return "", ""
    label = prefix.rstrip(":= ").strip()
    return (text[opening:], label) if label else ("", "")


def recover_literal_structure(value: Any) -> Any:
    """Recover inert container literals, including labelled mapping tails.

    Some legacy report projections converted structured roadmap or trend evidence
    to ``str(mapping)`` before the shared client-surface renderer received it. Use
    ``ast.literal_eval`` only for bounded strings with matching container delimiters.
    A line such as ``Outcome taxonomy: {'success': 80}`` is recovered as a nested
    mapping so the renderer keeps the label while removing Python mapping syntax.
    No names, calls, attributes, comprehensions, or executable expressions are
    accepted. Non-container values are returned unchanged.
    """

    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or len(text) > _MAX_LITERAL_LENGTH:
        return value

    literal, label = _literal_and_label(text)
    if not literal:
        return value
    try:
        recovered = ast.literal_eval(literal)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return value
    if not isinstance(recovered, (Mapping, list, tuple, set)):
        return value
    if label:
        return {label: recovered} if isinstance(recovered, Mapping) else value
    return recovered


def install_raw_mapping_string_recovery_v1() -> dict[str, Any]:
    """Install recovery at the common recursive client-surface value renderer."""

    from nico import comprehensive_client_surface_structure_cleanup_v1 as surface

    current = surface.humanize_client_surface_value
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "literal_eval_only": True,
            "bounded_container_literals_only": True,
            "labelled_mapping_tails_recovered": True,
            "canonical_structured_sources_unchanged": True,
        }

    @wraps(current)
    def humanize(value: Any, *, item_limit: int = 700) -> str:
        return current(recover_literal_structure(value), item_limit=item_limit)

    setattr(humanize, _MARKER, True)
    setattr(humanize, "_nico_previous", current)
    surface.humanize_client_surface_value = humanize
    return {
        "status": "installed",
        "version": VERSION,
        "literal_eval_only": True,
        "bounded_container_literals_only": True,
        "labelled_mapping_tails_recovered": True,
        "raw_mapping_strings_recovered_before_client_render": True,
        "canonical_structured_sources_unchanged": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_raw_mapping_string_recovery_v1",
    "recover_literal_structure",
]
