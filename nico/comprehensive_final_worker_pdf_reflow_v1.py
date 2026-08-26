from __future__ import annotations

import re
from functools import wraps
from typing import Any

VERSION = "nico.comprehensive_final_worker_pdf_reflow.v1.7"
_MARKER = "__nico_final_worker_pdf_reflow_v1__"
_SEMANTIC_MARKER = "__nico_final_worker_semantic_navigation_v1__"
_INSTALLED = False


def install_comprehensive_final_worker_pdf_reflow_v1() -> dict[str, Any]:
    """Bind safe compaction, localized metadata labels, and semantic navigation.

    Display metadata persistence remains stable source behavior in the canonical intake,
    detached-worker identity projection, and report package builder. This worker-local
    installer changes presentation only: es-MX metadata labels, sparse-page reflow, final
    semantic TOC/bookmarks, and physical page labels.
    """

    global _INSTALLED
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import comprehensive_pdf_reflow_v1 as pdf_reflow
    from nico.comprehensive_bilingual_navigation_validation_v1 import (
        install_bilingual_navigation_validation_v1,
    )
    from nico.comprehensive_display_metadata_localization_v1 import (
        install_display_metadata_localization_v1,
    )
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )
    from nico.comprehensive_semantic_navigation_v1 import (
        semantic_renumber_and_outline,
    )

    pdf_reflow._HEADER = re.compile(
        r"^NICO\s+Comprehensive\b.*(?:AUTOMATED\s+DRAFT|BORRADOR\s+AUTOMATIZADO)",
        re.I,
    )

    metadata_localization = install_display_metadata_localization_v1()
    install_comprehensive_manifest_navigation_v1()
    bilingual_validation = install_bilingual_navigation_validation_v1()
    current = navigation._renumber_and_outline
    if getattr(current, _SEMANTIC_MARKER, False):
        _INSTALLED = True
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "display_metadata_preservation_is_stable_source": True,
            "display_metadata_es_mx_labels_bound": (
                metadata_localization.get("status") in {"installed", "already_installed"}
            ),
            "reflow_before_final_navigation": True,
            "bilingual_source_headers_supported": True,
            "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
            "semantic_multi_heading_toc": True,
            "shared_page_sections_retained_in_toc": True,
            "mexican_spanish_toc_validation_supported": (
                bilingual_validation.get("mexican_spanish_toc_validation_supported") is True
            ),
            "canonical_truth_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def reflow_then_renumber(pdf_bytes: bytes) -> bytes:
        reflowed, _manifest = pdf_reflow.compact_sparse_stage_pages(pdf_bytes)
        return semantic_renumber_and_outline(reflowed)

    setattr(reflow_then_renumber, _MARKER, True)
    setattr(reflow_then_renumber, _SEMANTIC_MARKER, True)
    setattr(reflow_then_renumber, "_nico_previous", current)
    navigation._renumber_and_outline = reflow_then_renumber
    _INSTALLED = True
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "display_metadata_preservation_is_stable_source": True,
        "display_metadata_es_mx_labels_bound": (
            metadata_localization.get("status") in {"installed", "already_installed"}
        ),
        "reflow_before_final_navigation": True,
        "bilingual_source_headers_supported": True,
        "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
        "semantic_multi_heading_toc": True,
        "shared_page_sections_retained_in_toc": True,
        "mexican_spanish_toc_validation_supported": (
            bilingual_validation.get("mexican_spanish_toc_validation_supported") is True
        ),
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_final_worker_pdf_reflow_v1"]
