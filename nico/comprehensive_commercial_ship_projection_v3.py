from __future__ import annotations

import re
from functools import wraps
from typing import Any, Mapping

from nico import comprehensive_commercial_ship_projection_v1 as v1
from nico import comprehensive_pdf_reflow_v1 as pdf_reflow
from nico.comprehensive_commercial_ship_projection_v2 import (
    _deployment_metric_order_independent,
)

VERSION = "nico.comprehensive_commercial_ship_projection.v3.2"
_STAGE_MARKER = "__nico_commercial_ship_stage_projection_v3__"
_NAV_MARKER = "__nico_commercial_ship_navigation_projection_v3__"
_LOCALE_MARKER = "__nico_commercial_ship_locale_projection_v3__"
_RESPONSE_MARKER = "__nico_commercial_ship_pdf_response_v3__"
_INSTALLED = False

# Correct the helper before any stage projection is evaluated.
v1._is_deployment_metric = _deployment_metric_order_independent
# The Spanish renderer localizes the running page header from AUTOMATED DRAFT to
# BORRADOR AUTOMATIZADO. The sparse-page reflow is locale-neutral, so recognize both
# approved source-language header forms without changing any rendered report copy.
pdf_reflow._HEADER = re.compile(
    r"^NICO\s+Comprehensive\b.*(?:AUTOMATED\s+DRAFT|BORRADOR\s+AUTOMATIZADO)",
    re.I,
)


