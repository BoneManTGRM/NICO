from __future__ import annotations

import base64
import io
import re
import unicodedata
from collections.abc import Mapping, MutableMapping
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader

from nico import client_report_completion_v1 as legacy_report
from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_ci_operational_truth_v71 as ci_truth
from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_review_candidate_publication_v75 as publication
from nico import comprehensive_spanish_review_candidate_truth_v70 as legacy_candidate

VERSION = "nico.comprehensive-report-language-truth.v77"
_INSTALL_MARKER = "_nico_comprehensive_report_language_truth_v77"
_NORMALIZER_MARKER = "_nico_report_language_normalizer_v77"
_VALIDATOR_MARKER = "_nico_report_language_validator_v77"
_FUNCTION_MARKER = "_nico_report_language_resolver_v77"

_ES_BOUNDARY_MARKERS = (
    "A. Madurez de configuración de CI/CD:",
    "B. Preparación operativa actual:",
    "C. Estado de las verificaciones requeridas:",
    "D. Resultados históricos de los flujos de trabajo",
)
_EN_BOUNDARY_MARKERS = (
    "A. CI/CD configuration maturity:",
    "B. Current operational readiness:",
    "C. Required-check health:",
    "D. Historical workflow outcomes",
)

_LANGUAGE_ALIASES = (
    "artifact_language",
    "output_language",
    "requested_language",
    "assessment_language",
    "client_language",
    "ui_language",
    "language",
    "requested_locale",
    "output_locale",
    "ui_locale",
)
_LANGUAGE_CONTAINERS = (
    "review_metadata",
    "assessment_metadata",
    "request_metadata",
    "runtime_metadata",
    "report_metadata",
    "client_preferences",
    "request",
    "options",
    "rendering",
)
_BOOLEAN_LANGUAGE_KEYS = (
    "spanish",
    "is_spanish",
    "render_spanish",
    "spanish_report",
)
_PROBE_FIELDS = (
    "executive_summary",
    "improvement_summary",
    "delivery_summary",
    "decision_summary",
    "risk_summary",
    "recommendation_line",
    "recommendation",
    "recommendations",
    "next_steps",
    "summary",
    "description",
    "status",
    "title",
    "narrative",
    "client_report",
    "client_facing_version",
    "report",
    "markdown",
)
_PROBE_NESTED_FIELDS = (
    "maturity_signal",
    "client_readiness_contract",
    "v2_prepublication_contract",
    "review_candidate_summary",
)
_SPANISH_STRONG_MARKERS = (
    "resumen ejecutivo",
    "se recomienda",
    "evaluacion tecnica",
    "madurez tecnica",
    "evidencia considerada",
    "registro de hallazgos",
    "hallazgos y remediacion",
    "requiere revision",
    "estado de entrega",
    "preparacion operativa",
    "verificaciones requeridas",
    "resultados historicos",
    "recomendacion prioritaria",
    "aprobacion humana",
    "borrador automatizado",
    "riesgos principales",
    "repositorio evaluado",
)
_SPANISH_TOKENS = {
    "aprobacion",
    "cliente",
    "configuracion",
    "de",
    "del",
    "evidencia",
    "evaluacion",
    "hallazgos",
    "la",
    "las",
    "los",
    "madurez",
    "para",
    "preparacion",
    "que",
    "recomendacion",
    "recomienda",
    "remediacion",
    "repositorio",
    "requiere",
    "revision",
    "riesgo",
    "se",
    "tecnica",
    "tecnico",
    "verificaciones",
}
_ENGLISH_TOKENS = {
    "and",
    "assessment",
    "client",
    "configuration",
    "evidence",
    "findings",
    "for",
    "maturity",
    "recommendation",
    "remediation",
    "repository",
    "requires",
    "review",
    "risk",
    "technical",
    "the",
    "to",
    "with",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str("" if value is None else value).split()).strip()
    return normalized if len(normalized) <= limit else normalized[:limit]


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value, 50000).casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _language_from_value(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("code", "value", "locale", "language", "id"):
            resolved = _language_from_value(value.get(key))
            if resolved:
                return resolved
        return ""
    if isinstance(value, bool) or value is None:
        return ""

    normalized = _text(value, 120).casefold().replace("_", "-")
    if not normalized:
        return ""
    if (
        re.fullmatch(r"es(?:-[a-z0-9]+)*", normalized)
        or normalized in {"spanish", "espanol", "español", "castellano"}
        or normalized.startswith("spanish (")
        or normalized.startswith("espanol (")
        or normalized.startswith("español (")
    ):
        return "es-MX"
    if (
        re.fullmatch(r"en(?:-[a-z0-9]+)*", normalized)
        or normalized in {"english", "ingles", "inglés"}
        or normalized.startswith("english (")
    ):
        return "en"
    return ""


def _explicit_language(canonical: Mapping[str, Any]) -> tuple[str, str]:
    identity = _mapping(canonical.get("identity"))
    assessment = _mapping(canonical.get("assessment"))

    # Preserve the historical authoritative order before accepting newer aliases.
    candidates: list[tuple[str, Any]] = [
        ("report_language", canonical.get("report_language")),
        ("locale", canonical.get("locale")),
        ("identity.report_language", identity.get("report_language")),
        ("assessment.report_language", assessment.get("report_language")),
    ]
    for key in _LANGUAGE_ALIASES:
        candidates.append((key, canonical.get(key)))
    for container_name, container in (("identity", identity), ("assessment", assessment)):
        for key in ("locale", *_LANGUAGE_ALIASES):
            candidates.append((f"{container_name}.{key}", container.get(key)))
    for container_name in _LANGUAGE_CONTAINERS:
        container = _mapping(canonical.get(container_name))
        for key in ("report_language", "locale", *_LANGUAGE_ALIASES):
            candidates.append((f"{container_name}.{key}", container.get(key)))

    for source, value in candidates:
        resolved = _language_from_value(value)
        if resolved:
            return resolved, f"explicit:{source}"

    boolean_containers: list[tuple[str, Mapping[str, Any]]] = [
        ("root", canonical),
        ("identity", identity),
        ("assessment", assessment),
    ]
    boolean_containers.extend(
        (name, _mapping(canonical.get(name))) for name in _LANGUAGE_CONTAINERS
    )
    for container_name, container in boolean_containers:
        for key in _BOOLEAN_LANGUAGE_KEYS:
            value = container.get(key)
            if isinstance(value, bool):
                return ("es-MX" if value else "en"), f"explicit:{container_name}.{key}"
    return "", ""


def _iter_probe_strings(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    if isinstance(value, str):
        text = _text(value, 8000)
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in list(value)[:40]:
            output.extend(_iter_probe_strings(item, depth=depth + 1))
            if sum(len(part) for part in output) >= 40000:
                break
        return output
    if isinstance(value, Mapping):
        output = []
        for key in _PROBE_FIELDS:
            if key in value:
                output.extend(_iter_probe_strings(value.get(key), depth=depth + 1))
        return output
    return []


def _language_probe(canonical: Mapping[str, Any]) -> str:
    identity = _mapping(canonical.get("identity"))
    assessment = _mapping(canonical.get("assessment"))
    containers: list[Mapping[str, Any]] = [canonical, identity, assessment]
    containers.extend(_mapping(canonical.get(name)) for name in _LANGUAGE_CONTAINERS)

    parts: list[str] = []
    for container in containers:
        for key in _PROBE_FIELDS:
            parts.extend(_iter_probe_strings(container.get(key)))
        for key in _PROBE_NESTED_FIELDS:
            parts.extend(_iter_probe_strings(container.get(key)))

    for collection in (assessment.get("sections"), canonical.get("stage_summaries")):
        for item in list(collection or [])[:30]:
            if not isinstance(item, Mapping):
                continue
            for key in ("title", "summary", "status", "description", "recommendation", "evidence"):
                parts.extend(_iter_probe_strings(item.get(key)))

    return "\n".join(parts)[:50000]


def _looks_spanish(value: Any) -> bool:
    raw = _text(value, 50000)
    folded = _fold(raw)
    if not folded:
        return False
    if any(marker in folded for marker in _SPANISH_STRONG_MARKERS):
        return True

    tokens = re.findall(r"[a-z]+", folded)
    spanish_score = sum(token in _SPANISH_TOKENS for token in tokens)
    english_score = sum(token in _ENGLISH_TOKENS for token in tokens)
    accented = sum(character in "áéíóúüñ¿¡" for character in raw.casefold())
    return (
        accented >= 2 and spanish_score >= 2
    ) or (
        spanish_score >= 5 and spanish_score >= english_score + 2
    )


def _resolve_report_language(canonical: Mapping[str, Any]) -> tuple[str, str]:
    explicit, source = _explicit_language(canonical)
    if explicit:
        return explicit, source
    if _looks_spanish(_language_probe(canonical)):
        return "es-MX", "content:canonical-spanish"
    return "en", "default:english"


def resolve_report_language(canonical: Mapping[str, Any]) -> str:
    """Resolve one authoritative Comprehensive artifact language."""

    return _resolve_report_language(canonical)[0]


def normalize_report_language_metadata(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Promote explicit or strongly inferred language to the canonical root."""

    output = dict(canonical)
    language, source = _resolve_report_language(output)
    if not source.startswith("default:"):
        output["report_language"] = language
    return output


def _extract_pdf_text(result: Mapping[str, Any]) -> str:
    encoded = result.get("pdf_base64")
    if not encoded:
        return ""
    try:
        pdf = base64.b64decode(str(encoded), validate=True)
        return "\n".join(
            page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
        )
    except Exception:
        return ""


def rendered_boundary_language(result: Mapping[str, Any]) -> str:
    """Return the language of a complete rendered CI/CD boundary."""

    text = "\n".join(
        (
            str(result.get("markdown") or ""),
            str(result.get("html") or ""),
        )
    )
    spanish_complete = all(marker in text for marker in _ES_BOUNDARY_MARKERS)
    english_complete = all(marker in text for marker in _EN_BOUNDARY_MARKERS)
    if not spanish_complete and not english_complete:
        text += "\n" + _extract_pdf_text(result)
        spanish_complete = all(marker in text for marker in _ES_BOUNDARY_MARKERS)
        english_complete = all(marker in text for marker in _EN_BOUNDARY_MARKERS)
    if spanish_complete and english_complete:
        return "conflict"
    if spanish_complete:
        return "es-MX"
    if english_complete:
        return "en"
    return ""


def _report_language(canonical: Mapping[str, Any]) -> str:
    return resolve_report_language(canonical)


def _is_spanish_with_override(
    canonical: Mapping[str, Any],
    spanish: bool = False,
) -> bool:
    return bool(spanish) or resolve_report_language(canonical) == "es-MX"


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    return resolve_report_language(canonical) == "es-MX"


def _mark(function: Callable[..., Any]) -> Callable[..., Any]:
    setattr(function, _FUNCTION_MARKER, True)
    return function


def _patch_final_normalizer() -> bool:
    current = final_truth.normalize_client_truth
    if getattr(current, _NORMALIZER_MARKER, False):
        return True

    @wraps(current)
    def normalize_client_truth(canonical: Mapping[str, Any]) -> dict[str, Any]:
        normalized = current(canonical)
        return normalize_report_language_metadata(normalized)

    setattr(normalize_client_truth, _NORMALIZER_MARKER, True)
    setattr(normalize_client_truth, "_nico_previous", current)
    final_truth.normalize_client_truth = normalize_client_truth
    return final_truth.normalize_client_truth is normalize_client_truth


def _patch_final_validator() -> bool:
    current = final_truth._validate_surfaces
    if getattr(current, _VALIDATOR_MARKER, False):
        return True

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        canonical = _mapping(result.get("json"))
        normalized = normalize_report_language_metadata(canonical)
        _language, source = _resolve_report_language(canonical)
        if source.startswith("default:"):
            rendered_language = rendered_boundary_language(result)
            if rendered_language == "conflict":
                raise ValueError(
                    "client report contains conflicting English and Spanish CI/CD boundaries"
                )
            if rendered_language:
                normalized["report_language"] = rendered_language

        if isinstance(result, MutableMapping):
            result["json"] = normalized
            current(result)
            return
        repaired = dict(result)
        repaired["json"] = normalized
        current(repaired)

    setattr(_validate_surfaces, _VALIDATOR_MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    final_truth._validate_surfaces = _validate_surfaces
    return final_truth._validate_surfaces is _validate_surfaces


def install_comprehensive_report_language_truth_v77() -> dict[str, Any]:
    """Unify report-language truth across producers, renderers, and gates."""

    already_installed = getattr(final_truth, _INSTALL_MARKER, False)

    _mark(_report_language)
    _mark(_is_spanish_with_override)
    _mark(_is_spanish)

    final_truth._report_language = _report_language
    ci_v74._is_spanish = _is_spanish_with_override
    ci_truth._is_spanish = _is_spanish_with_override
    publication._is_spanish = _is_spanish_with_override
    legacy_report._is_spanish = _is_spanish
    legacy_candidate._is_spanish = _is_spanish

    normalizer_bound = _patch_final_normalizer()
    validator_bound = _patch_final_validator()
    setattr(final_truth, _INSTALL_MARKER, True)

    return {
        "status": "rebound" if already_installed else "installed",
        "version": VERSION,
        "explicit_language_precedence_preserved": True,
        "language_aliases_supported": True,
        "canonical_spanish_inference_supported": True,
        "rendered_boundary_recovery_supported": True,
        "conflicting_bilingual_boundaries_fail_closed": True,
        "final_normalizer_bound": normalizer_bound,
        "final_validator_bound": validator_bound,
        "english_and_spanish_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_language_truth_v77",
    "normalize_report_language_metadata",
    "rendered_boundary_language",
    "resolve_report_language",
]
