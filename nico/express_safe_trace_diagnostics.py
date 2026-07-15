from __future__ import annotations

import re
from typing import Any, Callable

import nico.express_backend_diagnostics as diagnostics

EXPRESS_SAFE_TRACE_DIAGNOSTICS_VERSION = "nico.express_safe_trace_diagnostics.v1"
_MARKER = "_nico_express_safe_trace_diagnostics_v1"
_FAILURE_MARKER = "_nico_express_safe_trace_failure_v1"
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,159}$")
_SAFE_FUNCTION = re.compile(r"^[A-Za-z_][A-Za-z0-9_<>.]{0,159}$")


def _safe_failure_frame(exc: BaseException) -> dict[str, Any]:
    """Return only the deepest NICO-owned traceback identity.

    Exception text, locals, source lines, absolute paths, request data, and provider
    responses are deliberately excluded. The result is suitable for a bounded
    production failure record and is intended only to locate the responsible code.
    """

    selected: dict[str, Any] = {}
    current = exc.__traceback__
    while current is not None:
        frame = current.tb_frame
        module = str(frame.f_globals.get("__name__") or "")[:160]
        function = str(frame.f_code.co_name or "")[:160]
        if module.startswith("nico.") and _SAFE_NAME.fullmatch(module):
            selected = {
                "failure_module": module,
                "failure_function": function if _SAFE_FUNCTION.fullmatch(function) else "unknown",
                "failure_line": max(1, int(current.tb_lineno)),
            }
        current = current.tb_next
    return selected


def _safe_location(failure: dict[str, Any]) -> str:
    module = str(failure.get("failure_module") or "")
    function = str(failure.get("failure_function") or "")
    line = failure.get("failure_line")
    if not module or not function or not isinstance(line, int):
        return ""
    return f"{module}.{function}:{line}"[:150]


def install_express_safe_trace_diagnostics() -> dict[str, Any]:
    current: Callable[[str, str, BaseException], dict[str, str]] = diagnostics._diagnostic
    current_failure = diagnostics._diagnostic_failure
    already_installed = bool(getattr(current, _MARKER, False)) and bool(
        getattr(current_failure, _FAILURE_MARKER, False)
    )
    if already_installed:
        return {
            "status": "already_installed",
            "version": EXPRESS_SAFE_TRACE_DIAGNOSTICS_VERSION,
            "nico_failure_frame_recorded": True,
            "bounded_location_in_public_message": True,
            "exception_text_exposed": False,
            "locals_exposed": False,
            "absolute_paths_exposed": False,
        }

    def diagnostic_with_safe_frame(run_id: str, stage: str, exc: BaseException) -> dict[str, Any]:
        result: dict[str, Any] = dict(current(run_id, stage, exc))
        result.update(_safe_failure_frame(exc))
        return result

    def failure_with_safe_location(
        run_id: str,
        request_payload: dict[str, Any],
        stage: str,
        exc: BaseException,
    ) -> dict[str, Any]:
        failure = current_failure(run_id, request_payload, stage, exc)
        location = _safe_location(failure)
        if not location:
            return failure
        message = (
            f"Express assessment execution failed during {failure.get('failure_stage', 'unknown_backend_stage')}. "
            f"Diagnostic ID {failure.get('diagnostic_id', 'unavailable')}; "
            f"exception class {failure.get('exception_class', 'BackendException')}; "
            f"NICO frame {location}. Internal exception text remains redacted."
        )[:320]
        progress = failure.get("progress") if isinstance(failure.get("progress"), list) else []
        if progress and isinstance(progress[0], dict):
            progress[0]["message"] = message
        failure["message"] = message
        failure["safe_failure_location"] = location
        return failure

    setattr(diagnostic_with_safe_frame, _MARKER, True)
    setattr(diagnostic_with_safe_frame, "_nico_previous", current)
    setattr(failure_with_safe_location, _FAILURE_MARKER, True)
    setattr(failure_with_safe_location, "_nico_previous", current_failure)
    diagnostics._diagnostic = diagnostic_with_safe_frame
    diagnostics._diagnostic_failure = failure_with_safe_location
    return {
        "status": "installed",
        "version": EXPRESS_SAFE_TRACE_DIAGNOSTICS_VERSION,
        "nico_failure_frame_recorded": True,
        "bounded_location_in_public_message": True,
        "exception_text_exposed": False,
        "locals_exposed": False,
        "absolute_paths_exposed": False,
    }


__all__ = [
    "EXPRESS_SAFE_TRACE_DIAGNOSTICS_VERSION",
    "install_express_safe_trace_diagnostics",
]
