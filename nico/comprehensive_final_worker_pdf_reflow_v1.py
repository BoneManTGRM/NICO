from __future__ import annotations

import re
from collections.abc import Mapping
from functools import wraps
from typing import Any

VERSION = "nico.comprehensive_final_worker_pdf_reflow.v1.4"
_MARKER = "__nico_final_worker_pdf_reflow_v1__"
_DISPLAY_MARKER = "__nico_final_worker_display_metadata_fallback_v1__"
_INSTALLED = False


def _install_display_metadata_fallback() -> None:
    """Recover report-only display metadata from durable retained evidence."""

    import nico.comprehensive_report_review_integrity_v1 as integrity

    current = integrity._display_values
    if getattr(current, _DISPLAY_MARKER, False):
        return

    def display_values_with_durable_fallback(record: Mapping[str, Any]) -> dict[str, str]:
        values = dict(current(record))
        human_evidence = (
            record.get("human_evidence")
            if isinstance(record.get("human_evidence"), Mapping)
            else {}
        )
        if not values.get("customer_name"):
            values["customer_name"] = integrity._find_evidence_value(
                human_evidence, "customer_name"
            ) or integrity._find_evidence_value(human_evidence, "client_name")
        if not values.get("project_name"):
            values["project_name"] = integrity._find_evidence_value(
                human_evidence, "project_name"
            )
        if not values.get("primary_technical_contact"):
            values["primary_technical_contact"] = integrity._find_evidence_value(
                human_evidence, "primary_technical_contact"
            )
        return values

    setattr(display_values_with_durable_fallback, _DISPLAY_MARKER, True)
    setattr(display_values_with_durable_fallback, "_nico_previous", current)
    integrity._display_values = display_values_with_durable_fallback


def install_comprehensive_final_worker_pdf_reflow_v1() -> dict[str, Any]:
    """Bind final metadata retention, sparse reflow and semantic navigation."""

    global _INSTALLED
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import comprehensive_pdf_reflow_v1 as pdf_reflow
    from nico.comprehensive_final_display_metadata_v92 import (
        install_comprehensive_final_display_metadata_v92,
    )
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )
    from nico.comprehensive_semantic_navigation_v3 import (
        install_comprehensive_semantic_navigation_v3,
    )

    _install_display_metadata_fallback()
    pdf_reflow._HEADER = re.compile(
        r"^NICO\s+Comprehensive\b.*(?:AUTOMATED\s+DRAFT|BORRADOR\s+AUTOMATIZADO)",
        re.I,
    )

    final_display_metadata = install_comprehensive_final_display_metadata_v92()
    install_comprehensive_manifest_navigation_v1()
    semantic_navigation = install_comprehensive_semantic_navigation_v3()
    current = navigation._renumber_and_outline
    if getattr(current, _MARKER, False):
        _INSTALLED = True
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "durable_report_display_metadata_fallback": True,
            "final_builder_display_metadata_preserved": final_display_metadata.get("bound") is True,
            "primary_technical_contact_preserved": final_display_metadata.get("primary_technical_contact_preserved") is True,
            "reflow_before_final_navigation": True,
            "semantic_navigation_bound": semantic_navigation.get("bound") is True,
            "semantic_navigation_non_recursive": semantic_navigation.get("non_recursive_fallback") is True,
            "multiple_sections_per_page_toc_supported": semantic_navigation.get("multiple_sections_per_page_supported") is True,
            "bilingual_toc_and_page_labels": semantic_navigation.get("bilingual_toc_and_page_labels") is True,
            "bilingual_source_headers_supported": True,
            "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
            "canonical_truth_mutated": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def reflow_then_renumber(pdf_bytes: bytes) -> bytes:
        reflowed, _manifest = pdf_reflow.compact_sparse_stage_pages(pdf_bytes)
        return current(reflowed)

    setattr(reflow_then_renumber, _MARKER, True)
    setattr(reflow_then_renumber, "_nico_previous", current)
    navigation._renumber_and_outline = reflow_then_renumber
    _INSTALLED = True
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "durable_report_display_metadata_fallback": True,
        "final_builder_display_metadata_preserved": final_display_metadata.get("bound") is True,
        "primary_technical_contact_preserved": final_display_metadata.get("primary_technical_contact_preserved") is True,
        "reflow_before_final_navigation": True,
        "semantic_navigation_bound": semantic_navigation.get("bound") is True,
        "semantic_navigation_non_recursive": semantic_navigation.get("non_recursive_fallback") is True,
        "multiple_sections_per_page_toc_supported": semantic_navigation.get("multiple_sections_per_page_supported") is True,
        "bilingual_toc_and_page_labels": semantic_navigation.get("bilingual_toc_and_page_labels") is True,
        "bilingual_source_headers_supported": True,
        "toc_page_labels_and_bookmarks_rebuilt_after_reflow": True,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_final_worker_pdf_reflow_v1"]
