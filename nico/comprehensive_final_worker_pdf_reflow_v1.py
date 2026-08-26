from __future__ import annotations

from functools import wraps
from typing import Any

VERSION = "nico.comprehensive_final_worker_pdf_reflow.v1"
_MARKER = "__nico_final_worker_pdf_reflow_v1__"
_INSTALLED = False


def install_comprehensive_final_worker_pdf_reflow_v1() -> dict[str, Any]:
    """Bind sparse-page reflow inside the isolated final-report renderer process.

    The production parent process already installed the commercial presentation reflow,
    but final PDF generation happens in an isolated subprocess. Parent monkey patches do
    not cross that boundary. Source-language PDFs are then frozen byte-for-byte, so a
    reflow installed only in the parent can never repair the original 44-page artifact.

    This worker-local binding touches only the final navigation seam: sparse ordinary
    report pages are compacted first and the existing navigation layer then rebuilds
    physical page labels, TOC and bookmarks. Canonical JSON, scores, findings, review
    state and delivery authority are never mutated.
    """

    global _INSTALLED
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )
    from nico.comprehensive_pdf_reflow_v1 import compact_sparse_stage_pages

    install_comprehensive_manifest_navigation_v1()
    current = navigation._renumber_and_outline
    if getattr(current, _MARKER, False):
        _INSTALLED = True
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "reflow_before_final_navigation": True,
            "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
            "canonical_truth_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def reflow_then_renumber(pdf_bytes: bytes) -> bytes:
        reflowed, _manifest = compact_sparse_stage_pages(pdf_bytes)
        return current(reflowed)

    setattr(reflow_then_renumber, _MARKER, True)
    setattr(reflow_then_renumber, "_nico_previous", current)
    navigation._renumber_and_outline = reflow_then_renumber
    _INSTALLED = True
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "reflow_before_final_navigation": True,
        "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_final_worker_pdf_reflow_v1"]
