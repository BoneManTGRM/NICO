from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_report_filename.v48"
_PATCH_MARKER = "_nico_comprehensive_final_report_filename_v48"
_SUFFIX_RE = re.compile(r"(?:-(?:DRAFT|FINAL-PENDING-APPROVAL))+\.pdf$", re.IGNORECASE)


def canonical_final_report_filename(value: Any) -> str:
    filename = str(value or "nico-comprehensive-final-report.pdf").strip()
    stem = _SUFFIX_RE.sub("", filename)
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    return f"{stem}-FINAL-PENDING-APPROVAL.pdf"


def install_comprehensive_final_report_filename_v48() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report_module

    current: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def build_with_canonical_filename(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        package = result.get("report_package")
        if isinstance(package, dict):
            package["pdf_filename"] = canonical_final_report_filename(package.get("pdf_filename"))
            quality = package.get("report_quality_contract")
            if not isinstance(quality, dict):
                quality = {}
                package["report_quality_contract"] = quality
            quality["canonical_final_report_filename"] = True
            quality["final_report_filename_version"] = VERSION
            result["report_quality_contract"] = dict(quality)
        return result

    setattr(build_with_canonical_filename, _PATCH_MARKER, True)
    setattr(build_with_canonical_filename, "_nico_previous", current)
    report_module.build_comprehensive_report_package = build_with_canonical_filename
    return {
        "status": "installed",
        "version": VERSION,
        "bound": report_module.build_comprehensive_report_package is build_with_canonical_filename,
        "idempotent_filename": True,
        "draft_suffix_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_final_report_filename",
    "install_comprehensive_final_report_filename_v48",
]
