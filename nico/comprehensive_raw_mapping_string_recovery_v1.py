from __future__ import annotations

import ast
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-raw-mapping-string-recovery.v1"
_MARKER = "__nico_raw_mapping_string_recovery_v1__"
_MAX_LITERAL_LENGTH = 100_000


def recover_literal_structure(value: Any) -> Any:
    """Recover only inert Python/JSON-like container literals from retained text.

    Some legacy report projections converted structured roadmap or trend evidence
    to ``str(mapping)`` before the shared client-surface renderer received it. Use
    ``ast.literal_eval`` only for bounded strings with matching container delimiters.
    No names, calls, attributes, comprehensions, or executable expressions are
    accepted. Non-container values are returned unchanged.
    """

    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or len(text) > _MAX_LITERAL_LENGTH:
        return value
    if not (
        (text.startswith("{") and text.endswith("}"))
        or (text.startswith("[") and text.endswith("]"))
        or (text.startswith("(") and text.endswith(")"))
    ):
        return value
    try:
        recovered = ast.literal_eval(text)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return value
    if isinstance(recovered, (Mapping, list, tuple, set)):
        return recovered
    return value


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
