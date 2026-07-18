from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_report_generation_recovery.v1"
_PATCH_MARKER = "_nico_express_report_generation_recovery_v1"
_MAX_ATTEMPTS = 3
_REQUIRED_FORMATS = ("markdown", "html", "pdf_base64")


def _reports(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("reports")
    return value if isinstance(value, dict) else {}


def _usable_formats(result: dict[str, Any]) -> bool:
    reports = _reports(result)
    return all(bool(str(reports.get(name) or "").strip()) for name in _REQUIRED_FORMATS)


def _missing_formats(result: dict[str, Any]) -> list[str]:
    reports = _reports(result)
    return [name for name in _REQUIRED_FORMATS if not str(reports.get(name) or "").strip()]


def install_express_report_generation_recovery() -> dict[str, Any]:
    """Retry deterministic report rebuilding before Express can leave report generation.

    The async Express runner calls ``nico.api.main.finalize_express_result_consistency``
    exactly once. A partial renderer result previously flowed into the final gate and
    produced a blocked run with no report. This wrapper keeps the same run and result
    identity, retries only report reconstruction, and fails closed with explicit
    evidence when all bounded attempts are exhausted.
    """

    from nico.api import main as api_main
    from nico.report_truth_runtime_patch import rebuild_reports

    current: Callable[[dict[str, Any]], dict[str, Any]] = api_main.finalize_express_result_consistency
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def finalize_with_report_recovery(result: dict[str, Any]) -> dict[str, Any]:
        output = deepcopy(current(result))
        attempts = 1
        while not _usable_formats(output) and attempts < _MAX_ATTEMPTS:
            output = deepcopy(rebuild_reports(output))
            attempts += 1

        evidence = output.get("report_generation_recovery")
        evidence = deepcopy(evidence) if isinstance(evidence, dict) else {}
        evidence.update(
            {
                "version": PATCH_VERSION,
                "attempts": attempts,
                "maximum_attempts": _MAX_ATTEMPTS,
                "same_run_continuation": True,
                "duplicate_assessment_started": False,
                "required_formats": list(_REQUIRED_FORMATS),
                "usable_report_artifacts": _usable_formats(output),
                "missing_formats": _missing_formats(output),
            }
        )
        output["report_generation_recovery"] = evidence

        if _usable_formats(output):
            output["report_generation_status"] = "complete"
            output.pop("report_format_error", None)
            return output

        output["status"] = "blocked"
        output["report_generation_status"] = "blocked_missing_usable_artifacts"
        output["report_format_error"] = (
            "Express report generation exhausted bounded recovery without usable "
            "Markdown, HTML, and PDF artifacts."
        )
        output["recovery_required"] = True
        output["recovery_code"] = "express_report_generation_exhausted"
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
        return output

    setattr(finalize_with_report_recovery, _PATCH_MARKER, True)
    setattr(finalize_with_report_recovery, "_nico_previous", current)
    api_main.finalize_express_result_consistency = finalize_with_report_recovery
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "maximum_attempts": _MAX_ATTEMPTS,
        "same_run_only": True,
        "duplicate_assessment_started": False,
        "required_formats": list(_REQUIRED_FORMATS),
        "fail_closed": True,
    }


__all__ = [
    "PATCH_VERSION",
    "install_express_report_generation_recovery",
]
