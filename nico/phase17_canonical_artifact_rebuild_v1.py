from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader

from nico.canonical_section_status_v1 import normalize_report_package
from nico.client_pdf_status_sanitizer_v1 import sanitize_client_pdf_status
from nico.client_text_status_sanitizer_v1 import sanitize_client_text_status
from nico.comprehensive_automated_draft_cross_format_v1 import (
    install_automated_draft_cross_format_contract,
)
from nico.comprehensive_client_surface_structure_cleanup_v1 import (
    install_client_surface_structure_cleanup_v1,
    project_client_stage_summaries,
)
from nico.comprehensive_client_truth_canonical_v2 import (
    install_comprehensive_client_truth_canonical_v2,
)
from nico.comprehensive_compact_design_marker_v1 import (
    install_compact_design_marker_gate,
)
from nico.comprehensive_decision_summary_truth_v1 import (
    install_comprehensive_decision_summary_truth_v1,
)
from nico.comprehensive_executive_summary_semantic_truth_v1 import (
    install_comprehensive_executive_summary_semantic_truth_v1,
)
from nico.comprehensive_human_review_package_cleanup_v1 import (
    install_comprehensive_human_review_package_cleanup_v1,
)
from nico.comprehensive_human_review_package_cleanup_compat_v1 import (
    install_comprehensive_human_review_package_cleanup_compat_v1,
)
from nico.comprehensive_incomplete_analyzer_summary_v1 import (
    install_comprehensive_incomplete_analyzer_summary,
)
from nico.comprehensive_markdown_identity_v1 import (
    install_comprehensive_markdown_identity_v1,
)
from nico.comprehensive_pdf_navigation_titles_v1 import (
    install_comprehensive_pdf_navigation_titles_v1,
)
from nico.comprehensive_placeholder_sanitization_v1 import (
    install_comprehensive_placeholder_sanitization,
)
from nico.comprehensive_platform_parity_summary_v1 import (
    install_comprehensive_platform_parity_summary,
)
from nico.comprehensive_rendered_package_reuse_v1 import (
    install_comprehensive_rendered_package_reuse_v1,
)
from nico.comprehensive_report_clarity_v1 import (
    install_comprehensive_report_clarity,
)
from nico.comprehensive_score_presence_truth_v1 import (
    install_comprehensive_score_presence_truth_v1,
)
from nico.comprehensive_spanish_generated_at_v1 import (
    install_comprehensive_spanish_generated_at_v1,
)
from nico.comprehensive_truth_diagnostics_v1 import (
    install_comprehensive_truth_diagnostics_v1,
)
from nico.comprehensive_zero_incomplete_validation_v1 import (
    install_comprehensive_zero_incomplete_validation_v1,
)
from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.scanner_command_repair_v1 import install_scanner_command_repair
from nico.scanner_evidence_contract_v2 import install_scanner_evidence_contract_v2
from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_automated_draft_quality_compat_v3 import (
    install_automated_draft_quality_compat,
    repair_localized_rendered_report,
    repair_rendered_report,
)
from nico.v2_client_ready_truth_projection_v1 import install_client_ready_truth_projection
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_report_quality_repairs import _is_spanish, repair_canonical_truth
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Repair concrete scanner commands before wrapping execution evidence. This keeps
# Bandit configuration deterministic and preserves one fail-closed scanner chain.
_SCANNER_COMMAND_REPAIR = install_scanner_command_repair()
_SCANNER_EVIDENCE_CONTRACT = install_scanner_evidence_contract_v2()
_AUTOMATED_DRAFT_CROSS_FORMAT = install_automated_draft_cross_format_contract()
_AUTOMATED_DRAFT_QUALITY_COMPAT = install_automated_draft_quality_compat()
_CANONICAL_CLIENT_TRUTH = install_comprehensive_client_truth_canonical_v2()
_SPANISH_GENERATED_AT = install_comprehensive_spanish_generated_at_v1()
_SCORE_PRESENCE_TRUTH = install_comprehensive_score_presence_truth_v1()
_TRUTH_DIAGNOSTICS = install_comprehensive_truth_diagnostics_v1()
_ZERO_INCOMPLETE_VALIDATION = install_comprehensive_zero_incomplete_validation_v1()
_DECISION_SUMMARY_TRUTH = install_comprehensive_decision_summary_truth_v1()
_MARKDOWN_IDENTITY = install_comprehensive_markdown_identity_v1()
_PDF_NAVIGATION_TITLES = install_comprehensive_pdf_navigation_titles_v1()
_RENDERED_PACKAGE_REUSE = install_comprehensive_rendered_package_reuse_v1()
_INCOMPLETE_ANALYZER_SUMMARY = install_comprehensive_incomplete_analyzer_summary()
_PLATFORM_PARITY_SUMMARY = install_comprehensive_platform_parity_summary()
_PLACEHOLDER_SANITIZATION = install_comprehensive_placeholder_sanitization()
_REPORT_CLARITY = install_comprehensive_report_clarity()
_COMPACT_DESIGN_MARKER_GATE = install_compact_design_marker_gate()
install_pipeline_projection()
install_client_ready_truth_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()
_EXECUTIVE_SUMMARY_SEMANTIC_TRUTH = (
    install_comprehensive_executive_summary_semantic_truth_v1()
)
# Install last after every renderer, compatibility layer, manifest, navigation,
# and semantic-truth extension so the final exact-artifact boundary validates the
# cleaned human-review package.
_HUMAN_REVIEW_PACKAGE_CLEANUP = (
    install_comprehensive_human_review_package_cleanup_v1()
)
_HUMAN_REVIEW_PACKAGE_CLEANUP_COMPAT = (
    install_comprehensive_human_review_package_cleanup_compat_v1()
)


