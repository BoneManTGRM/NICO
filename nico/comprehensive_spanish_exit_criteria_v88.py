from __future__ import annotations

from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-exit-criteria.v88"

# Free-form remediation criteria can enter the canonical report through retained
# finding acceptance criteria. Keep the known production contract here as a
# presentation-only fast path so canonical evidence and English output remain
# byte-for-byte unchanged without expanding the global renderer replacement loop.
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

_EXIT_CRITERIA_MARKER = next(iter(_EXIT_CRITERIA_TRANSLATIONS))
_ORIGINAL_CANONICAL_TRANSLATE_FIELD: Callable[[str, str], str] | None = None
_ORIGINAL_PRESENTATION_SAFE_ES: Callable[[Any], str] | None = None


def _translate_known_exit_criteria(value: Any) -> str:
    text = str(value or "")
    if _EXIT_CRITERIA_MARKER not in text:
        return text
    for source, target in _EXIT_CRITERIA_TRANSLATIONS.items():
        text = text.replace(source, target)
    return text


def _translate_canonical_field_v88(value: str, key: str) -> str:
    original = _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 canonical translator is not installed")

    if str(key) == "exit_criteria" and _EXIT_CRITERIA_MARKER in str(value or ""):
        # Delegate the partially localized value to the existing fail-closed gate.
        # Any unknown English tail still fails instead of being silently approved.
        return original(_translate_known_exit_criteria(value), key)
    return original(value, key)


def _presentation_safe_es_v88(value: Any) -> str:
    original = _ORIGINAL_PRESENTATION_SAFE_ES
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 presentation translator is not installed")

    text = str(value or "")
    if _EXIT_CRITERIA_MARKER in text:
        return original(_translate_known_exit_criteria(text))
    return original(value)


def install_comprehensive_spanish_exit_criteria_v88() -> dict[str, Any]:
    """Bind the production remediation exit-criteria family into Spanish surfaces."""

    global _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    global _ORIGINAL_PRESENTATION_SAFE_ES

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    # Do not append these phrases to either global replacement registry. Those
    # registries are sorted and scanned for every presentation value and this
    # report path is performance-sensitive. Intercept only the observed
    # exit-criteria family, then hand control back to the existing fail-closed
    # translators for every remaining localization and validation rule.
    if canonical._translate_presentation_field is not _translate_canonical_field_v88:
        _ORIGINAL_CANONICAL_TRANSLATE_FIELD = canonical._translate_presentation_field
        canonical._translate_presentation_field = _translate_canonical_field_v88

    if presentation._safe_es is not _presentation_safe_es_v88:
        _ORIGINAL_PRESENTATION_SAFE_ES = presentation._safe_es
        presentation._safe_es = _presentation_safe_es_v88

    return {
        "status": "installed",
        "version": VERSION,
        "bound": (
            canonical._translate_presentation_field is _translate_canonical_field_v88
            and presentation._safe_es is _presentation_safe_es_v88
        ),
        "targeted_fast_path": True,
        "global_replacement_registry_unchanged": True,
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
