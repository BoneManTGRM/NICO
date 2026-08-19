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

# Some report fields, including rollback guidance, are standalone presentation
# literals rather than exit-criteria prose. Keep production-observed literals in a
# separate exact fast path so they do not expand the global replacement registry
# or weaken the canonical renderer's unknown-English fail-closed behavior.
_TARGETED_PRESENTATION_TRANSLATIONS: dict[str, str] = {
    (
        "Revert the isolated remediation change if targeted or full verification fails; "
        "retain the failed evidence and keep client delivery blocked."
    ): (
        "Revierta el cambio aislado de remediación si falla la verificación dirigida o "
        "completa; conserve la evidencia del fallo y mantenga bloqueada la entrega al cliente."
    ),
}
_TARGETED_PRESENTATION_TRANSLATIONS_CASEFOLD = {
    source.casefold(): target
    for source, target in _TARGETED_PRESENTATION_TRANSLATIONS.items()
}

# The v85 terminal client-surface localizer calls v87._translate_presentation
# directly. v87 intentionally splits multiline values before applying full-match
# structured contracts, so a renderer-inserted soft line wrap can strand an otherwise
# valid structured sentence. Repair only production-observed structured spans and
# require v87's authoritative full-match translator to recognize the normalized text.
_STRUCTURED_SOFT_WRAP_SPANS: tuple[tuple[str, str], ...] = (
    (
        "Technical maturity remains based on exact-commit technical controls.",
        "readiness scores.",
    ),
)
_MAX_STRUCTURED_SOFT_WRAP_CHARS = 2400

_EXIT_CRITERIA_MARKER = next(iter(_EXIT_CRITERIA_TRANSLATIONS))
_ORIGINAL_CANONICAL_TRANSLATE_FIELD: Callable[[str, str], str] | None = None
_ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION: Callable[[Any], str] | None = None
_ORIGINAL_PRESENTATION_SAFE_ES: Callable[[Any], str] | None = None
_ORIGINAL_NATIVE_BUILD_REPORT: Callable[[dict[str, Any], bool], dict[str, Any]] | None = None


def _translate_targeted_presentation_literal(value: Any) -> str | None:
    text = str(value or "").strip()
    translated = _TARGETED_PRESENTATION_TRANSLATIONS.get(text)
    if translated is not None:
        return translated
    return _TARGETED_PRESENTATION_TRANSLATIONS_CASEFOLD.get(text.casefold())


def _translate_known_exit_criteria(value: Any) -> str:
    text = str(value or "")
    if _EXIT_CRITERIA_MARKER not in text:
        return text
    for source, target in _EXIT_CRITERIA_TRANSLATIONS.items():
        text = text.replace(source, target)
    return text


def _normalize_known_structured_presentation(value: Any) -> tuple[str, str] | None:
    """Recognize known v87 presentation contracts across soft whitespace drift.

    Production report values can acquire line wrapping or repeated whitespace before
    the Spanish compatibility layer sees them. v87 intentionally uses full-match
    structured contracts and fails closed for unknown English. Normalize whitespace
    only when the normalized value is already recognized by that authoritative
    structured translator. Unknown or changed prose is delegated unchanged so the
    existing fail-closed guard remains authoritative.
    """

    text = str(value or "")
    normalized = " ".join(text.split())
    if not normalized or normalized == text.strip():
        return None

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    try:
        translated = canonical._structured_presentation_es(normalized)
    except ValueError:
        return None
    if translated is None:
        return None
    return normalized, translated


def _repair_known_structured_spans(value: Any) -> str:
    """Normalize recognized structured contracts before v87 translates them.

    The terminal v85 localizer can pass an entire Markdown or review block to v87's
    direct presentation translator. Normalize only a bounded span whose start and end
    markers are known, and only when v87 independently recognizes the normalized
    English contract. The normalized English is then delegated to the original v87
    translator so its authoritative translation and fail-closed checks remain active.
    If the contract changes, leave it untouched so v87 still fails closed.
    """

    text = str(value or "")

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    for start_marker, end_marker in _STRUCTURED_SOFT_WRAP_SPANS:
        search_from = 0
        while True:
            start = text.find(start_marker, search_from)
            if start < 0:
                break
            end_start = text.find(end_marker, start + len(start_marker))
            if end_start < 0:
                break
            end = end_start + len(end_marker)
            if end - start > _MAX_STRUCTURED_SOFT_WRAP_CHARS:
                search_from = start + len(start_marker)
                continue

            candidate = text[start:end]
            normalized = " ".join(candidate.split())
            try:
                recognized = canonical._structured_presentation_es(normalized)
            except ValueError:
                recognized = None
            if recognized is None:
                search_from = start + len(start_marker)
                continue

            text = text[:start] + normalized + text[end:]
            search_from = start + len(normalized)
    return text


def _translate_presentation_v88(value: Any) -> str:
    original = _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 direct translator is not installed")
    return original(_repair_known_structured_spans(value))


def _translate_canonical_field_v88(value: str, key: str) -> str:
    original = _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 canonical translator is not installed")

    targeted = _translate_targeted_presentation_literal(value)
    if str(key) == "rollback" and targeted is not None:
        # Translate only the exact production-observed rollback contract. The existing
        # canonical translator still validates the resulting presentation value.
        return original(targeted, key)

    if str(key) == "exit_criteria" and _EXIT_CRITERIA_MARKER in str(value or ""):
        # Delegate the partially localized value to the existing fail-closed gate.
        # Any unknown English tail still fails instead of being silently approved.
        return original(_translate_known_exit_criteria(value), key)

    structured = _normalize_known_structured_presentation(value)
    if structured is not None:
        normalized, _ = structured
        # Feed only the already-recognized normalized contract back through the
        # authoritative field translator so all existing validation remains active.
        return original(normalized, key)

    return original(value, key)


