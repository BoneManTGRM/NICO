from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

FULL_TERMINAL_FORMAT_INTEGRITY_VERSION = "nico.full_terminal_format_integrity.v1"
_PATCH_MARKER = "_nico_full_terminal_format_integrity_v1"
_REQUIRED_FORMATS = ("markdown", "html", "pdf")


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def install_full_terminal_format_integrity() -> dict[str, Any]:
    """Fail closed when a Full report package lacks any required export format."""
    from nico import full_assessment_idempotent_handlers as handlers

    current: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = handlers._reports_handler
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION}

    @wraps(current)
    def reports_with_complete_format_set(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(current(context, outputs))
        if result.get("status") != "complete":
            return result

        package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
        formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
        availability = {
            "markdown": _non_empty(formats.get("markdown")),
            "html": _non_empty(formats.get("html")),
            "pdf": _non_empty(formats.get("pdf")) and not _non_empty(package.get("pdf_error")),
        }
        missing = [name for name in _REQUIRED_FORMATS if not availability[name]]
        complete = not missing

        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        evidence = deepcopy(evidence)
        evidence["required_formats"] = list(_REQUIRED_FORMATS)
        evidence["missing_formats"] = missing
        evidence["format_equivalence_ready"] = complete
        evidence["available_formats"] = [name for name in _REQUIRED_FORMATS if availability[name]]
        result["evidence"] = evidence

        result["format_integrity"] = {
            "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION,
            "required_formats": list(_REQUIRED_FORMATS),
            "missing_formats": missing,
            "format_equivalence_ready": complete,
            "availability": availability,
        }
        if missing:
            result["status"] = "limited"
            result["message"] = (
                "Full report generation finished without a complete export set. "
                "Missing required format(s): " + ", ".join(missing) + "."
            )
            result["report_format_error"] = result["message"]
        else:
            result.pop("report_format_error", None)
        return result

    setattr(reports_with_complete_format_set, _PATCH_MARKER, True)
    setattr(reports_with_complete_format_set, "_nico_previous", current)
    handlers._reports_handler = reports_with_complete_format_set
    return {
        "status": "installed",
        "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION,
        "required_formats": list(_REQUIRED_FORMATS),
        "fail_closed": True,
    }


__all__ = ["FULL_TERMINAL_FORMAT_INTEGRITY_VERSION", "install_full_terminal_format_integrity"]
