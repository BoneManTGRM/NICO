from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-spanish-current-copy-worker.v98.1"
_ONE_ARG_MARKER = "__nico_spanish_current_copy_worker_one_v98__"
_TWO_ARG_MARKER = "__nico_spanish_current_copy_worker_two_v98__"

_STATE_ES = {
    "passed": "aprobado",
    "failed": "fallido",
    "not_assessed": "no evaluado",
    "not assessed": "no evaluado",
}
_BOOLEAN_ES = {
    "true": "sí",
    "false": "no",
    "not assessed": "no evaluada",
}

# These are generator contracts, not a screenshot allowlist. Dynamic values are
# captured and preserved while the renderer-owned sentence is projected to es-MX.
_PROVIDER_WORKFLOW_FILES_RE = re.compile(
    r"Workflow files at assessed commit: (?P<count>\d+)\."
)
_PROVIDER_EXACT_SHA_RE = re.compile(
    r"Workflow configuration exact-SHA match: (?P<state>True|False|not assessed)\.",
    re.IGNORECASE,
)
_PROVIDER_PERMISSION_RE = re.compile(
    r"Explicit permissions control: (?P<state>passed|failed|not_assessed|not assessed)\.",
    re.IGNORECASE,
)
_PROVIDER_COVERAGE_RE = re.compile(
    r"Provider-neutral immutable CI objective coverage: (?P<coverage>\d+(?:\.\d+)?%)\."
)
_PROVIDER_ASSURANCE_RE = re.compile(
    r"CI control assurance incomplete; no pass/fail claim was made for: (?P<objectives>[^.]+)\."
)
_CANDIDATE_VOLUME_RE = re.compile(
    r"Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or "
    r"(?:Evidence-Adjusted|Ajuste por evidencia) score effect\."
)

_STATIC_GENERATOR_COPY = {
    "Historical workflow, job, and deployment outcomes are retained as an unscored operational trend.": (
        "Los resultados históricos de flujos de trabajo, trabajos y despliegues se conservan como una tendencia operativa sin puntuación."
    ),
    "No workflow configuration was retained at the assessed commit.": (
        "No se conservó configuración de flujos de trabajo en el commit evaluado."
    ),
    "Workflow configuration was not proven against the exact assessed commit.": (
        "No se demostró la configuración de flujos de trabajo contra el commit exacto evaluado."
    ),
    "Explicit workflow permission boundaries were assessed and not proven at the assessed commit.": (
        "Se evaluaron los límites explícitos de permisos del flujo de trabajo y no se demostraron en el commit evaluado."
    ),
}