def _presentation_safe_es_v88(value: Any) -> str:
    original = _ORIGINAL_PRESENTATION_SAFE_ES
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 presentation translator is not installed")

    targeted = _translate_targeted_presentation_literal(value)
    if targeted is not None:
        return original(targeted)

    text = str(value or "")
    if _EXIT_CRITERIA_MARKER in text:
        return original(_translate_known_exit_criteria(text))

    structured = _normalize_known_structured_presentation(value)
    if structured is not None:
        _, translated = structured
        # The canonical v87 structured translator already produced the approved
        # Spanish presentation value. Pass that through the existing surface guard
        # rather than reintroducing the soft-wrapped English source.
        return original(translated)

    return original(value)


def _bind_translation_surfaces() -> tuple[Any, Any]:
    """Bind the targeted translators to the live modules without touching global loops."""

    global _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    global _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    global _ORIGINAL_PRESENTATION_SAFE_ES

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    if canonical._translate_presentation is not _translate_presentation_v88:
        _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION = canonical._translate_presentation
        canonical._translate_presentation = _translate_presentation_v88

    if canonical._translate_presentation_field is not _translate_canonical_field_v88:
        _ORIGINAL_CANONICAL_TRANSLATE_FIELD = canonical._translate_presentation_field
        canonical._translate_presentation_field = _translate_canonical_field_v88

    if presentation._safe_es is not _presentation_safe_es_v88:
        _ORIGINAL_PRESENTATION_SAFE_ES = presentation._safe_es
        presentation._safe_es = _presentation_safe_es_v88

    return canonical, presentation


def _spanish_report_requested(context: Any) -> bool:
    if not isinstance(context, dict):
        return False
    value = str(
        context.get("report_language")
        or context.get("requested_report_language")
        or context.get("locale")
        or ""
    ).strip().casefold()
    return value.startswith("es")


def _native_build_report_v88(context: dict[str, Any], final: bool) -> dict[str, Any]:
    """Reassert terminal report guards immediately before native report rendering.

    Production Comprehensive decision-report execution is detached from the browser
    request and may begin after late compatibility installers have rebound renderer
    aliases. The provider function captured by the runtime still resolves its private
    ``_build_report`` global at call time, so this boundary is the stable place to
    restore the exact Spanish translation contract before either the decision report
    or final report is rendered. The CI/CD PDF control-glyph repair is also installed
    here, rather than at application import time, so offline English golden renderers
    remain byte-for-byte unchanged while native production reports are control-safe.
    """

    original = _ORIGINAL_NATIVE_BUILD_REPORT
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 report boundary is not installed")

    from nico.comprehensive_ci_pdf_control_safety_v89 import (
        install_comprehensive_ci_pdf_control_safety_v89,
    )

    ci_pdf_control_safety = install_comprehensive_ci_pdf_control_safety_v89()
    if (
        ci_pdf_control_safety.get("bound") is not True
        or ci_pdf_control_safety.get("del_control_glyph_sanitized") is not True
    ):
        raise RuntimeError("CI/CD PDF control-safety boundary could not be installed")

    if _spanish_report_requested(context):
        _bind_translation_surfaces()
    return original(context, final)


def install_comprehensive_spanish_exit_criteria_v88() -> dict[str, Any]:
    """Bind the production remediation exit-criteria family into Spanish surfaces."""

    global _ORIGINAL_NATIVE_BUILD_REPORT

    canonical, presentation = _bind_translation_surfaces()

    # Decision-report generation in the hosted Postgres runtime runs behind a detached
    # stage lease. Keep a call-time guard on the provider's shared report boundary so a
    # later compatibility installer cannot silently strand an es-MX worker with stale
    # translator aliases. This does not add translation phrases to the hot global loops
    # and does not change any English, evidence, scoring, or delivery semantics.
    from nico import comprehensive_native_providers as providers

    if providers._build_report is not _native_build_report_v88:
        _ORIGINAL_NATIVE_BUILD_REPORT = providers._build_report
        providers._build_report = _native_build_report_v88

    # Do not install the PDF producer patch at application/import time. It is deferred
    # to the native report execution boundary so legacy/offline English golden renderers
    # remain byte-identical while production Comprehensive reports receive the repair.
    return {
        "status": "installed",
        "version": VERSION,
        "bound": (
            canonical._translate_presentation is _translate_presentation_v88
            and canonical._translate_presentation_field is _translate_canonical_field_v88
            and presentation._safe_es is _presentation_safe_es_v88
        ),
        "direct_canonical_presentation_bound": (
            canonical._translate_presentation is _translate_presentation_v88
        ),
        "terminal_client_surface_soft_wrap_repair": True,
        "report_runtime_boundary_bound": (
            providers._build_report is _native_build_report_v88
        ),
        "detached_decision_report_reassertion": True,
        "targeted_fast_path": True,
        "targeted_rollback_translation": True,
        "structured_soft_whitespace_repair": True,
        "ci_pdf_control_safety_deferred_to_native_report_boundary": True,
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
