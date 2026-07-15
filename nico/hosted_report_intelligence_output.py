from __future__ import annotations

import sys
from typing import Any, Callable

PATCH_VERSION = "nico.hosted_report_intelligence_output.v1"
_MARKER = "_nico_hosted_report_intelligence_output_v1"


def rebuild_report_intelligence_exports(hosted: Any, result: dict[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(result, dict)
        or result.get("status") != "complete"
        or not result.get("repair_intelligence")
    ):
        return result

    markdown = hosted.build_markdown(result)
    reports = dict(result.get("reports") or {})
    reports["markdown"] = markdown
    reports["html"] = hosted.build_html(markdown)
    pdf_base64, pdf_error = hosted.build_pdf_base64(markdown)
    if pdf_base64:
        reports["pdf_base64"] = pdf_base64
        reports["pdf_filename"] = (
            f"nico-express-assessment-{str(result.get('repository') or 'repository').replace('/', '-')}.pdf"
        )
        reports.pop("pdf_error", None)
    elif pdf_error:
        reports["pdf_error"] = pdf_error
        result.setdefault("unavailable_data_notes", [])
        if pdf_error not in result["unavailable_data_notes"]:
            result["unavailable_data_notes"].append(pdf_error)
    result["reports"] = reports
    result["report_intelligence_export"] = {
        "status": "complete",
        "markdown_includes_repair_intelligence": "## Prioritized Repair Intelligence" in markdown,
        "markdown_includes_repository_quality": "## Repository Quality and Governance Signals" in markdown,
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "human_review_required": True,
    }
    return result


def install_hosted_report_intelligence_output() -> dict[str, Any]:
    from nico import hosted_assessment as hosted

    current: Callable[[dict[str, Any]], dict[str, Any]] = hosted.run_github_assessment
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "report_exports_rebuilt": True,
        }
    original = current

    def run_with_rebuilt_intelligence_exports(payload: dict[str, Any]) -> dict[str, Any]:
        result = original(payload)
        return rebuild_report_intelligence_exports(hosted, result)

    setattr(run_with_rebuilt_intelligence_exports, _MARKER, True)
    setattr(run_with_rebuilt_intelligence_exports, "_nico_previous", original)
    hosted.run_github_assessment = run_with_rebuilt_intelligence_exports

    rebound = 0
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, "run_github_assessment", None) is original:
                setattr(module, "run_github_assessment", run_with_rebuilt_intelligence_exports)
                rebound += 1
        except Exception:
            continue

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "report_exports_rebuilt": True,
        "rebound_import_references": rebound,
        "code_changes_applied": False,
        "automatic_application_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "install_hosted_report_intelligence_output",
    "rebuild_report_intelligence_exports",
]
