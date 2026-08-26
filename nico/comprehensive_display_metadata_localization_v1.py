from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive_display_metadata_localization.v1.1"
_MARKER = "__nico_display_metadata_localization_v1__"

# Renderer-owned labels only. User-supplied values remain byte-for-byte unchanged
# across locales and canonical scope identifiers are not touched.
_ES_METADATA_LABELS: tuple[tuple[str, str], ...] = (
    ("Client display name", "Nombre visible del cliente"),
    ("Project display name", "Nombre visible del proyecto"),
    ("Primary technical contact", "Contacto técnico principal"),
)


def install_display_metadata_localization_v1() -> dict[str, Any]:
    """Register new metadata labels on both active es-MX presentation paths.

    The isolated renderer installs its runtime cache before the final PDF presentation
    installer. The cached wrapper still delegates through the v98 current-report phrase
    registry, which is read dynamically, while direct canonical translation reads the
    v87 replacement tuple. Register the same three bounded labels in both authorities.

    Complete labels are inserted before generic replacements such as ``Project`` so a
    partial replacement cannot strand English words. No user value, canonical identifier,
    evidence value, score, finding, review state, or authorization state is translated.
    """

    from nico import comprehensive_current_report_truth_parity_v1 as current_truth
    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    blocked_sources = {source for source, _target in _ES_METADATA_LABELS}

    current = tuple(canonical._PRESENTATION_REPLACEMENTS)
    retained = tuple(
        pair for pair in current if str(pair[0]) not in blocked_sources
    )
    canonical._PRESENTATION_REPLACEMENTS = _ES_METADATA_LABELS + retained

    # v98 calls this mapping dynamically even after v94 has captured the wrapper, so
    # this registration is intentionally effective across the worker cache boundary.
    for source, target in _ES_METADATA_LABELS:
        current_truth._ES_PHRASES[source] = target

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
        "current_report_dynamic_registry_bound": all(
            current_truth._ES_PHRASES.get(source) == target
            for source, target in _ES_METADATA_LABELS
        ),
        "runtime_cache_order_safe": True,
        "canonical_truth_mutated": False,
        "user_values_translated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_display_metadata_localization_v1"]