def project_canonical_for_client_presentation(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    return v1.project_canonical_for_client_presentation(canonical)


def compact_sparse_limitation_pages(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Run both bounded sparse-page compactors before final navigation is rebuilt."""

    limitation_pdf, limitation_manifest = v1.compact_sparse_limitation_pages(pdf_bytes)
    reflowed_pdf, reflow_manifest = pdf_reflow.compact_sparse_stage_pages(limitation_pdf)
    original_pages = int(limitation_manifest.get("original_pages") or 0)
    final_pages = int(reflow_manifest.get("final_pages") or limitation_manifest.get("final_pages") or original_pages)
    pages_removed = max(0, original_pages - final_pages)
    return reflowed_pdf, {
        "status": "compacted" if pages_removed else "unchanged",
        "original_pages": original_pages,
        "final_pages": final_pages,
        "compacted_groups": int(limitation_manifest.get("compacted_groups") or 0)
        + int(reflow_manifest.get("compacted_groups") or 0),
        "pages_removed": pages_removed,
        "truth_preserved": limitation_manifest.get("truth_preserved") is True
        and reflow_manifest.get("truth_preserved") is True,
        "canonical_truth_mutated": False,
        "limitation_compaction": limitation_manifest,
        "sparse_stage_reflow": reflow_manifest,
    }


def install_comprehensive_commercial_ship_projection_v3() -> dict[str, Any]:
    """Bind presentation-only ship fixes without replacing final assembled source PDFs."""

    global _INSTALLED
    if _INSTALLED:
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "final_assembled_source_pdf_preserved": True,
            "sparse_stage_reflow_before_final_navigation": True,
            "localized_sparse_stage_reflow_supported": True,
            "canonical_truth_mutated": False,
            "assessment_rerun": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    from nico import comprehensive_final_six_client_report_cleanup_v1 as final_six
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import comprehensive_same_run_locale_report_v1 as locale_report
    from nico import comprehensive_spanish_canonical_report_v87 as spanish_report
    from nico.comprehensive_final_six_client_report_cleanup_v1 import (
        install_final_six_client_report_cleanup_v1,
    )
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )

    # Ensure the existing mature client composer/navigation layers own the final package,
    # then wrap only their presentation seams.
    install_final_six_client_report_cleanup_v1()
    install_comprehensive_manifest_navigation_v1()

    current_stage = final_six.sanitize_client_report_stage
    if not getattr(current_stage, _STAGE_MARKER, False):

        @wraps(current_stage)
        def stage_projection(stage: Mapping[str, Any]) -> dict[str, Any]:
            return v1._project_stage(current_stage(stage))

        setattr(stage_projection, _STAGE_MARKER, True)
        setattr(stage_projection, "_nico_previous", current_stage)
        final_six.sanitize_client_report_stage = stage_projection

    current_renumber = navigation._renumber_and_outline
    if not getattr(current_renumber, _NAV_MARKER, False):

        @wraps(current_renumber)
        def renumber_after_compaction(pdf: bytes) -> bytes:
            compacted, _manifest = compact_sparse_limitation_pages(pdf)
            # Rebuild physical page labels, TOC, and bookmarks after both bounded
            # sparse-page passes. Canonical assessment truth is never mutated.
            return current_renumber(compacted)

        setattr(renumber_after_compaction, _NAV_MARKER, True)
        setattr(renumber_after_compaction, "_nico_previous", current_renumber)
        navigation._renumber_and_outline = renumber_after_compaction

    # Cross-locale renders derive from a deep-copied canonical snapshot. The source
    # language continues to use the fully assembled frozen artifact produced by the run.
    for attribute in ("_english_artifacts", "_spanish_artifacts"):
        current = getattr(locale_report, attribute)
        if getattr(current, _LOCALE_MARKER, False):
            continue

        @wraps(current)
        def localized_artifacts(
            canonical: Mapping[str, Any],
            _current: Any = current,
        ) -> dict[str, Any]:
            projected = project_canonical_for_client_presentation(canonical)
            artifacts = _current(projected)
            return v1._compact_artifacts(artifacts)

        setattr(localized_artifacts, _LOCALE_MARKER, True)
        setattr(localized_artifacts, "_nico_previous", current)
        setattr(locale_report, attribute, localized_artifacts)

    current_dynamic = getattr(spanish_report, "_localize_dynamic_sentence", None)
    if current_dynamic is not None and not getattr(current_dynamic, _LOCALE_MARKER, False):
        v1._ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR = current_dynamic
        translated = v1._spanish_dynamic_translation
        setattr(translated, _LOCALE_MARKER, True)
        setattr(translated, "_nico_previous", current_dynamic)
        spanish_report._localize_dynamic_sentence = translated

    current_response = locale_report.build_same_run_locale_pdf_response
    if not getattr(current_response, _RESPONSE_MARKER, False):

        @wraps(current_response)
        def pdf_response(status: Mapping[str, Any], report_language: str) -> Any:
            response = current_response(status, report_language)
            repository = str(status.get("repository") or "").strip()
            commit_sha = str(status.get("commit_sha") or "").strip()
            if repository:
                response.headers["X-NICO-Repository"] = repository
            if commit_sha:
                response.headers["X-NICO-Commit-SHA"] = commit_sha
            response.headers["X-NICO-Artifact-Scope"] = "client-facing-same-run-projection"
            response.headers["X-NICO-Assessment-Rerun"] = "false"
            response.headers["X-NICO-Approval-State-Mutated"] = "false"
            response.headers["X-NICO-Delivery-State-Mutated"] = "false"
            return response

        setattr(pdf_response, _RESPONSE_MARKER, True)
        setattr(pdf_response, "_nico_previous", current_response)
        locale_report.build_same_run_locale_pdf_response = pdf_response

    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "presentation_only_projection": True,
        "processing_complete_distinguished_from_evidence_sufficiency": True,
        "deployment_metric_detection_order_independent": True,
        "deployment_outcomes_mutually_exclusive_when_failure_classification_available": True,
        "intermediate_pdf_page_count_scoped": True,
        "sparse_limitation_compaction_before_final_navigation": True,
        "sparse_stage_reflow_before_final_navigation": True,
        "localized_sparse_stage_reflow_supported": True,
        "toc_page_labels_and_bookmarks_rebuilt_after_compaction": True,
        "final_assembled_source_pdf_preserved": True,
        "cross_locale_projection_from_same_canonical_snapshot": True,
        "exact_run_repository_commit_locale_headers": True,
        "canonical_truth_mutated": False,
        "assessment_rerun": False,
        "approval_state_mutated": False,
        "delivery_state_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "compact_sparse_limitation_pages",
    "install_comprehensive_commercial_ship_projection_v3",
    "project_canonical_for_client_presentation",
]
