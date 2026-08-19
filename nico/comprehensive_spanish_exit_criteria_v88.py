from __future__ import annotations

import re
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

# Standalone report fields and deterministic finding-generator contracts use exact
# presentation literals rather than one concatenated exit-criteria paragraph. Keep
# the approved production vocabulary here so all report surfaces share one bounded
# contract. Unknown prose still delegates to the canonical fail-closed translator.
_TARGETED_PRESENTATION_TRANSLATIONS: dict[str, str] = {
    (
        "Revert the isolated remediation change if targeted or full verification fails; "
        "retain the failed evidence and keep client delivery blocked."
    ): (
        "Revierta el cambio aislado de remediación si falla la verificación dirigida o "
        "completa; conserve la evidencia del fallo y mantenga bloqueada la entrega al cliente."
    ),
    "Targeted characterization tests pass on the remediation commit.": (
        "Las pruebas de caracterización dirigidas se superan en el commit de remediación."
    ),
    "The repository's complete required-check suite passes on the remediation commit.": (
        "El conjunto completo de verificaciones requeridas del repositorio se supera "
        "en el commit de remediación."
    ),
    "No new material regression or cross-format report-truth mismatch is introduced.": (
        "No se introduce ninguna nueva regresión material ni discrepancia de coherencia "
        "del informe entre formatos."
    ),
    "All verification requirements pass on the exact remediation commit.": (
        "Todos los requisitos de verificación se cumplen en el commit exacto de remediación."
    ),
    "The exact-SHA rerun no longer reports the condition as unresolved material risk.": (
        "La nueva ejecución sobre el SHA exacto ya no informa la condición como un "
        "riesgo material sin resolver."
    ),
    "No new material regression is introduced.": (
        "No se introduce ninguna nueva regresión material."
    ),
    "Higher regression probability, slower review, and growing maintenance cost.": (
        "Mayor probabilidad de regresión, revisiones más lentas y costos de mantenimiento "
        "crecientes."
    ),
    "Requires exact-source human review after automated remediation proof.": (
        "Requiere revisión humana de la fuente exacta después de la prueba automatizada "
        "de remediación."
    ),
}
_TARGETED_PRESENTATION_TRANSLATIONS_CASEFOLD = {
    source.casefold(): target
    for source, target in _TARGETED_PRESENTATION_TRANSLATIONS.items()
}

# The restored decision-content generator emits dynamic complexity findings. Their
# machine anchors (thresholds, paths, lines, symbols, and scanner method tokens) vary
# per repository, so enumerating complete English strings guarantees another
# production miss. Translate only anchored, full-match generator contracts and
# preserve every captured machine token byte-for-byte. Any grammar drift falls through
# to the existing fail-closed renderer instead of silently publishing mixed-language
# prose.
_COMPLEXITY_ACCEPTANCE_RE = re.compile(
    r"^The exact-SHA rerun no longer reports cyclomatic complexity above "
    r"(?P<threshold>\d+) at (?P<location>[A-Za-z0-9_.\-/]+:\d+)\.$"
)
_COMPLEXITY_TITLE_RE = re.compile(
    r"^Reduce complexity in (?P<name>[^\r\n]+)$"
)
_COMPLEXITY_INTERPRETATION_RE = re.compile(
    r"^Concentrated branching in `(?P<name>[^`\r\n]+)`\.$"
)
_COMPLEXITY_FACT_RE = re.compile(
    r"^cyclomatic_complexity=(?P<complexity>\d+); method=(?P<method>[^;\r\n]+); "
    r"source=retained exact-SHA architecture evidence$"
)
_COMPLEXITY_EVIDENCE_RE = re.compile(
    r"^cyclomatic_complexity=(?P<complexity>\d+); method=(?P<method>[^;\r\n]+); "
    r"exact_commit_match=(?P<exact>True|False)$"
)
_COMPLEXITY_REPORT_RECOMMENDATION_RE = re.compile(
    r"^Separate canonical-data preparation, translation selection, layout construction, "
    r"and artifact validation in `(?P<name>[^`\r\n]+)`; preserve snapshot report "
    r"fixtures and cross-format truth tests; target cyclomatic complexity at or below "
    r"(?P<threshold>\d+)\.$"
)
_COMPLEXITY_COLLECTION_RECOMMENDATION_RE = re.compile(
    r"^Split collection, normalization, classification, and serialization responsibilities "
    r"in `(?P<name>[^`\r\n]+)` into bounded pure helpers; preserve exact-SHA evidence "
    r"fixtures and add regression tests for failure and partial-evidence paths\.$"
)
_COMPLEXITY_COMMAND_RECOMMENDATION_RE = re.compile(
    r"^Separate argument parsing, orchestration, evidence assembly, and artifact writing in "
    r"`(?P<name>[^`\r\n]+)`; add command-level characterization tests and enforce the "
    r"approved complexity threshold\.$"
)
_COMPLEXITY_DEFAULT_RECOMMENDATION_RE = re.compile(
    r"^Decompose `(?P<name>[^`\r\n]+)` around cohesive branch groups, preserve behavior "
    r"with characterization tests, and enforce cyclomatic complexity at or below "
    r"(?P<threshold>\d+) on the exact remediation commit\.$"
)
_COMPLEXITY_DEFAULT_METHOD = "retained exact-SHA complexity evidence"
_COMPLEXITY_DEFAULT_METHOD_ES = "evidencia de complejidad conservada del SHA exacto"
_COMPLEXITY_MACHINE_METHOD_RE = re.compile(r"^[A-Za-z0-9_.@/+:-]+$")

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


