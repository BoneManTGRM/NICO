from __future__ import annotations

import unicodedata
from typing import Any

VERSION = "nico.client-pdf-status-sanitizer.v7"
_MARKER = "__nico_client_pdf_status_sanitizer_v7__"
_PRESERVED_REVIEW_MARKERS = (
    "nico | comprehensive client review | automated draft",
    "section 1 of 8 | page 1 of 2",
    "section 2 of 8 | page 1 of 2",
    "section 3 of 8 | page 1 of 2",
    "section 4 of 8 | page 1 of 2",
    "section 5 of 8 | page 1 of 2",
    "section 6 of 8 | page 1 of 2",
    "section 7 of 8 | page 1 of 2",
    "section 8 of 8 | page 1 of 2",
    "human decision pending | delivery blocked",
    "automated draft | human review required",
)


def _normalized(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def install_client_pdf_status_sanitizer_v7() -> dict[str, Any]:
    from nico import client_pdf_status_sanitizer_v1 as sanitizer

    current = sanitizer._drop_internal_page
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "client_review_pages_preserved": True,
        }

    def _drop_internal_page(text: str) -> bool:
        normalized = _normalized(text)
        if any(marker in normalized for marker in _PRESERVED_REVIEW_MARKERS):
            return False
        return current(text)

    setattr(_drop_internal_page, _MARKER, True)
    setattr(_drop_internal_page, "_nico_previous", current)
    sanitizer._drop_internal_page = _drop_internal_page
    return {
        "status": "installed",
        "version": VERSION,
        "client_review_pages_preserved": True,
        "raw_internal_pages_still_removed": True,
        "automated_draft_boundary_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_client_pdf_status_sanitizer_v7"]
