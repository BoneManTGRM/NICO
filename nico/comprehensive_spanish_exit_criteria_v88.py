from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive-spanish-exit-criteria.v88"

# Free-form remediation criteria can enter the canonical report through retained
# finding acceptance criteria. Keep the known production contract here as
# presentation-only translations so canonical evidence and English output remain
# byte-for-byte unchanged.
_EXIT_CRITERIA_TRANSLATIONS: dict[str, str] = {
    "All listed verification requirements pass on the exact remediation commit": (
        "Todos los requisitos de verificación enumerados se cumplen en el commit "
        "exacto de remediación"
    ),
    "the exact-SHA rerun no longer reports the condition as unresolved material risk": (
        "la nueva ejecución sobre el SHA exacto ya no informa la condición como un "
        "riesgo material sin resolver"
    ),
    "and no new material regression is introduced": (
        "y no se introduce ninguna nueva regresión material"
    ),
    "and no new material regressions are introduced": (
        "y no se introducen nuevas regresiones materiales"
    ),
    "and no new material regression is observed": (
        "y no se observa ninguna nueva regresión material"
    ),
    "and no new material regressions are observed": (
        "y no se observan nuevas regresiones materiales"
    ),
}


def install_comprehensive_spanish_exit_criteria_v88() -> dict[str, Any]:
    """Bind the production remediation exit-criteria family into Spanish surfaces."""

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    # Detached finding-register surfaces use the shared phrase map dynamically.
    presentation._ES_PHRASES.update(_EXIT_CRITERIA_TRANSLATIONS)

    # The canonical renderer snapshots that phrase map into a tuple at import time,
    # so extend its live replacement contract explicitly as well. Translation is
    # presentation-only; protected evidence fields and English output are untouched.
    existing_sources = {
        source for source, _target in canonical._PRESENTATION_REPLACEMENTS
    }
    additions = tuple(
        (source, target)
        for source, target in _EXIT_CRITERIA_TRANSLATIONS.items()
        if source not in existing_sources
    )
    if additions:
        canonical._PRESENTATION_REPLACEMENTS = (
            *canonical._PRESENTATION_REPLACEMENTS,
            *additions,
        )

    bound_sources = {
        source for source, _target in canonical._PRESENTATION_REPLACEMENTS
    }
    return {
        "status": "installed",
        "version": VERSION,
        "bound": all(
            source in bound_sources and presentation._ES_PHRASES.get(source) == target
            for source, target in _EXIT_CRITERIA_TRANSLATIONS.items()
        ),
        "presentation_only": True,
        "english_path_unchanged": True,
        "protected_evidence_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_exit_criteria_v88",
]
