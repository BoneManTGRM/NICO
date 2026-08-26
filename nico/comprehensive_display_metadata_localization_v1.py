from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive_display_metadata_localization.v1"
_MARKER = "__nico_display_metadata_localization_v1__"

# These are renderer-owned labels only. User-supplied values remain byte-for-byte
# unchanged across locales and canonical scope identifiers are not touched.
_ES_METADATA_LABELS: tuple[tuple[str, str], ...] = (
    ("Client display name", "Nombre visible del cliente"),
    ("Project display name", "Nombre visible del proyecto"),
    ("Primary technical contact", "Contacto técnico principal"),
)


def install_display_metadata_localization_v1() -> dict[str, Any]:
    """Teach the existing fail-closed es-MX renderer the new metadata labels.

    Prepend the complete labels before generic replacements such as ``Project`` so a
    partial replacement cannot strand English words in the final Spanish artifact.
    Canonical JSON values and user-supplied metadata are not translated.
    """

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    current = tuple(canonical._PRESENTATION_REPLACEMENTS)
    if getattr(canonical, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "labels": len(_ES_METADATA_LABELS),
            "canonical_truth_mutated": False,
            "user_values_translated": False,
        }

    blocked_sources = {source for source, _target in _ES_METADATA_LABELS}
    retained = tuple(
        pair for pair in current if str(pair[0]) not in blocked_sources
    )
    canonical._PRESENTATION_REPLACEMENTS = _ES_METADATA_LABELS + retained
    setattr(canonical, _MARKER, True)
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "labels": len(_ES_METADATA_LABELS),
        "canonical_truth_mutated": False,
        "user_values_translated": False,
    }


__all__ = ["VERSION", "install_display_metadata_localization_v1"]
