from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive_display_metadata_localization.v1.2"
_MARKER = "__nico_display_metadata_localization_v1__"

# Renderer-owned labels only. User-supplied values remain byte-for-byte unchanged
# across locales and canonical scope identifiers are not touched.
_ES_METADATA_LABELS: tuple[tuple[str, str], ...] = (
    ("Client display name", "Nombre visible del cliente"),
    ("Project display name", "Nombre visible del proyecto"),
    ("Primary technical contact", "Contacto técnico principal"),
)


def install_display_metadata_localization_v1() -> dict[str, Any]:
    """Register the three new labels on the canonical es-MX translator only.

    The canonical v87 translator reads its replacement tuple dynamically even when the
    isolated renderer has already cached the translation function, so this bounded
    registration is cache-order safe. Do not append these labels to the v98/current-report
    dynamic phrase registry: that wrapper is installed globally and a late mutation can
    alter a later English render in the same process.

    Complete labels are prepended before generic replacements such as ``Project`` so a
    partial replacement cannot strand English words. No user value, canonical identifier,
    evidence value, score, finding, review state, or authorization state is translated.
    """

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    blocked_sources = {source for source, _target in _ES_METADATA_LABELS}
    current = tuple(canonical._PRESENTATION_REPLACEMENTS)
    retained = tuple(
        pair for pair in current if str(pair[0]) not in blocked_sources
    )
    canonical._PRESENTATION_REPLACEMENTS = _ES_METADATA_LABELS + retained

    already_installed = bool(getattr(canonical, _MARKER, False))
    setattr(canonical, _MARKER, True)
    return {
        "artifact_schema": VERSION,
        "status": "already_installed" if already_installed else "installed",
        "labels": len(_ES_METADATA_LABELS),
        "canonical_replacement_registry_bound": all(
            pair in canonical._PRESENTATION_REPLACEMENTS
            for pair in _ES_METADATA_LABELS
        ),
        "late_dynamic_phrase_registry_untouched": True,
        "runtime_cache_order_safe": True,
        "english_render_state_isolation_preserved": True,
        "canonical_truth_mutated": False,
        "user_values_translated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_display_metadata_localization_v1"]
