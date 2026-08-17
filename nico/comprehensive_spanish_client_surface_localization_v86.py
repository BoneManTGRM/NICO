from __future__ import annotations

import re
from typing import Any

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


def install_comprehensive_spanish_client_surface_localization_v86() -> dict[str, Any]:
    """Install the v85 terminal surface contract with corrected precedence/validation."""

    base = v85.install_comprehensive_spanish_client_surface_localization_v85()
    return {
        **base,
        "status": "installed",
        "version": VERSION,
        "specific_scanner_label_precedence": True,
        "wrapped_pdf_heading_validation": True,
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
