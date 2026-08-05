#!/usr/bin/env python3
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Callable

VERSION = "nico.final_stage_diagnostics.v1"
_MAX_TEXT = 1000
_MAX_VALIDATION_ITEMS = 20
_MAX_VALIDATION_TEXT = 320
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|bearer|token|password|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;]+"
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _redact(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _BEARER_VALUE.sub("Bearer [REDACTED]", text)
    return text[:limit]


def _record(payload: Mapping[str, Any], acceptance: Any) -> Mapping[str, Any]:
    try:
        value = acceptance.record(dict(payload))
    except Exception:
        value = {}
    return value if isinstance(value, Mapping) else {}


def _current_stage(payload: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    return _redact(payload.get("current_stage") or record.get("current_stage"), limit=160)


def _stage_container(payload: Mapping[str, Any], record: Mapping[str, Any]) -> Any:
    for owner in (payload, record):
        for key in ("stage_results", "stages"):
            value = owner.get(key)
            if isinstance(value, Mapping) or (
                isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
            ):
                return value
    return None


def _select_stage(payload: Mapping[str, Any], acceptance: Any) -> Mapping[str, Any]:
    record = _record(payload, acceptance)
    current = _current_stage(payload, record)
    container = _stage_container(payload, record)
    if isinstance(container, Mapping):
        direct = container.get(current) if current else None
        if isinstance(direct, Mapping):
            return direct
        candidates = [value for value in container.values() if isinstance(value, Mapping)]
    elif isinstance(container, Sequence) and not isinstance(container, (str, bytes, bytearray)):
        candidates = [value for value in container if isinstance(value, Mapping)]
    else:
        candidates = []

    if current:
        for candidate in reversed(candidates):
            name = _redact(
                candidate.get("stage") or candidate.get("stage_name") or candidate.get("name"),
                limit=160,
            )
            if name == current:
                return candidate
    return candidates[-1] if candidates else {}


def _validation_item(value: Any) -> str:
    if isinstance(value, Mapping):
        parts = []
        for key in ("field", "code", "message", "reason"):
            text = _redact(value.get(key), limit=_MAX_VALIDATION_TEXT)
            if text:
                parts.append(f"{key}={text}")
        return "; ".join(parts)[:_MAX_VALIDATION_TEXT]
    return _redact(value, limit=_MAX_VALIDATION_TEXT)


def _validation_errors(stage: Mapping[str, Any]) -> list[str]:
    value: Any = stage.get("validation_errors")
    if value in (None, ""):
        details = stage.get("validation_details")
        if isinstance(details, Mapping):
            value = details.get("errors") or details.get("validation_errors")
    if value in (None, ""):
        return []
    items = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else [value]
    result = []
    for item in items[:_MAX_VALIDATION_ITEMS]:
        text = _validation_item(item)
        if text:
            result.append(text)
    return result


def final_stage_diagnostics(payload: Mapping[str, Any], acceptance: Any) -> dict[str, Any]:
    """Return bounded scalar diagnostics without provider payloads or report bodies."""

    stage = _select_stage(payload, acceptance)
    if not stage:
        return {}
    nested_error = stage.get("error") if isinstance(stage.get("error"), Mapping) else {}
    reason = _redact(stage.get("reason"), limit=_MAX_TEXT)
    error_code = _redact(stage.get("error_code") or nested_error.get("code"), limit=160)
    error_message = _redact(
        stage.get("error_message") or nested_error.get("message"),
        limit=_MAX_TEXT,
    )
    validation_errors = _validation_errors(stage)
    result: dict[str, Any] = {}
    if reason:
        result["stage_reason"] = reason
    if error_code:
        result["stage_error_code"] = error_code
    if error_message:
        result["stage_error_message"] = error_message
    if validation_errors:
        result["stage_validation_errors"] = validation_errors
    return result


def install(runtime: Any, acceptance: Any) -> dict[str, Any]:
    """Patch the shared status serializer while preserving fail-closed behavior."""

    original: Callable[..., dict[str, Any]] = runtime._status_summary
    if getattr(original, "_nico_final_stage_diagnostics_v1", False):
        return {"version": VERSION, "installed": True, "already_installed": True}

    def status_summary(payload: dict[str, Any], *, http_status: int | None = None) -> dict[str, Any]:
        summary = original(payload, http_status=http_status)
        if isinstance(summary, dict):
            summary.update(final_stage_diagnostics(payload, acceptance))
        return summary

    status_summary._nico_final_stage_diagnostics_v1 = True  # type: ignore[attr-defined]
    runtime._status_summary = status_summary
    return {"version": VERSION, "installed": True, "already_installed": False}
