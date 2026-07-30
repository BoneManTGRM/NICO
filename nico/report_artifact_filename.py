from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.report-artifact-filename.v1"

_PENDING_SUFFIX = "FINAL-PENDING-APPROVAL"
_PENDING_PATTERN = re.compile(
    r"(?:-(?:FINAL-)?PENDING-APPROVAL)+(?:-(?:FINAL-)?PENDING-APPROVAL)*$",
    re.IGNORECASE,
)
_DUPLICATED_FINAL_PATTERN = re.compile(
    r"(?:-FINAL-PENDING-APPROVAL){2,}$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_pdf_filename(value: Any, *, pending_approval: bool = True) -> Any:
    """Return one stable lifecycle suffix without changing the report identity stem."""
    if not isinstance(value, str) or not value.casefold().endswith(".pdf"):
        return value

    filename = value.strip()
    stem = filename[:-4]
    stem = _DUPLICATED_FINAL_PATTERN.sub("", stem)
    stem = _PENDING_PATTERN.sub("", stem)
    stem = stem.rstrip("-_. ")
    suffix = f"-{_PENDING_SUFFIX}" if pending_approval else ""
    return f"{stem}{suffix}.pdf"


def _normalize_container(value: Any, *, pending_approval: bool) -> Any:
    if isinstance(value, Mapping):
        repaired: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key.casefold().endswith("filename"):
                repaired[key] = normalize_pdf_filename(
                    raw_value,
                    pending_approval=pending_approval,
                )
            else:
                repaired[key] = _normalize_container(
                    raw_value,
                    pending_approval=pending_approval,
                )
        return repaired
    if isinstance(value, list):
        return [
            _normalize_container(item, pending_approval=pending_approval)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _normalize_container(item, pending_approval=pending_approval)
            for item in value
        )
    return deepcopy(value)


def normalize_report_artifact_filenames(package: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize all PDF filename fields and record the idempotent lifecycle contract."""
    approval = _text(package.get("approval_status")).casefold()
    delivery = _text(package.get("delivery_status")).casefold()
    pending = (
        not approval
        or "pending" in approval
        or "pending" in delivery
        or package.get("human_review_required") is True
    )
    result = _normalize_container(dict(package), pending_approval=pending)
    contract = deepcopy(dict(result.get("artifact_filename_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "idempotent_pdf_filename": True,
            "single_pending_approval_suffix": pending,
        }
    )
    result["artifact_filename_contract"] = contract
    return result


__all__ = [
    "VERSION",
    "normalize_pdf_filename",
    "normalize_report_artifact_filenames",
]
