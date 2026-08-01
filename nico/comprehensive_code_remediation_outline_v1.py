from __future__ import annotations

import io
from typing import Any

VERSION = "nico.comprehensive_code_remediation_outline.v1"
_PATCH_MARKER = "_nico_comprehensive_code_remediation_outline_v1"


def _append_preserving_outline(
    original_bytes: bytes,
    *,
    identity: dict[str, Any],
    assessment: dict[str, Any],
    limitations: dict[str, int],
) -> tuple[bytes, int]:
    """Append remediation pages without discarding the base report outline.

    ``PdfWriter.add_page`` copies pages but not the existing outline tree. The
    decision-grade report already exposes bookmarks for its major sections, so the
    appendix must compose through ``PdfWriter.append(..., import_outline=True)``.
    """

    from pypdf import PdfReader, PdfWriter
    from nico import comprehensive_code_remediation_appendix_v1 as appendix

    base_reader = PdfReader(io.BytesIO(original_bytes))
    plan = (
        assessment.get("code_remediation_plan")
        if isinstance(assessment.get("code_remediation_plan"), list)
        else appendix.build_code_remediation_plan(assessment)
    )

    provisional = appendix._appendix_pdf(
        plan,
        base_page_count=len(base_reader.pages),
        final_page_count=len(base_reader.pages) + max(1, len(plan)),
    )
    provisional_reader = PdfReader(io.BytesIO(provisional))
    final_page_count = len(base_reader.pages) + len(provisional_reader.pages)
    appendix_reader = PdfReader(
        io.BytesIO(
            appendix._appendix_pdf(
                plan,
                base_page_count=len(base_reader.pages),
                final_page_count=final_page_count,
            )
        )
    )
    overlay_reader = PdfReader(
        io.BytesIO(
            appendix._page_count_overlay(
                identity,
                limitations,
                final_page_count,
            )
        )
    )

    for index, page in enumerate(base_reader.pages):
        if index < len(overlay_reader.pages):
            page.merge_page(overlay_reader.pages[index], over=True)

    writer = PdfWriter()
    writer.append(base_reader, import_outline=True)
    appendix_start = len(base_reader.pages)
    writer.append(appendix_reader, import_outline=False)
    try:
        writer.add_outline_item("Code Remediation Plan", appendix_start)
    except Exception:
        # The imported base outline is the required navigation contract. Older
        # pypdf releases may not support adding a new outline item consistently.
        pass

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), final_page_count


def install_comprehensive_code_remediation_outline_v1() -> dict[str, Any]:
    from nico import comprehensive_code_remediation_appendix_v1 as appendix
    from nico.comprehensive_pdf_outline_truth_v1 import (
        install_comprehensive_pdf_outline_truth_v1,
    )

    pdf_outline_truth = install_comprehensive_pdf_outline_truth_v1()
    current = appendix._append_code_pages
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "base_outline_preserved": True,
            "appendix_outline_added_when_supported": True,
            "final_page_count_preserved": True,
            "pdf_outline_truth": pdf_outline_truth,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    setattr(_append_preserving_outline, _PATCH_MARKER, True)
    setattr(_append_preserving_outline, "_nico_previous", current)
    appendix._append_code_pages = _append_preserving_outline
    return {
        "status": "installed",
        "version": VERSION,
        "base_outline_preserved": True,
        "appendix_outline_added_when_supported": True,
        "final_page_count_preserved": True,
        "pdf_outline_truth": pdf_outline_truth,
        "automatic_merge_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_append_preserving_outline",
    "install_comprehensive_code_remediation_outline_v1",
]
