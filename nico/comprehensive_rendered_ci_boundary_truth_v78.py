from __future__ import annotations

import base64
import html
import io
import re
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader

from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_report_language_truth_v77 as language_v77

VERSION = "nico.comprehensive-rendered-ci-boundary-truth.v78.1"
_INSTALL_MARKER = "_nico_comprehensive_rendered_ci_boundary_truth_v78"
_VALIDATOR_MARKER = "_nico_rendered_ci_boundary_validator_v78"

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

# The persisted Comprehensive run identity is the authoritative language source.
# Root/package language fields are projections and may be rebuilt by compatibility
# layers, so they must never outrank identity.report_language at publication time.
_ROOT_REQUEST_LANGUAGE_KEYS = (
    "requested_report_language",
    "requested_language",
    "artifact_language",
    "output_language",
    "assessment_language",
    "client_language",
    "ui_language",
    "requested_locale",
    "output_locale",
    "ui_locale",
)
_REQUEST_LANGUAGE_KEYS = (
    "report_language",
    "locale",
    *_ROOT_REQUEST_LANGUAGE_KEYS,
    "language",
)
_REQUEST_CONTAINERS = (
    "request_metadata",
    "assessment_request",
    "original_request",
    "request_payload",
    "source_request",
    "request",
    "intake",
    "input",
    "assessment_metadata",
    "runtime_metadata",
    "report_metadata",
    "client_preferences",
    "options",
    "rendering",
)

_PREVIOUS_PRIVATE_RESOLVER = language_v77._resolve_report_language


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _request_scoped_language(canonical: Mapping[str, Any]) -> tuple[str, str]:
    identity = _mapping(canonical.get("identity"))
    for key in ("report_language", "locale", "requested_report_language"):
        resolved = language_v77._language_from_value(identity.get(key))
        if resolved:
            return resolved, f"run_identity:{key}"

    for key in _ROOT_REQUEST_LANGUAGE_KEYS:
        resolved = language_v77._language_from_value(canonical.get(key))
        if resolved:
            return resolved, f"request:root.{key}"

    assessment = _mapping(canonical.get("assessment"))
    containers: list[tuple[str, Mapping[str, Any]]] = [
        (name, _mapping(canonical.get(name))) for name in _REQUEST_CONTAINERS
    ]
    for parent_name, parent in (("identity", identity), ("assessment", assessment)):
        for name in _REQUEST_CONTAINERS:
            containers.append((f"{parent_name}.{name}", _mapping(parent.get(name))))

    for container_name, container in containers:
        for key in _REQUEST_LANGUAGE_KEYS:
            resolved = language_v77._language_from_value(container.get(key))
            if resolved:
                return resolved, f"request:{container_name}.{key}"
    return "", ""


def _resolve_report_language(canonical: Mapping[str, Any]) -> tuple[str, str]:
    requested, source = _request_scoped_language(canonical)
    if requested:
        return requested, source
    return _PREVIOUS_PRIVATE_RESOLVER(canonical)


def resolve_report_language(canonical: Mapping[str, Any]) -> str:
    """Resolve immutable run/request truth before synthesized canonical defaults."""

    return _resolve_report_language(canonical)[0]


def _normalize_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\u00a0", " ")
    return " ".join(text.split())


def _html_text(value: Any) -> str:
    return _normalize_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def _extract_pdf_text(result: Mapping[str, Any]) -> str:
    encoded = result.get("pdf_base64")
    if not encoded:
        return ""
    try:
        pdf = base64.b64decode(str(encoded), validate=True)
        return _normalize_text(
            "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
            )
        )
    except Exception:
        return ""


def _surface_texts(result: Mapping[str, Any]) -> dict[str, str]:
    return {
        "Markdown": _normalize_text(result.get("markdown")),
        "HTML": _html_text(result.get("html")),
        "PDF": _extract_pdf_text(result),
    }


def _coverage(text: str, markers: tuple[str, ...]) -> dict[str, Any]:
    normalized = _normalize_text(text)
    present = [marker for marker in markers if _normalize_text(marker) in normalized]
    missing = [marker for marker in markers if marker not in present]
    return {
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "required_count": len(markers),
        "complete": len(present) == len(markers),
    }


def rendered_ci_boundary_truth(result: Mapping[str, Any]) -> dict[str, Any]:
    """Describe rendered CI/CD structure without treating it as language authority."""

    surfaces = _surface_texts(result)
    combined = _normalize_text("\n".join(surfaces.values()))
    english = _coverage(combined, _EN_BOUNDARY_MARKERS)
    spanish = _coverage(combined, _ES_BOUNDARY_MARKERS)

    if english["complete"] and spanish["complete"]:
        detected_language = "conflict"
    elif spanish["complete"]:
        detected_language = "es-MX"
    elif english["complete"]:
        detected_language = "en"
    else:
        detected_language = ""

    per_surface: dict[str, Any] = {}
    for name, text in surfaces.items():
        per_surface[name.casefold()] = {
            "english": _coverage(text, _EN_BOUNDARY_MARKERS),
            "spanish": _coverage(text, _ES_BOUNDARY_MARKERS),
        }

    return {
        "version": VERSION,
        "language": detected_language,
        "english": english,
        "spanish": spanish,
        "per_surface": per_surface,
        "complete": detected_language in {"en", "es-MX"},
        "conflict": detected_language == "conflict",
        "rendered_artifact_is_language_authority": False,
    }


