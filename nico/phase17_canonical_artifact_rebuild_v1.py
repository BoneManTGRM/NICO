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
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
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
from nico.comprehensive_human_review_worksheet_title_contract_v1 import (
    install_human_review_worksheet_title_contract_v1,
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
_HUMAN_REVIEW_WORKSHEET_TITLE_CONTRACT = (
    install_human_review_worksheet_title_contract_v1()
)

_PHASE2_REVIEW_TRUTH_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "Score effect: assurance-only until triaged.",
        "Score effect: assurance-only while authorized human disposition remains pending; NICO technical-triage status is reported separately.",
    ),
    (
        "Assurance-only until triaged",
        "Human disposition pending; NICO technical-triage status is reported separately",
    ),
    (
        "Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
        "Efecto en la puntuación: solo aseguramiento mientras la disposición humana autorizada siga pendiente; el estado del triaje técnico de NICO se informa por separado.",
    ),
)


def _phase2_review_truth_text(value: str) -> str:
    output = str(value or "")
    for previous, replacement in _PHASE2_REVIEW_TRUTH_REPLACEMENTS:
        output = output.replace(previous, replacement)
    return output


def _phase2_review_truth_node(value: Any) -> Any:
    """Synchronize Phase 2 triage/disposition terminology without changing evidence."""

    if isinstance(value, str):
        return _phase2_review_truth_text(value)
    if isinstance(value, list):
        return [_phase2_review_truth_node(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_phase2_review_truth_node(item) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _phase2_review_truth_node(item)
            for key, item in value.items()
        }
    return value


def _rewrite_phase2_review_truth_pdf(pdf: bytes) -> bytes:
    """Repair only stale Phase 2 review wording in the already-rendered PDF."""

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        for operands, operator in stream.operations:
            if operator in {b"Tj", b"'", b'"'}:
                targets = operands
            elif operator == b"TJ" and operands:
                targets = operands[0]
            else:
                continue
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                    updated = _phase2_review_truth_text(original)
                    if updated != original:
                        targets[index] = TextStringObject(updated)
                        changed = True
                elif isinstance(operand, ByteStringObject):
                    original = bytes(operand)
                    updated = original
                    for previous, replacement in _PHASE2_REVIEW_TRUTH_REPLACEMENTS:
                        for encoding in ("utf-8", "latin-1"):
                            try:
                                updated = updated.replace(
                                    previous.encode(encoding),
                                    replacement.encode(encoding),
                                )
                            except UnicodeEncodeError:
                                continue
                    if updated != original:
                        targets[index] = ByteStringObject(updated)
                        changed = True
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _reconcile(package: Mapping[str, Any]) -> dict[str, Any]:
    """Keep numeric score bands and assurance state separate after each truth pass."""

    return normalize_report_package(reconcile_production_report_truth(package))


def _sanitize_published_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    # This is the last mutable cross-format boundary before exact artifact hashes are
    # bound. Repair the narrow Phase 2 wording here so JSON/CSV/text/PDF cannot diverge.
    result = deepcopy(dict(_phase2_review_truth_node(package)))
    pdf = sanitize_client_pdf_status(
        base64.b64decode(str(result.get("pdf_base64") or ""))
    )
    pdf = _rewrite_phase2_review_truth_pdf(pdf)
    markdown = _phase2_review_truth_text(
        sanitize_client_text_status(str(result.get("markdown") or ""))
    )
    rendered_html = _phase2_review_truth_text(
        sanitize_client_text_status(str(result.get("html") or ""))
    )
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
            "phase2_review_truth_language_synchronized": True,
            "technical_triage_separate_from_human_disposition": True,
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


def _reassert_terminal_report_language_authority() -> dict[str, Any]:
    """Rebind language truth after every mutable render/compatibility extension."""

    from nico.comprehensive_terminal_report_language_authority_v83 import (
        install_comprehensive_terminal_report_language_authority_v83,
    )

    state = install_comprehensive_terminal_report_language_authority_v83()
    required = (
        "persisted_run_identity_outranks_root_projection",
        "final_truth_language_bound",
        "final_truth_ci_markers_bound",
        "final_truth_ci_lines_bound",
        "final_surface_validator_bound",
        "independent_markdown_html_pdf_validation",
        "mixed_language_structural_markers_fail_closed",
        "human_review_required",
    )
    missing = [flag for flag in required if state.get(flag) is not True]
    if state.get("client_delivery_allowed") is not False:
        missing.append("client_delivery_allowed_false")
    if missing:
        raise RuntimeError(
            "phase17_terminal_report_language_authority_incomplete:"
            + ",".join(missing)
        )
    return state


def _populate_premium_stage_summaries(package: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the final stage population without rendering Markdown, HTML, or PDF.

    ``install_client_surface_structure_cleanup_v1`` binds the premium stage builder
    before this helper is called. Using that same runtime builder preserves the exact
    stage population and client-surface cleanup that the old first render produced,
    while avoiding an entire throw-away Spanish Markdown/HTML/PDF render.
    """

    from nico import v2_premium_report_renderer as premium

    result = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(result.get("json") or {}))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
    stages = [
        deepcopy(dict(item))
        for item in premium._canonical_stages(canonical)
        if isinstance(item, Mapping)
    ]
    assessment = (
        deepcopy(dict(canonical.get("assessment") or {}))
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    canonical["stage_summaries"] = deepcopy(stages)
    assessment["stage_summaries"] = deepcopy(stages)
    canonical["assessment"] = assessment
    result["json"] = canonical
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
    from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
        release_comprehensive_spanish_render_input_cache_v94,
    )

    try:
        reconciled = _phase2_review_truth_node(_reconcile(package))
        prepared = repair_canonical_truth(reconciled)
        prepared = _phase2_review_truth_node(_reconcile(prepared))
        # The final truth prepare wrapper is itself a stage-evidence normalization
        # boundary. Install the structured-value cleaner before preparation so no
        # retained mapping can be irreversibly converted to Python object text.
        install_client_surface_structure_cleanup_v1()
        # Scanner applicability, scanner-outcome truth, canonical finding identity,
        # and the structured remediation register must exist before the premium
        # compiler derives stages, scores, executive findings, and artifact content.
        prepared = completion.prepare_client_report_package(prepared)
        # Preparation extensions can legitimately rebind shared renderers. Reassert
        # the client-surface and worksheet-title contracts at the exact render boundary.
        install_client_surface_structure_cleanup_v1()
        install_human_review_worksheet_title_contract_v1()

        # Derive the complete canonical stage population directly through the same
        # runtime-bound stage builder used by the renderer. The previous implementation
        # performed a full throw-away premium render only to discover these stages, then
        # rendered every Spanish artifact a second time. Populate and sanitize the stage
        # contract first so the expensive renderer executes exactly once.
        prepared = _populate_premium_stage_summaries(prepared)
        prepared = _phase2_review_truth_node(project_client_stage_summaries(prepared))
        install_human_review_worksheet_title_contract_v1()
        rendered = rebuild_single_pass_premium_artifacts(prepared)

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
        repaired = _phase2_review_truth_node(_reconcile(repaired))
        sanitized = _sanitize_published_artifacts(repaired)
        # Some compatibility extensions legitimately rebind global report helpers during
        # preparation/rendering. Reassert the terminal language producer and validator at
        # the exact last mutable boundary, immediately before client-report finalization.
        _reassert_terminal_report_language_authority()
        finalized = completion.finalize_client_report_package(sanitized)
        final_canonical = (
            finalized.get("json")
            if isinstance(finalized.get("json"), Mapping)
            else {}
        )
        if final_canonical:
            # Finalization legitimately appends deterministic manifest/navigation
            # metadata. Bind the persisted truth hash only after that last mutation so
            # publication and read authority describe the same canonical object.
            finalized["canonical_truth_sha256"] = canonical_sha256(
                final_canonical
            )
        return finalized
    finally:
        # Render-input cache entries retain the entire canonical tree and its localized
        # projection. Final-report execution is serialized, so those heavyweight objects
        # are attempt-scoped and can be released on both success and failure. The bounded
        # translation-string caches remain warm for later Spanish assessments.
        release_comprehensive_spanish_render_input_cache_v94()


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
    "_HUMAN_REVIEW_WORKSHEET_TITLE_CONTRACT",
    "_EXECUTIVE_SUMMARY_SEMANTIC_TRUTH",
    "_phase2_review_truth_node",
    "_phase2_review_truth_text",
    "_populate_premium_stage_summaries",
    "_rewrite_phase2_review_truth_pdf",
    "rebuild_client_artifacts",
]
