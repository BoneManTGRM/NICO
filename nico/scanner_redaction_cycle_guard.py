from __future__ import annotations

import json
from typing import Any, Callable

import nico.scanner_tool_runners as scanner_tools

SCANNER_REDACTION_CYCLE_GUARD_VERSION = "nico.scanner_redaction_cycle_guard.v1"
_MARKER = "_nico_scanner_redaction_cycle_guard_v1"
_MAX_REDACTION_DEPTH = 64


def _cycle_marker(kind: str) -> dict[str, str]:
    return {"$circular_reference": kind}


def cycle_safe_redact_payload(
    value: Any,
    *,
    _active_container_ids: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    """Redact arbitrary scanner evidence without following container cycles forever.

    The returned value is JSON-safe. Circular references and excessive nesting are
    represented explicitly; secrets are redacted from string values, dictionary keys,
    bytes, and fallback object representations.
    """

    if isinstance(value, str):
        return scanner_tools.redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        return scanner_tools.redact_text(value.decode("utf-8", errors="replace"))
    if _depth >= _MAX_REDACTION_DEPTH:
        return {"$truncated": "maximum_redaction_depth"}

    active = _active_container_ids if _active_container_ids is not None else set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            return _cycle_marker("dict")
        active.add(identity)
        try:
            return {
                scanner_tools.redact_text(str(key)): cycle_safe_redact_payload(
                    item,
                    _active_container_ids=active,
                    _depth=_depth + 1,
                )
                for key, item in value.items()
            }
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            return _cycle_marker(type(value).__name__)
        active.add(identity)
        try:
            return [
                cycle_safe_redact_payload(
                    item,
                    _active_container_ids=active,
                    _depth=_depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in active:
            return _cycle_marker(type(value).__name__)
        active.add(identity)
        try:
            normalized = [
                cycle_safe_redact_payload(
                    item,
                    _active_container_ids=active,
                    _depth=_depth + 1,
                )
                for item in value
            ]
        finally:
            active.remove(identity)
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
        )

    return scanner_tools.redact_text(str(value))


def install_cycle_safe_scanner_redaction() -> dict[str, Any]:
    current: Callable[[Any], Any] = scanner_tools.redact_payload
    already_installed = bool(getattr(current, _MARKER, False))
    safe_redactor = current if already_installed else cycle_safe_redact_payload
    if not already_installed:
        setattr(safe_redactor, _MARKER, True)
        setattr(safe_redactor, "_nico_previous", current)
        scanner_tools.redact_payload = safe_redactor

    hosted_worker_patched = False
    try:
        import nico.hosted_scanner_worker as hosted_worker

        hosted_worker.redact_payload = safe_redactor
        hosted_worker_patched = hosted_worker.redact_payload is safe_redactor
    except Exception:
        hosted_worker_patched = False

    return {
        "status": "already_installed" if already_installed else "installed",
        "version": SCANNER_REDACTION_CYCLE_GUARD_VERSION,
        "cycle_safe": True,
        "maximum_depth": _MAX_REDACTION_DEPTH,
        "json_safe_output": True,
        "hosted_worker_patched": hosted_worker_patched,
        "raw_secret_exposure_allowed": False,
    }


__all__ = [
    "SCANNER_REDACTION_CYCLE_GUARD_VERSION",
    "cycle_safe_redact_payload",
    "install_cycle_safe_scanner_redaction",
]