def _current_report_phrase_pairs() -> tuple[tuple[str, str], ...]:
    """Return approved static final-report presentation pairs."""

    from nico.comprehensive_current_report_truth_parity_v1 import _ES_PHRASES

    return tuple(
        sorted(
            ((str(source), str(target)) for source, target in _ES_PHRASES.items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def _translate_structured_current_report_copy(text: str) -> str:
    def workflow_files(match: re.Match[str]) -> str:
        return f"Archivos de flujo de trabajo en el commit evaluado: {match.group('count')}."

    def exact_sha(match: re.Match[str]) -> str:
        state = _BOOLEAN_ES.get(match.group("state").casefold(), match.group("state"))
        return f"Coincidencia exacta de SHA de la configuración del flujo de trabajo: {state}."

    def permission(match: re.Match[str]) -> str:
        state = _STATE_ES.get(match.group("state").casefold(), match.group("state"))
        return f"Control de permisos explícitos: {state}."

    def coverage(match: re.Match[str]) -> str:
        return (
            "Cobertura de objetivos inmutables de CI independiente del proveedor: "
            f"{match.group('coverage')}."
        )

    def assurance(match: re.Match[str]) -> str:
        # Objective identifiers are canonical machine keys and intentionally remain exact.
        return (
            "La garantía de los controles de CI está incompleta; no se afirmó aprobación ni fallo para: "
            f"{match.group('objectives')}."
        )

    output = str(text or "")
    output = _PROVIDER_WORKFLOW_FILES_RE.sub(workflow_files, output)
    output = _PROVIDER_EXACT_SHA_RE.sub(exact_sha, output)
    output = _PROVIDER_PERMISSION_RE.sub(permission, output)
    output = _PROVIDER_COVERAGE_RE.sub(coverage, output)
    output = _PROVIDER_ASSURANCE_RE.sub(assurance, output)
    output = _CANDIDATE_VOLUME_RE.sub(
        "El volumen de candidatos y la carga de trabajo del revisor son métricas operativas de revisión y no tienen efecto numérico sobre la madurez técnica ni sobre la puntuación de Ajuste por evidencia.",
        output,
    )
    for source, target in _STATIC_GENERATOR_COPY.items():
        output = output.replace(source, target)
    return output


def localize_current_report_copy_v98(value: Any) -> str:
    """Project registered NICO-authored current-report copy to es-MX.

    Structured generator families are translated by grammar so dynamic values remain
    exact. Static approved phrases are then applied. Unknown prose is deliberately left
    unchanged so the canonical Spanish translator can fail closed rather than publish
    mixed-language presentation copy.
    """

    text = _translate_structured_current_report_copy(str(value or ""))
    for source, target in _current_report_phrase_pairs():
        text = text.replace(source, target)
    return text


def _wrap_one_arg(current: Callable[[Any], str]) -> Callable[[Any], str]:
    if getattr(current, _ONE_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any) -> str:
        return current(localize_current_report_copy_v98(value))

    setattr(wrapped, _ONE_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def _wrap_two_arg(current: Callable[[Any, Any], str]) -> Callable[[Any, Any], str]:
    if getattr(current, _TWO_ARG_MARKER, False):
        return current

    @wraps(current)
    def wrapped(value: Any, key: Any = "") -> str:
        return current(localize_current_report_copy_v98(value), key)

    setattr(wrapped, _TWO_ARG_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    return wrapped


def install_comprehensive_spanish_current_copy_worker_v98() -> dict[str, Any]:
    """Bind current report localization before the isolated renderer cache freezes."""

    from nico import comprehensive_spanish_exit_criteria_v88 as v88

    baseline = v88.install_comprehensive_spanish_exit_criteria_v88()
    if baseline.get("bound") is not True:
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_v88_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    current_field = getattr(v88, "_translate_canonical_field_v88", None)
    current_presentation = getattr(v88, "_translate_presentation_v88", None)
    current_safe = getattr(v88, "_presentation_safe_es_v88", None)
    if not all(callable(value) for value in (current_field, current_presentation, current_safe)):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "spanish_current_copy_translation_surface_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    field = _wrap_two_arg(current_field)
    presentation = _wrap_one_arg(current_presentation)
    safe = _wrap_one_arg(current_safe)
    v88._translate_canonical_field_v88 = field
    v88._translate_presentation_v88 = presentation
    v88._presentation_safe_es_v88 = safe

    binder = getattr(v88, "_bind_translation_surfaces", None)
    if callable(binder):
        binder()

    from nico import comprehensive_spanish_canonical_report_v87 as canonical
    from nico import comprehensive_spanish_presentation_parity_v1 as presentation_module

    bound = bool(
        canonical._translate_presentation_field is field
        and canonical._translate_presentation is presentation
        and presentation_module._safe_es is safe
    )
    sample = localize_current_report_copy_v98(
        "Explicit permissions control: passed. Provider-neutral immutable CI objective coverage: 100%. "
        "Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or Evidence-Adjusted score effect."
    )
    sample_ok = (
        "Explicit permissions control" not in sample
        and "Provider-neutral immutable CI objective coverage" not in sample
        and "Candidate volume and reviewer workload" not in sample
        and "Control de permisos explícitos: aprobado." in sample
        and "Cobertura de objetivos inmutables de CI independiente del proveedor: 100%." in sample
        and "El volumen de candidatos y la carga de trabajo del revisor" in sample
    )

    return {
        "status": "installed" if bound and sample_ok else "blocked",
        "version": VERSION,
        "bound": bound,
        "current_report_copy_contract_bound": sample_ok,
        "structured_provider_ci_copy_bound": True,
        "worker_safe_before_renderer_cache": True,
        "unknown_prose_still_delegates_fail_closed": True,
        "canonical_report_truth_unchanged": True,
        "scanner_truth_unchanged": True,
        "score_truth_unchanged": True,
        "english_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_current_copy_worker_v98",
    "localize_current_report_copy_v98",
]
