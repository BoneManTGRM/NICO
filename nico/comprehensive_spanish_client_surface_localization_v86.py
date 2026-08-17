from __future__ import annotations

import re
from typing import Any

from nico import client_pdf_status_sanitizer_v1 as sanitizer
from nico import comprehensive_client_ready_projection_v1 as projection
from nico import comprehensive_client_review_companion_v5 as review_v5
from nico import comprehensive_client_review_companion_v7 as review_v7
from nico import comprehensive_spanish_client_surface_localization_v85 as v85

VERSION = "nico.comprehensive-spanish-client-surface-localization.v86"
_MARKER = "__nico_comprehensive_spanish_client_surface_localization_v86__"

_BASE_LOCALIZE_PRESENTATION_TEXT = v85._localize_presentation_text
_BASE_PDF_TEXT = v85._pdf_text


def _localize_presentation_text(value: str) -> str:
    """Apply specific structural translations before generic phrase replacements."""

    output = str(value or "")
    # v85 translated the generic prefix "Confirmed material" before its more
    # specific scanner-count regex ran. That left mixed copy such as
    # "Material confirmado scanner findings: 3". Translate the structural label
    # first, then let the established bounded presentation translator handle the
    # remaining NICO-owned copy.
    output = re.sub(
        r"\bConfirmed material scanner findings:\s*(\d+)",
        r"Hallazgos materiales confirmados por analizadores: \1",
        output,
    )
    return _BASE_LOCALIZE_PRESENTATION_TEXT(output)


def _pdf_text(pdf: bytes) -> str:
    """Preserve raw extraction and add a whitespace-normalized validation view."""

    raw = _BASE_PDF_TEXT(pdf)
    normalized = " ".join(raw.split())
    if not normalized or normalized in raw:
        return raw
    # ReportLab may wrap long Spanish section headings across text operators.
    # Presence validation must not reject a correct artifact only because the PDF
    # extractor inserts a newline at that visual wrap boundary.
    return raw + "\n" + normalized


# v85 closures resolve these helpers through module globals at call time. Patch the
# globals once so every final Markdown/PDF producer installed by v85 consumes the
# corrected implementation without creating a second language authority.
v85._localize_presentation_text = _localize_presentation_text
v85._pdf_text = _pdf_text

# Re-export the production helpers for focused tests and compatibility callers.
ES_BOUNDARY = v85.ES_BOUNDARY
EN_BOUNDARY = v85.EN_BOUNDARY
SPANISH_MANIFEST_TITLE = v85.SPANISH_MANIFEST_TITLE
SPANISH_APPROVAL_TITLE = v85.SPANISH_APPROVAL_TITLE
_english_status_only = v85._english_status_only
_render_spanish_manifest = v85._render_spanish_manifest
_spanish_markdown_manifest = v85._spanish_markdown_manifest
_transform_pdf_text = v85._transform_pdf_text
localize_spanish_markdown = v85.localize_spanish_markdown


def _provider_bindings() -> tuple[tuple[Any, str, Any], ...]:
    """Capture provider aliases before the terminal v85 consumer layer is installed.

    The final publication path consumes the aliases on client_report_completion_v2.
    Rebinding both those terminal consumer aliases and the provider aliases underneath
    them can turn an earlier compatibility wrapper into a cycle: terminal wrapper ->
    older delegating wrapper -> provider alias -> terminal wrapper. Preserve the exact
    provider functions that exist immediately before v85 and restore them afterwards.
    """

    return (
        (review_v5, "merge_substantive_review_markdown", review_v5.merge_substantive_review_markdown),
        (projection, "compact_client_markdown", projection.compact_client_markdown),
        (
            projection,
            "render_compact_finding_register_pdf",
            projection.render_compact_finding_register_pdf,
        ),
        (
            projection,
            "render_evidence_review_gate_pdf",
            projection.render_evidence_review_gate_pdf,
        ),
        (
            review_v7,
            "render_paired_substantive_review_pdf",
            review_v7.render_paired_substantive_review_pdf,
        ),
        (sanitizer, "sanitize_client_pdf_status", sanitizer.sanitize_client_pdf_status),
    )


def _restore_provider_bindings(bindings: tuple[tuple[Any, str, Any], ...]) -> None:
    for module, name, target in bindings:
        setattr(module, name, target)


def install_comprehensive_spanish_client_surface_localization_v86() -> dict[str, Any]:
    """Install the v85 terminal surface contract without recursive provider rebinding."""

    provider_bindings = _provider_bindings()
    try:
        base = v85.install_comprehensive_spanish_client_surface_localization_v85()
    finally:
        # v85 intentionally localizes the terminal completion aliases, but it also
        # mirrored several wrappers back into their provider modules. In the stacked
        # production compatibility graph an older wrapper may delegate dynamically to
        # one of those provider aliases. Mirroring the terminal wrapper back into that
        # provider closes a recursive loop and surfaced in production as
        # RecursionError: maximum recursion depth exceeded. Keep terminal localization
        # authoritative while leaving provider ownership with the pre-v85 layer.
        _restore_provider_bindings(provider_bindings)

    return {
        **base,
        "status": "installed",
        "version": VERSION,
        "specific_scanner_label_precedence": True,
        "wrapped_pdf_heading_validation": True,
        "provider_alias_cycle_prevention": True,
        "terminal_consumer_aliases_only": True,
        "canonical_language_resolver_reused": True,
        "code_and_exact_source_literals_preserved": True,
        "spanish_full_data_truth_gate_updated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "ES_BOUNDARY",
    "EN_BOUNDARY",
    "SPANISH_MANIFEST_TITLE",
    "SPANISH_APPROVAL_TITLE",
    "_english_status_only",
    "_localize_presentation_text",
    "_pdf_text",
    "_render_spanish_manifest",
    "_spanish_markdown_manifest",
    "_transform_pdf_text",
    "localize_spanish_markdown",
    "install_comprehensive_spanish_client_surface_localization_v86",
]
