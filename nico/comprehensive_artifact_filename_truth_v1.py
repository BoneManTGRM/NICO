from __future__ import annotations

import re
from functools import wraps
from typing import Any

VERSION = "nico.comprehensive-artifact-filename-truth.v1"
_MARKER = "__nico_comprehensive_artifact_filename_truth_v1__"
_TERMINAL_STATES = re.compile(
    r"(?:-(?:AUTOMATED-)?(?:DRAFT|FINAL))+(?:-PENDING-APPROVAL)?$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def install_comprehensive_artifact_filename_truth_v1() -> dict[str, Any]:
    from nico import v2_pipeline_adapter as adapter

    current = adapter._normalized_artifact_filename
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _normalized_artifact_filename(
        value: Any,
        *,
        default_name: str,
        extension: str,
    ) -> str:
        filename = _text(value) or default_name
        normalized_extension = extension if extension.startswith(".") else f".{extension}"
        if not filename.casefold().endswith(normalized_extension.casefold()):
            filename += normalized_extension
        stem = filename[: -len(normalized_extension)]
        while True:
            cleaned = _TERMINAL_STATES.sub("", stem)
            if cleaned == stem:
                break
            stem = cleaned
        stem = stem.rstrip("-_. ") or default_name[: -len(normalized_extension)]
        return f"{stem}-{adapter._APPROVAL_SUFFIX}{normalized_extension}"

    setattr(_normalized_artifact_filename, _MARKER, True)
    setattr(_normalized_artifact_filename, "_nico_previous", current)
    adapter._normalized_artifact_filename = _normalized_artifact_filename
    return {
        "status": "installed",
        "version": VERSION,
        "repeated_draft_final_suffixes_removed": True,
        "approval_suffix_exactly_once": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_artifact_filename_truth_v1",
]
