from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_TERMINAL_FORMAT_INTEGRITY_VERSION = "nico.mid_terminal_format_integrity.v1"
_PATCH_MARKER = "_nico_mid_terminal_format_integrity_v1"
_REQUIRED_FORMATS = ("markdown", "html", "pdf")


def install_mid_terminal_format_integrity() -> dict[str, Any]:
    """Require Markdown, HTML, and integrity-verified PDF before a Mid artifact is complete."""
    from nico import mid_status_read_path as read_path

    current: Callable[..., tuple[dict[str, Any], bool]] = read_path._rehydrate_final_report
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_TERMINAL_FORMAT_INTEGRITY_VERSION}

    @wraps(current)
    def rehydrate_with_complete_format_set(
        record: dict[str, Any],
        result: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        output, _legacy_complete = current(record, result)
        output = deepcopy(output)
        reports = output.get("reports") if isinstance(output.get("reports"), dict) else {}
        status = output.get("report_artifact_status") if isinstance(output.get("report_artifact_status"), dict) else {}

        availability = {
            "markdown": bool(reports.get("markdown")),
            "html": bool(reports.get("html")),
            "pdf": bool(reports.get("pdf_base64")) and bool(status.get("pdf_integrity_verified")),
        }
        missing = [name for name in _REQUIRED_FORMATS if not availability[name]]
        complete = not missing

        if status:
            status = deepcopy(status)
            status["status"] = "complete" if complete else "limited"
            status["required_formats"] = list(_REQUIRED_FORMATS)
            status["missing_formats"] = missing
            status["format_equivalence_ready"] = complete
            status["markdown_available"] = availability["markdown"]
            status["html_available"] = availability["html"]
            status["pdf_available"] = availability["pdf"]
            output["report_artifact_status"] = status

        if missing:
            output["report_format_error"] = (
                "The retained Mid report is incomplete. Missing required format(s): "
                + ", ".join(missing)
                + "."
            )
        else:
            output.pop("report_format_error", None)

        return output, complete

    setattr(rehydrate_with_complete_format_set, _PATCH_MARKER, True)
    setattr(rehydrate_with_complete_format_set, "_nico_previous", current)
    read_path._rehydrate_final_report = rehydrate_with_complete_format_set
    return {
        "status": "installed",
        "version": MID_TERMINAL_FORMAT_INTEGRITY_VERSION,
        "required_formats": list(_REQUIRED_FORMATS),
        "html_required_for_completion": True,
        "pdf_integrity_required_for_completion": True,
        "fail_closed": True,
    }


__all__ = [
    "MID_TERMINAL_FORMAT_INTEGRITY_VERSION",
    "install_mid_terminal_format_integrity",
]