def _reconcile(package: Mapping[str, Any]) -> dict[str, Any]:
    """Keep numeric score bands and assurance state separate after each truth pass."""

    return normalize_report_package(reconcile_production_report_truth(package))


def _sanitize_published_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    pdf = sanitize_client_pdf_status(
        base64.b64decode(str(result.get("pdf_base64") or ""))
    )
    markdown = sanitize_client_text_status(str(result.get("markdown") or ""))
    rendered_html = sanitize_client_text_status(str(result.get("html") or ""))
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    result.update(
        {
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown": markdown,
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html": rendered_html,
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
        }
    )
    completion = deepcopy(dict(result.get("client_report_completion") or {}))
    completion.update(
        {
            "unapproved_finality_removed_from_pdf_headers": True,
            "automated_draft_grammar_normalized": True,
            "canonical_incomplete_analyzer_summary_retained": True,
            "canonical_platform_parity_summary_retained": True,
            "parser_placeholders_absent": True,
            "candidate_section_summaries_deduplicated": True,
            "review_candidate_status_requires_human_review": True,
            "exact_source_complexity_truth_reconciled": bool(
                completion.get("exact_source_complexity_truth_reconciled")
            ),
            "compact_evidence_summary_design_marker_retained": True,
            "retired_raw_evidence_appendix_absent": True,
            "page_count": page_count,
        }
    )
    result["client_report_completion"] = completion
    return result


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build one bounded client package from canonical finding and scanner truth.

    Publication extensions patch ``client_report_completion_v2`` at runtime. Use
    the module attributes at execution time rather than stale function references
    captured when this module was imported. This guarantees that the final
    canonical truth pass occurs before rendering and that the final cross-format
    validator and exact-artifact manifest gate execute after sanitization.
    """

    from nico import client_report_completion_v2 as completion

    reconciled = _reconcile(package)
    prepared = repair_canonical_truth(reconciled)
    prepared = _reconcile(prepared)
    # Scanner applicability, scanner-outcome truth, canonical finding identity,
    # and the structured remediation register must exist before the premium
    # compiler derives stages, scores, executive findings, and artifact content.
    prepared = completion.prepare_client_report_package(prepared)
    # Preparation extensions can legitimately rebind shared renderers. Reassert
    # the client-surface structured-value contract at the exact render boundary.
    install_client_surface_structure_cleanup_v1()
    prepared = project_client_stage_summaries(prepared)

    # The first pass derives the complete canonical stage population. Normalize
    # only the derived client-facing stage fields, then render the final package
    # from that cleaned population. Complete roadmap, trend, scanner, finding,
    # and remediation source objects remain retained in canonical JSON.
    derived = rebuild_single_pass_premium_artifacts(prepared)
    final_input = project_client_stage_summaries(derived)
    rendered = rebuild_single_pass_premium_artifacts(final_input)

    canonical = rendered.get("json") if isinstance(rendered.get("json"), Mapping) else {}
    repaired = (
        repair_localized_rendered_report(rendered)
        if _is_spanish(canonical)
        else repair_rendered_report(rendered)
    )
    # Reconcile once more after report-quality repair, then sanitize every
    # mutable rendered surface before the exact-artifact finalizer computes the
    # PDF, Markdown, HTML, canonical JSON, and detached-manifest digests. No
    # renderer or sanitizer may change retained bytes after that binding point.
    repaired = _reconcile(repaired)
    sanitized = _sanitize_published_artifacts(repaired)
    return completion.finalize_client_report_package(sanitized)


__all__ = [
    "VERSION",
    "_SCANNER_COMMAND_REPAIR",
    "_SCANNER_EVIDENCE_CONTRACT",
    "_AUTOMATED_DRAFT_CROSS_FORMAT",
    "_AUTOMATED_DRAFT_QUALITY_COMPAT",
    "_CANONICAL_CLIENT_TRUTH",
    "_SPANISH_GENERATED_AT",
    "_SCORE_PRESENCE_TRUTH",
    "_TRUTH_DIAGNOSTICS",
    "_ZERO_INCOMPLETE_VALIDATION",
    "_DECISION_SUMMARY_TRUTH",
    "_MARKDOWN_IDENTITY",
    "_PDF_NAVIGATION_TITLES",
    "_RENDERED_PACKAGE_REUSE",
    "_INCOMPLETE_ANALYZER_SUMMARY",
    "_PLATFORM_PARITY_SUMMARY",
    "_PLACEHOLDER_SANITIZATION",
    "_REPORT_CLARITY",
    "_COMPACT_DESIGN_MARKER_GATE",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "_HUMAN_REVIEW_PACKAGE_CLEANUP",
    "_HUMAN_REVIEW_PACKAGE_CLEANUP_COMPAT",
    "_EXECUTIVE_SUMMARY_SEMANTIC_TRUTH",
    "rebuild_client_artifacts",
]
