from __future__ import annotations

import re
from functools import wraps
from typing import Any

VERSION = "nico.comprehensive-pdf-navigation-titles.v1"
_MARKER = "__nico_comprehensive_pdf_navigation_titles_v1__"
_PAGE_LABELS = (
    re.compile(r"^(?:Page|Página)\s+\d+(?:\s+of\s+\d+)?$", re.IGNORECASE),
    re.compile(
        r"^Section\s+\d+\s+of\s+\d+\s*\|\s*(?:Page|Sheet)\s+\d+\s+of\s+\d+$",
        re.IGNORECASE,
    ),
    re.compile(r"^Integrity(?:\s+sheet)?\s+\d+$", re.IGNORECASE),
    re.compile(r"^Document\s+page\s+\d+\s+of\s+\d+$", re.IGNORECASE),
)
_SKIP_EXACT = {
    "NICO",
    "AUTOMATED DRAFT | HUMAN REVIEW REQUIRED",
    "HUMAN DECISION PENDING | DELIVERY BLOCKED",
    "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
    "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
    "REVIEW PACKAGE READY · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED",
}


def _text(value: Any, limit: int = 160) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _is_page_label(value: str) -> bool:
    return any(pattern.fullmatch(value) for pattern in _PAGE_LABELS)


def install_comprehensive_pdf_navigation_titles_v1() -> dict[str, Any]:
    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._outline_title
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _outline_title(text: str) -> str:
        lines = [_text(line) for line in str(text or "").splitlines() if _text(line)]
        for line in lines[:24]:
            if line in _SKIP_EXACT:
                continue
            if line.startswith("NICO |") or line.startswith("NICO Comprehensive ·"):
                continue
            if _is_page_label(line) or re.fullmatch(r"\d+(?:/100)?", line):
                continue
            return line[:100]
        return "Report page"

    setattr(_outline_title, _MARKER, True)
    setattr(_outline_title, "_nico_previous", current)
    navigation._outline_title = _outline_title
    return {
        "status": "installed",
        "version": VERSION,
        "generic_page_labels_excluded_from_toc": True,
        "review_section_titles_retained": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_pdf_navigation_titles_v1",
]
