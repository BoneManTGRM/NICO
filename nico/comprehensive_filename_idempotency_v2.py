from __future__ import annotations

import re
from typing import Any

VERSION = "nico.comprehensive_filename_idempotency.v2"
_FINAL_SUFFIX_RE = re.compile(r"(?:-FINAL-PENDING-APPROVAL)+\.pdf$", re.IGNORECASE)
_DRAFT_SUFFIX_RE = re.compile(r"-DRAFT\.pdf$", re.IGNORECASE)


def normalize_comprehensive_filename(value: Any) -> str:
    """Return exactly one final-pending-approval suffix for every PDF filename."""
    filename = str(value or "nico-comprehensive-assessment-FINAL-PENDING-APPROVAL.pdf")
    if _FINAL_SUFFIX_RE.search(filename):
        return _FINAL_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    if _DRAFT_SUFFIX_RE.search(filename):
        return _DRAFT_SUFFIX_RE.sub("-FINAL-PENDING-APPROVAL.pdf", filename)
    if filename.casefold().endswith(".pdf"):
        return filename[:-4] + "-FINAL-PENDING-APPROVAL.pdf"
    return filename + "-FINAL-PENDING-APPROVAL.pdf"


def install_comprehensive_filename_idempotency_v2() -> dict[str, Any]:
    from nico import comprehensive_canonical_report_truth_v1 as canonical

    current = getattr(canonical, "_normalize_filename", None)
    if current is normalize_comprehensive_filename:
        return {"status": "already_installed", "version": VERSION, "bound": True}

    canonical._normalize_filename = normalize_comprehensive_filename
    return {
        "status": "installed",
        "version": VERSION,
        "bound": canonical._normalize_filename is normalize_comprehensive_filename,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_filename_idempotency_v2",
    "normalize_comprehensive_filename",
]
