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

VERSION = "nico.comprehensive-rendered-ci-boundary-truth.v78"
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

# Request-scoped values outrank canonical defaults. Root report_language and
# locale remain supported by the v77 resolver, but they are intentionally not
# included here because upstream normalization can synthesize a default "en".
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
    for key in _ROOT_REQUEST_LANGUAGE_KEYS:
        resolved = language_v77._language_from_value(canonical.get(key))
        if resolved:
            return resolved, f"request:root.{key}"

    identity = _mapping(canonical.get("identity"))
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
    """Resolve request truth before any synthesized canonical language default."""

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
    """Classify the actual final Markdown, HTML, and PDF CI/CD boundary."""

    surfaces = {
        "markdown": _normalize_text(result.get("markdown")),
        "html": _html_text(result.get("html")),
        "pdf": _extract_pdf_text(result),
    }
    combined = _normalize_text("\n".join(surfaces.values()))
    english = _coverage(combined, _EN_BOUNDARY_MARKERS)
    spanish = _coverage(combined, _ES_BOUNDARY_MARKERS)

    if english["complete"] and spanish["complete"]:
        language = "conflict"
    elif spanish["complete"]:
        language = "es-MX"
    elif english["complete"]:
        language = "en"
    else:
        language = ""

    per_surface: dict[str, Any] = {}
    for name, text in surfaces.items():
        per_surface[name] = {
            "english": _coverage(text, _EN_BOUNDARY_MARKERS),
            "spanish": _coverage(text, _ES_BOUNDARY_MARKERS),
        }

    return {
        "version": VERSION,
        "language": language,
        "english": english,
        "spanish": spanish,
        "per_surface": per_surface,
        "complete": language in {"en", "es-MX"},
        "conflict": language == "conflict",
    }


def _expected_language_for_incomplete_boundary(
    result: Mapping[str, Any],
    truth: Mapping[str, Any],
) -> str:
    spanish = _mapping(truth.get("spanish"))
    english = _mapping(truth.get("english"))
    spanish_count = int(spanish.get("present_count") or 0)
    english_count = int(english.get("present_count") or 0)
    if spanish_count > english_count:
        return "es-MX"
    if english_count > spanish_count:
        return "en"
    canonical = _mapping(result.get("json"))
    return resolve_report_language(canonical)


def reconcile_rendered_ci_boundary_language(
    result: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Make the complete rendered boundary authoritative for publication."""

    truth = rendered_ci_boundary_truth(result)
    language = str(truth.get("language") or "")
    if language == "conflict":
        raise ValueError(
            "client report contains complete English and Spanish CI/CD boundaries"
        )
    if not language:
        expected = _expected_language_for_incomplete_boundary(result, truth)
        coverage = _mapping(
            truth.get("spanish") if expected == "es-MX" else truth.get("english")
        )
        missing = list(coverage.get("missing") or [])
        marker = missing[0] if missing else (
            _ES_BOUNDARY_MARKERS[0] if expected == "es-MX" else _EN_BOUNDARY_MARKERS[0]
        )
        raise ValueError(f"client report omitted CI/CD boundary: {marker}")

    canonical = deepcopy(dict(_mapping(result.get("json"))))
    prior_language = language_v77.resolve_report_language(canonical)
    canonical["report_language"] = language
    contract = deepcopy(dict(_mapping(canonical.get("v2_prepublication_contract"))))
    contract.update(
        {
            "rendered_ci_boundary_truth_version": VERSION,
            "rendered_ci_boundary_language": language,
            "rendered_ci_boundary_complete": True,
            "rendered_ci_boundary_overrode_canonical_language": (
                prior_language != language
            ),
        }
    )
    canonical["v2_prepublication_contract"] = contract
    result["json"] = canonical
    result["rendered_ci_boundary_truth"] = truth
    return truth


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
    """Bind request precedence and rendered final-artifact CI/CD truth last."""

    already_installed = getattr(final_truth, _INSTALL_MARKER, False)

    # All v77-bound renderer functions perform global lookup in the v77 module,
    # so rebinding both resolver entry points updates every previously bound
    # producer without another chain of renderer wrappers.
    language_v77._resolve_report_language = _resolve_report_language
    language_v77.resolve_report_language = resolve_report_language

    validator_bound = _patch_final_validator()
    setattr(final_truth, _INSTALL_MARKER, True)
    return {
        "status": "rebound" if already_installed else "installed",
        "version": VERSION,
        "request_language_precedes_synthesized_default": True,
        "rendered_ci_boundary_is_final_authority": True,
        "stale_canonical_language_is_reconciled": True,
        "complete_bilingual_conflict_fails_closed": True,
        "incomplete_boundary_fails_closed": True,
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
