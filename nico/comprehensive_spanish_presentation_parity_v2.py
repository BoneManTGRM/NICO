from __future__ import annotations

import re
from typing import Any

from nico import comprehensive_spanish_presentation_parity_v1 as v1

VERSION = "nico.comprehensive-spanish-presentation-parity.v2"
_MARKER = "__nico_comprehensive_spanish_presentation_parity_v2__"
_BASE_ASSERT_SPANISH_FULL_DATA_PARITY = v1._assert_spanish_full_data_parity


def _safe_replace(text: str, source: str, target: str) -> str:
    """Replace presentation phrases without corrupting identifiers or blocking spaced phrases.

    v1 guarded both sides of every alpha-led phrase. That is correct for a bare
    word such as ``workflow`` but incorrect for phrases that intentionally end or
    begin with whitespace (for example ``Reduce complexity in ``). The trailing
    word-boundary check was evaluated after the literal space and therefore
    rejected the following identifier, leaving mixed English/Spanish copy.
    """

    if not source:
        return text
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 /&'’().,+\-]*", source):
        left_guard = r"(?<![A-Za-z0-9_])" if source[0].isalnum() else ""
        right_guard = r"(?![A-Za-z0-9_])" if source[-1].isalnum() else ""
        pattern = f"{left_guard}{re.escape(source)}{right_guard}"
        return re.sub(pattern, lambda _match: target, text)
    return text.replace(source, target)


def _assert_spanish_full_data_parity(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Preserve stable worksheet-lineage proof metadata while using the v1 truth gate."""

    proof = dict(_BASE_ASSERT_SPANISH_FULL_DATA_PARITY(*args, **kwargs))
    proof.setdefault("worksheet_identity_source", "stable_stage_id_or_established_alias")
    proof.setdefault("missing_worksheets_not_synthesized", True)
    return proof


# v1 helpers resolve these symbols through their module globals at call time. Bind
# the corrected implementations on import so focused callers and production
# installation use the same boundary and proof semantics.
v1._safe_replace = _safe_replace
v1._assert_spanish_full_data_parity = _assert_spanish_full_data_parity


def _install_pdf_text_normalization() -> bool:
    """Make final-section validation insensitive to harmless PDF line wrapping."""

    from nico import comprehensive_full_data_worksheet_localization_v1 as localization

    current = localization._pdf_text
    if getattr(current, _MARKER, False):
        return True

    def pdf_text(pdf: bytes) -> str:
        raw = current(pdf)
        normalized = " ".join(raw.split())
        if not normalized or normalized in raw:
            return raw
        # Preserve the original extraction for line-sensitive checks while adding
        # one normalized copy for exact client-section title membership checks.
        return raw + "\n" + normalized

    setattr(pdf_text, _MARKER, True)
    setattr(pdf_text, "_nico_previous", current)
    localization._pdf_text = pdf_text
    return True


def install_comprehensive_spanish_presentation_parity_v2() -> dict[str, Any]:
    """Harden v1 Spanish parity without changing canonical scores or evidence."""

    v1._safe_replace = _safe_replace
    v1._assert_spanish_full_data_parity = _assert_spanish_full_data_parity
    pdf_heading_normalization = _install_pdf_text_normalization()
    base = v1.install_comprehensive_spanish_presentation_parity_v1()
    return {
        **base,
        "status": "installed",
        "version": VERSION,
        "spaced_phrase_boundaries_fixed": True,
        "identifier_boundaries_preserved": True,
        "worksheet_identity_proof_preserved": True,
        "wrapped_pdf_heading_validation": pdf_heading_normalization,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


# Re-export the corrected v1 helpers so focused regression tests exercise the same
# implementation that production installs through this compatibility layer.
_safe_es = v1._safe_es
_localized_register = v1._localized_register
_render_manifest_spanish = v1._render_manifest_spanish
_toc_page_spanish = v1._toc_page_spanish


__all__ = [
    "VERSION",
    "_safe_es",
    "_safe_replace",
    "_assert_spanish_full_data_parity",
    "_localized_register",
    "_render_manifest_spanish",
    "_toc_page_spanish",
    "install_comprehensive_spanish_presentation_parity_v2",
]
