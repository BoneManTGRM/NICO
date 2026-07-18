from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.scanner_redaction_type_safety.v1"
_PATCH_MARKER = "_nico_scanner_redaction_type_safety_v1"


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, bytearray):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8", errors="replace")
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
        except (TypeError, ValueError, RecursionError):
            return str(value)
    return str(value)


def install_scanner_redaction_type_safety() -> dict[str, Any]:
    """Prevent scanner evidence collection from failing on non-string output.

    Worker adapters and subprocess libraries can return bytes or structured error
    payloads. ``scanner_tool_runners.redact_text`` previously passed those values
    directly to ``re.Pattern.sub``, causing the production TypeError observed in
    collect_assessment. The wrapper normalizes only the input representation and
    delegates all secret-pattern handling to the existing redactor.
    """

    from nico import scanner_tool_runners

    current: Callable[[Any], str] = scanner_tool_runners.redact_text
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def type_safe_redact_text(value: Any) -> str:
        return current(_coerce_text(value))

    setattr(type_safe_redact_text, _PATCH_MARKER, True)
    setattr(type_safe_redact_text, "_nico_previous", current)
    scanner_tool_runners.redact_text = type_safe_redact_text
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "supported_inputs": ["str", "bytes", "bytearray", "memoryview", "mapping", "sequence", "scalar", "none"],
        "secret_redaction_preserved": True,
    }


__all__ = ["PATCH_VERSION", "install_scanner_redaction_type_safety"]