def _validate_authoritative_surfaces(
    result: Mapping[str, Any],
    *,
    language: str,
) -> dict[str, Any]:
    expected = _ES_BOUNDARY_MARKERS if language == "es-MX" else _EN_BOUNDARY_MARKERS
    opposite_language = "en" if language == "es-MX" else "es-MX"
    opposite = _EN_BOUNDARY_MARKERS if language == "es-MX" else _ES_BOUNDARY_MARKERS
    surfaces = _surface_texts(result)
    coverage: dict[str, Any] = {}

    for surface_name, text in surfaces.items():
        surface_coverage = _coverage(text, expected)
        coverage[surface_name.casefold()] = surface_coverage
        if not surface_coverage["complete"]:
            marker = list(surface_coverage["missing"])[0]
            raise ValueError(
                f"client report omitted {language} CI/CD boundary in {surface_name}: {marker}"
            )
        normalized = _normalize_text(text)
        for marker in opposite:
            if _normalize_text(marker) in normalized:
                raise ValueError(
                    f"client report contains {opposite_language} CI/CD boundary in "
                    f"{surface_name} for authoritative {language} report: {marker}"
                )
    return coverage


def reconcile_rendered_ci_boundary_language(
    result: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Validate rendered surfaces against immutable run/request language truth."""

    canonical = deepcopy(dict(_mapping(result.get("json"))))
    language, source = _resolve_report_language(canonical)
    if language not in {"en", "es-MX"}:
        raise ValueError("authoritative report language is unavailable")

    surface_coverage = _validate_authoritative_surfaces(result, language=language)
    truth = rendered_ci_boundary_truth(result)

    identity = deepcopy(dict(_mapping(canonical.get("identity"))))
    identity["report_language"] = language
    canonical["identity"] = identity
    assessment = deepcopy(dict(_mapping(canonical.get("assessment"))))
    assessment["report_language"] = language
    assessment["locale"] = language
    canonical["assessment"] = assessment
    canonical["report_language"] = language
    canonical["locale"] = language

    contract = deepcopy(dict(_mapping(canonical.get("v2_prepublication_contract"))))
    contract.update(
        {
            "rendered_ci_boundary_truth_version": VERSION,
            "authoritative_report_language": language,
            "report_language_authority_source": source,
            "rendered_ci_boundary_language": language,
            "rendered_ci_boundary_complete": True,
            "rendered_ci_boundary_overrode_canonical_language": False,
            "rendered_artifact_is_language_authority": False,
            "ci_cd_surfaces_validated_independently": True,
            "mixed_language_structural_markers_rejected": True,
            "ci_cd_surface_coverage": surface_coverage,
        }
    )
    canonical["v2_prepublication_contract"] = contract
    result["json"] = canonical
    result["report_language"] = language
    result["locale"] = language
    result["rendered_ci_boundary_truth"] = {
        **truth,
        "language": language,
        "authoritative_language": language,
        "authority_source": source,
        "surface_coverage": surface_coverage,
    }
    return result["rendered_ci_boundary_truth"]


def _patch_final_validator() -> bool:
    current: Callable[[Mapping[str, Any]], None] = final_truth._validate_surfaces
    if getattr(current, _VALIDATOR_MARKER, False):
        return True

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        if isinstance(result, MutableMapping):
            reconcile_rendered_ci_boundary_language(result)
            current(result)
            return
        repaired: dict[str, Any] = deepcopy(dict(result))
        reconcile_rendered_ci_boundary_language(repaired)
        current(repaired)

    setattr(_validate_surfaces, _VALIDATOR_MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    final_truth._validate_surfaces = _validate_surfaces
    return final_truth._validate_surfaces is _validate_surfaces


def install_comprehensive_rendered_ci_boundary_truth_v78() -> dict[str, Any]:
    """Bind persisted run-language authority and final per-surface validation."""

    already_installed = getattr(final_truth, _INSTALL_MARKER, False)

    # Previously bound renderers perform global lookup in v77. Rebinding both
    # entry points keeps one runtime resolver decision across every producer.
    language_v77._resolve_report_language = _resolve_report_language
    language_v77.resolve_report_language = resolve_report_language

    validator_bound = _patch_final_validator()
    setattr(final_truth, _INSTALL_MARKER, True)
    return {
        "status": "rebound" if already_installed else "installed",
        "version": VERSION,
        "run_identity_language_precedes_synthesized_default": True,
        "request_language_precedes_synthesized_default": True,
        "rendered_ci_boundary_is_final_authority": False,
        "rendered_ci_boundary_validated_against_authority": True,
        "stale_projected_language_is_reconciled": True,
        "mixed_language_structural_markers_fail_closed": True,
        "surface_validation_independent": True,
        "validator_bound": validator_bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_rendered_ci_boundary_truth_v78",
    "reconcile_rendered_ci_boundary_language",
    "rendered_ci_boundary_truth",
    "resolve_report_language",
]
