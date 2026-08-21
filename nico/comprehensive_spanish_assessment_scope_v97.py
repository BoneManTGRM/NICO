from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive-spanish-assessment-scope.v97"

PRODUCTION_ASSESSMENT_SCOPE = (
    "Review the repository and produce a prioritized remediation roadmap with "
    "evidence-backed findings."
)
PRODUCTION_ASSESSMENT_SCOPE_ES = (
    "Revisar el repositorio y producir una hoja de ruta de remediación priorizada "
    "con hallazgos respaldados por evidencia."
)

_ASSESSMENT_SCOPE_TRANSLATIONS: dict[str, str] = {
    PRODUCTION_ASSESSMENT_SCOPE: PRODUCTION_ASSESSMENT_SCOPE_ES,
    PRODUCTION_ASSESSMENT_SCOPE.removesuffix("."): (
        PRODUCTION_ASSESSMENT_SCOPE_ES.removesuffix(".")
    ),
}


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "version": VERSION,
        "bound": False,
        "reason": reason,
        "presentation_only": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_spanish_assessment_scope_v97() -> dict[str, Any]:
    """Register the exact production assessment-scope presentation contract.

    The Comprehensive scoring stage retains a canonical ``assessment_scope`` sentence
    that is report-owned presentation prose. The English system may publish that exact
    contract, but an es-MX run must translate it before final-report publication. Add
    only the approved exact contract and its terminal-period-normalized equivalent to
    v88's bounded targeted vocabulary. Unknown scope prose continues through the
    existing fail-closed canonical translator.
    """

    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    v88.install_comprehensive_spanish_exit_criteria_v88()

    exact = getattr(v88, "_TARGETED_PRESENTATION_TRANSLATIONS", None)
    folded = getattr(v88, "_TARGETED_PRESENTATION_TRANSLATIONS_CASEFOLD", None)
    if not isinstance(exact, dict) or not isinstance(folded, dict):
        return _blocked("spanish_targeted_translation_registry_unavailable")

    exact.update(_ASSESSMENT_SCOPE_TRANSLATIONS)
    folded.update(
        {
            source.casefold(): target
            for source, target in _ASSESSMENT_SCOPE_TRANSLATIONS.items()
        }
    )

    v88_state = v88.install_comprehensive_spanish_exit_criteria_v88()

    translated = v88._translate_targeted_presentation_literal(
        PRODUCTION_ASSESSMENT_SCOPE
    )
    normalized_translated = v88._translate_targeted_presentation_literal(
        PRODUCTION_ASSESSMENT_SCOPE.removesuffix(".")
    )

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    canonical_translation = canonical._translate_presentation_field(
        PRODUCTION_ASSESSMENT_SCOPE,
        "assessment_scope",
    )
    bound = bool(
        v88_state.get("bound") is True
        and translated == PRODUCTION_ASSESSMENT_SCOPE_ES
        and normalized_translated
        == PRODUCTION_ASSESSMENT_SCOPE_ES.removesuffix(".")
        and canonical_translation == PRODUCTION_ASSESSMENT_SCOPE_ES
    )

    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "production_assessment_scope_translation_supported": bound,
        "terminal_period_normalization_supported": bound,
        "approved_exact_contracts_only": True,
        "unknown_assessment_scope_prose_still_fail_closed": True,
        "presentation_only": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "english_report_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "PRODUCTION_ASSESSMENT_SCOPE",
    "PRODUCTION_ASSESSMENT_SCOPE_ES",
    "VERSION",
    "install_comprehensive_spanish_assessment_scope_v97",
]