def _translate_complexity_method(method: str) -> str | None:
    normalized = str(method or "").strip()
    if normalized == _COMPLEXITY_DEFAULT_METHOD:
        return _COMPLEXITY_DEFAULT_METHOD_ES
    # Scanner identifiers such as radon, lizard_cc, or provider/tool atoms are machine
    # evidence, not prose. Preserve only a deliberately narrow atom grammar. Verbose
    # unknown method descriptions still fall through to the canonical fail-closed gate.
    if _COMPLEXITY_MACHINE_METHOD_RE.fullmatch(normalized):
        return normalized
    return None


def _translate_generated_complexity_contract(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None

    match = _COMPLEXITY_ACCEPTANCE_RE.fullmatch(text)
    if match is not None:
        return (
            "La nueva ejecución sobre el SHA exacto ya no informa una complejidad "
            f"ciclomática superior a {match.group('threshold')} en "
            f"{match.group('location')}."
        )

    match = _COMPLEXITY_FACT_RE.fullmatch(text)
    if match is not None:
        method = _translate_complexity_method(match.group("method"))
        if method is None:
            return None
        return (
            f"cyclomatic_complexity={match.group('complexity')}; method={method}; "
            "source=evidencia de arquitectura conservada del SHA exacto"
        )

    match = _COMPLEXITY_EVIDENCE_RE.fullmatch(text)
    if match is not None:
        method = _translate_complexity_method(match.group("method"))
        if method is None:
            return None
        return (
            f"cyclomatic_complexity={match.group('complexity')}; method={method}; "
            f"exact_commit_match={match.group('exact')}"
        )

    match = _COMPLEXITY_TITLE_RE.fullmatch(text)
    if match is not None:
        return f"Reducir la complejidad en {match.group('name')}"

    match = _COMPLEXITY_INTERPRETATION_RE.fullmatch(text)
    if match is not None:
        return f"Ramificación concentrada en `{match.group('name')}`."

    match = _COMPLEXITY_REPORT_RECOMMENDATION_RE.fullmatch(text)
    if match is not None:
        return (
            "Separar la preparación de datos canónicos, la selección de traducción, la "
            "construcción del diseño y la validación de artefactos en "
            f"`{match.group('name')}`; conservar fixtures de informes de instantáneas y "
            "pruebas de coherencia entre formatos; fijar como objetivo una complejidad "
            f"ciclomática igual o inferior a {match.group('threshold')}."
        )

    match = _COMPLEXITY_COLLECTION_RECOMMENDATION_RE.fullmatch(text)
    if match is not None:
        return (
            "Separar las responsabilidades de recopilación, normalización, clasificación "
            f"y serialización de `{match.group('name')}` en helpers puros y acotados; "
            "conservar fixtures de evidencia del SHA exacto y agregar pruebas de regresión "
            "para rutas de fallo y de evidencia parcial."
        )

    match = _COMPLEXITY_COMMAND_RECOMMENDATION_RE.fullmatch(text)
    if match is not None:
        return (
            "Separar el análisis de argumentos, la orquestación, el ensamblaje de evidencia "
            f"y la escritura de artefactos en `{match.group('name')}`; agregar pruebas de "
            "caracterización a nivel de comando y aplicar el umbral de complejidad aprobado."
        )

    match = _COMPLEXITY_DEFAULT_RECOMMENDATION_RE.fullmatch(text)
    if match is not None:
        return (
            f"Descomponer `{match.group('name')}` alrededor de grupos cohesivos de ramas, "
            "preservar el comportamiento con pruebas de caracterización y aplicar una "
            f"complejidad ciclomática igual o inferior a {match.group('threshold')} en el "
            "commit exacto de remediación."
        )

    return None


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

    repaired = _repair_known_structured_spans(value)
    targeted = _translate_targeted_presentation_literal(repaired)
    if targeted is not None:
        return original(targeted)
    generated = _translate_generated_complexity_contract(repaired)
    if generated is not None:
        return original(generated)
    return original(repaired)


def _translate_canonical_field_v88(value: str, key: str) -> str:
    original = _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    if original is None:
        raise RuntimeError("Spanish exit-criteria v88 canonical translator is not installed")

    targeted = _translate_targeted_presentation_literal(value)
    if targeted is not None:
        # Exact approved presentation literals are safe on every presentation field.
        # The canonical translator still validates the resulting Spanish value.
        return original(targeted, key)

    generated = _translate_generated_complexity_contract(value)
    if generated is not None:
        # Dynamic generator contracts are accepted only after anchored full-match
        # recognition. Threshold, path, line, symbol, and method tokens are preserved.
        return original(generated, key)

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

    generated = _translate_generated_complexity_contract(value)
    if generated is not None:
        return original(generated)

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
    """Restore v88 surfaces without recapturing late delegating wrappers.

    The first installation captures the authoritative lower-level delegates. Detached
    report workers can run after later compatibility installers replace public aliases.
    Reasserting v88 must restore those aliases, but it must never promote a late wrapper
    to an ``_ORIGINAL_*`` delegate. A late wrapper can resolve the same public alias at
    call time; recapturing it would turn the repair into a self-recursive cycle during
    decision-report generation.
    """

    global _ORIGINAL_CANONICAL_TRANSLATE_FIELD
    global _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION
    global _ORIGINAL_PRESENTATION_SAFE_ES

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation

    if _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION is None:
        candidate = canonical._translate_presentation
        if candidate is _translate_presentation_v88:
            raise RuntimeError("Spanish v88 direct translator has no base delegate")
        _ORIGINAL_CANONICAL_TRANSLATE_PRESENTATION = candidate
    if canonical._translate_presentation is not _translate_presentation_v88:
        canonical._translate_presentation = _translate_presentation_v88

    if _ORIGINAL_CANONICAL_TRANSLATE_FIELD is None:
        candidate = canonical._translate_presentation_field
        if candidate is _translate_canonical_field_v88:
            raise RuntimeError("Spanish v88 canonical translator has no base delegate")
        _ORIGINAL_CANONICAL_TRANSLATE_FIELD = candidate
    if canonical._translate_presentation_field is not _translate_canonical_field_v88:
        canonical._translate_presentation_field = _translate_canonical_field_v88

    if _ORIGINAL_PRESENTATION_SAFE_ES is None:
        candidate = presentation._safe_es
        if candidate is _presentation_safe_es_v88:
            raise RuntimeError("Spanish v88 presentation guard has no base delegate")
        _ORIGINAL_PRESENTATION_SAFE_ES = candidate
    if presentation._safe_es is not _presentation_safe_es_v88:
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
    """Bind bounded production presentation contracts into Spanish surfaces."""

    global _ORIGINAL_NATIVE_BUILD_REPORT

    canonical, presentation = _bind_translation_surfaces()

    # Decision-report generation in the hosted Postgres runtime runs behind a detached
    # stage lease. Keep a call-time guard on the provider's shared report boundary so a
    # later compatibility installer cannot silently strand an es-MX worker with stale
    # translator aliases. Capture the lower-level provider exactly once: recapturing a
    # late wrapper that delegates through providers._build_report would make this guard
    # recurse into itself when the detached stage executes.
    from nico import comprehensive_native_providers as providers

    if _ORIGINAL_NATIVE_BUILD_REPORT is None:
        candidate = providers._build_report
        if candidate is _native_build_report_v88:
            raise RuntimeError("Spanish v88 report boundary has no base delegate")
        _ORIGINAL_NATIVE_BUILD_REPORT = candidate
    if providers._build_report is not _native_build_report_v88:
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
        "base_delegates_immutable": True,
        "late_wrapper_rebind_cycle_blocked": True,
        "targeted_fast_path": True,
        "targeted_rollback_translation": True,
        "generated_complexity_contract_translation": True,
        "parametric_acceptance_criteria_translation": True,
        "generated_complexity_fact_evidence_translation": True,
        "generated_complexity_machine_tokens_preserved": True,
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
