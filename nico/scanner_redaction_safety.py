from __future__ import annotations

import json
from typing import Any

SCANNER_REDACTION_SAFETY_VERSION = "nico.scanner_redaction_safety.v1"
_MAX_REDACTION_DEPTH = 64
_MARKER = "_nico_scanner_redaction_safety_v1"


def _safe_string(value: Any) -> str:
    try:
        return str(value)
    except BaseException:
        return f"<{type(value).__module__}.{type(value).__qualname__}>"


def cycle_safe_redact_payload(
    value: Any,
    *,
    active_container_ids: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Redact arbitrary scanner evidence without recursing forever on cycles.

    Scanner tools and compatibility layers may return shared or self-referential
    containers. Redaction must produce a bounded JSON-safe copy while leaving the
    original evidence untouched. Cycles and excessive depth remain explicit rather
    than being silently dropped or terminating the assessment.
    """

    from nico.scanner_tool_runners import redact_text

    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return redact_text(bytes(value).decode("utf-8", errors="replace"))
    if depth >= _MAX_REDACTION_DEPTH:
        return {"$truncated": "maximum_redaction_depth"}

    active = active_container_ids if active_container_ids is not None else set()

    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": "dict"}
        active.add(identity)
        try:
            return {
                redact_text(_safe_string(key)): cycle_safe_redact_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for key, item in value.items()
            }
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            return [
                cycle_safe_redact_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            normalized = [
                cycle_safe_redact_payload(
                    item,
                    active_container_ids=active,
                    depth=depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
        )

    return redact_text(_safe_string(value))


setattr(cycle_safe_redact_payload, _MARKER, True)


def scanner_redaction_safety_status() -> dict[str, Any]:
    import nico.scanner_tool_runners as tool_runners

    active = bool(getattr(tool_runners.redact_payload, _MARKER, False))
    return {
        "status": "ok" if active else "blocked",
        "version": SCANNER_REDACTION_SAFETY_VERSION,
        "cycle_safe_redaction_installed": active,
        "maximum_depth": _MAX_REDACTION_DEPTH,
        "circular_references_explicit": True,
        "original_evidence_mutated": False,
    }


def install_scanner_redaction_safety() -> dict[str, Any]:
    """Install the cycle-safe redactor at the scanner runtime boundary."""

    import nico.scanner_tool_runners as tool_runners

    current = tool_runners.redact_payload
    if not getattr(current, _MARKER, False):
        if not hasattr(tool_runners, "_nico_original_redact_payload"):
            tool_runners._nico_original_redact_payload = current
        tool_runners.redact_payload = cycle_safe_redact_payload
    return scanner_redaction_safety_status()


__all__ = [
    "SCANNER_REDACTION_SAFETY_VERSION",
    "cycle_safe_redact_payload",
    "install_scanner_redaction_safety",
    "scanner_redaction_safety_status",
]
