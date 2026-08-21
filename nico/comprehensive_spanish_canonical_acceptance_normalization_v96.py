from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-canonical-acceptance-normalization.v96"
_TARGETED_MARKER = "__nico_spanish_acceptance_targeted_v96__"
_GENERATED_MARKER = "__nico_spanish_acceptance_generated_v96__"

_ORIGINAL_TARGETED_TRANSLATOR: Callable[[Any], str | None] | None = None
_ORIGINAL_GENERATED_COMPLEXITY_TRANSLATOR: Callable[[Any], str | None] | None = None


def _with_terminal_period(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.endswith("."):
        return None
    return text + "."


def install_comprehensive_spanish_canonical_acceptance_normalization_v96() -> dict[str, Any]:
    """Accept punctuation-normalized variants of already-approved Spanish contracts.

    Canonical finding deduplication deliberately ignores terminal punctuation when it
    computes acceptance-criterion identity. When equivalent findings are merged, the
    shorter representation can therefore win and remove a final period. The Spanish
    renderer previously recognized only the punctuated generator contract, so a valid
    canonical criterion could become an untranslated-English publication blocker.

    This layer does not translate arbitrary prose. It retries only the exact same
    approved v88 targeted/generated contract with one terminal period restored. If the
    underlying v88 contract still does not recognize the value, the normal fail-closed
    Spanish field translator remains authoritative.
    """

    global _ORIGINAL_TARGETED_TRANSLATOR
    global _ORIGINAL_GENERATED_COMPLEXITY_TRANSLATOR

    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    # Establish v88's immutable lower-level delegates before extending its helper
    # contracts. Re-installation is intentional and idempotent.
    v88.install_comprehensive_spanish_exit_criteria_v88()

    current_targeted = v88._translate_targeted_presentation_literal
    if not getattr(current_targeted, _TARGETED_MARKER, False):
        if _ORIGINAL_TARGETED_TRANSLATOR is None:
            _ORIGINAL_TARGETED_TRANSLATOR = current_targeted
        base_targeted = _ORIGINAL_TARGETED_TRANSLATOR
        if base_targeted is None:
            raise RuntimeError("Spanish canonical acceptance normalization has no targeted base")

        @wraps(base_targeted)
        def targeted(value: Any) -> str | None:
            translated = base_targeted(value)
            if translated is not None:
                return translated
            punctuated = _with_terminal_period(value)
            if punctuated is None:
                return None
            return base_targeted(punctuated)

        setattr(targeted, _TARGETED_MARKER, True)
        setattr(targeted, "_nico_previous", base_targeted)
        v88._translate_targeted_presentation_literal = targeted

    current_generated = v88._translate_generated_complexity_contract
    if not getattr(current_generated, _GENERATED_MARKER, False):
        if _ORIGINAL_GENERATED_COMPLEXITY_TRANSLATOR is None:
            _ORIGINAL_GENERATED_COMPLEXITY_TRANSLATOR = current_generated
        base_generated = _ORIGINAL_GENERATED_COMPLEXITY_TRANSLATOR
        if base_generated is None:
            raise RuntimeError("Spanish canonical acceptance normalization has no generated base")

        @wraps(base_generated)
        def generated(value: Any) -> str | None:
            translated = base_generated(value)
            if translated is not None:
                return translated
            punctuated = _with_terminal_period(value)
            if punctuated is None:
                return None
            return base_generated(punctuated)

        setattr(generated, _GENERATED_MARKER, True)
        setattr(generated, "_nico_previous", base_generated)
        v88._translate_generated_complexity_contract = generated

    # Reassert the v88 field/presentation aliases after helper replacement. Those
    # bound functions resolve these helper globals at call time, including inside the
    # isolated final-report worker and the later v93 publication preflight.
    v88_state = v88.install_comprehensive_spanish_exit_criteria_v88()

    production_acceptance = (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323"
    )
    targeted_acceptance = "Targeted characterization tests pass on the remediation commit"
    production_translation = v88._translate_generated_complexity_contract(production_acceptance)
    targeted_translation = v88._translate_targeted_presentation_literal(targeted_acceptance)
    bound = bool(
        getattr(v88._translate_targeted_presentation_literal, _TARGETED_MARKER, False)
        and getattr(v88._translate_generated_complexity_contract, _GENERATED_MARKER, False)
        and isinstance(production_translation, str)
        and production_translation.startswith("La nueva ejecución sobre el SHA exacto")
        and isinstance(targeted_translation, str)
        and targeted_translation.startswith("Las pruebas de caracterización dirigidas")
        and v88_state.get("bound") is True
    )

    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "canonical_acceptance_terminal_period_loss_supported": True,
        "production_complexity_acceptance_without_period_supported": bool(production_translation),
        "targeted_acceptance_without_period_supported": bool(targeted_translation),
        "approved_contracts_only": True,
        "unknown_presentation_prose_still_fail_closed": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_canonical_acceptance_normalization_v96",
]
