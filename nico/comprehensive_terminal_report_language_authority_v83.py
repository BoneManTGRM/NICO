from __future__ import annotations

import base64
import html
import io
import re
from functools import wraps
from typing import Any, Callable, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-terminal-report-language-authority.v83"
_EXPLICIT_MARKER = "_nico_terminal_language_explicit_v83"
_VALIDATOR_MARKER = "_nico_terminal_language_validator_v83"
_FUNCTION_MARKER = "_nico_terminal_language_function_v83"
_LEGACY_RAW_CI_BOUNDARY_PREFIX = "client report omitted CI/CD boundary:"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize(value: Any) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def _visible_html(value: Any) -> str:
    return _normalize(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))))


def _pdf_text(result: Mapping[str, Any]) -> str:
    encoded = str(result.get("pdf_base64") or "")
    if not encoded:
        return ""
    try:
        pdf = base64.b64decode(encoded, validate=True)
        return _normalize(
            "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
            )
        )
    except Exception as exc:
        raise ValueError("client report PDF could not be decoded for CI/CD language validation") from exc


def _patch_shared_language_authority() -> bool:
    """Make the persisted run identity outrank mutable publication projections.

    v77 remains the one shared report-language resolver. This terminal patch changes
    only the precedence of its explicit-source lookup so a persisted run language can
    never be replaced by a stale root/package projection created later in the pipeline.
    """

    from nico import comprehensive_report_language_truth_v77 as language

    current = language._explicit_language
    if getattr(current, _EXPLICIT_MARKER, False):
        return True

    @wraps(current)
    def _explicit_language(canonical: Mapping[str, Any]) -> tuple[str, str]:
        identity = _mapping(canonical.get("identity"))
        for key in (
            "report_language",
            "requested_report_language",
            "requested_locale",
            "locale",
        ):
            resolved = language._language_from_value(identity.get(key))
            if resolved:
                return resolved, f"explicit:identity.{key}"
        return current(canonical)

    setattr(_explicit_language, _EXPLICIT_MARKER, True)
    setattr(_explicit_language, "_nico_previous", current)
    language._explicit_language = _explicit_language
    return language._explicit_language is _explicit_language


def _authoritative_language(canonical: Mapping[str, Any]) -> str:
    from nico import comprehensive_report_language_truth_v77 as language

    return language.resolve_report_language(canonical)


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    return _authoritative_language(canonical) == "es-MX"


def _is_spanish_with_override(
    canonical: Mapping[str, Any],
    spanish: bool = False,
) -> bool:
    return bool(spanish) or _is_spanish(canonical)


def _ci_boundary_markers(canonical: Mapping[str, Any]) -> tuple[str, ...]:
    from nico import comprehensive_ci_boundary_compat_v74 as ci_boundary

    return ci_boundary.ci_cd_boundary_markers(
        canonical,
        spanish=_is_spanish(canonical),
    )


def _ci_lines(canonical: Mapping[str, Any]) -> list[str]:
    from nico import comprehensive_ci_boundary_compat_v74 as ci_boundary

    return ci_boundary.ci_cd_boundary_lines(
        canonical,
        spanish=_is_spanish(canonical),
    )


def _validate_authoritative_ci_surfaces(result: Mapping[str, Any]) -> dict[str, Any]:
    from nico import comprehensive_report_language_truth_v77 as language

    canonical = _mapping(result.get("json"))
    selected = _authoritative_language(canonical)
    selected_markers = (
        language._ES_BOUNDARY_MARKERS
        if selected == "es-MX"
        else language._EN_BOUNDARY_MARKERS
    )
    opposite_language = "en" if selected == "es-MX" else "es-MX"
    opposite_markers = (
        language._EN_BOUNDARY_MARKERS
        if selected == "es-MX"
        else language._ES_BOUNDARY_MARKERS
    )
    surfaces = {
        "Markdown": _normalize(result.get("markdown")),
        "HTML": _visible_html(result.get("html")),
        "PDF": _pdf_text(result),
    }

    coverage: dict[str, Any] = {}
    for surface_name, surface_text in surfaces.items():
        normalized_surface = _normalize(surface_text)
        missing = [
            marker
            for marker in selected_markers
            if _normalize(marker) not in normalized_surface
        ]
        if missing:
            raise ValueError(
                f"client report omitted {selected} CI/CD boundary in {surface_name}: "
                f"{missing[0]}"
            )
        mixed = [
            marker
            for marker in opposite_markers
            if _normalize(marker) in normalized_surface
        ]
        if mixed:
            raise ValueError(
                f"client report contains {opposite_language} CI/CD boundary in "
                f"{surface_name} for authoritative {selected} report: {mixed[0]}"
            )
        coverage[surface_name.casefold()] = {
            "complete": True,
            "marker_count": len(selected_markers),
        }

    return {
        "authoritative_report_language": selected,
        "surface_coverage": coverage,
        "independent_markdown_html_pdf_validation": True,
        "mixed_language_structural_markers_rejected": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _validate_with_legacy_ci_compat(
    current_validate: Callable[[Mapping[str, Any]], None],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the strong surface gate and suppress only its obsolete raw-text duplicate.

    The pre-v83 validator searches one raw Markdown+HTML+PDF string for an exact CI/CD
    marker. Production renderers can legitimately wrap the label across whitespace,
    HTML nodes, or PDF text lines. v83 already validates all four markers independently
    in normalized Markdown, visible HTML, and extracted PDF text and rejects opposite-
    language structure. If that stronger gate succeeds, the historical raw-string
    ``client report omitted CI/CD boundary`` exception is necessarily a formatting
    false positive and may not block publication. Every other legacy truth check still
    runs and every other exception still fails closed.
    """

    validation = _validate_authoritative_ci_surfaces(result)
    try:
        current_validate(result)
    except ValueError as exc:
        if not _normalize(exc).startswith(_LEGACY_RAW_CI_BOUNDARY_PREFIX):
            raise
    return validation


def _patch_terminal_consumers() -> dict[str, bool]:
    """Rebind the exact final producers/validators after every late bootstrap installer."""

    from nico import client_report_completion_v1 as legacy_completion
    from nico import comprehensive_ci_boundary_compat_v74 as ci_boundary
    from nico import comprehensive_ci_operational_truth_v71 as ci_truth
    from nico import comprehensive_client_truth_final_v1 as final_truth
    from nico import comprehensive_review_candidate_publication_v75 as publication
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    from nico import v2_report_quality_repairs as quality

    setattr(_is_spanish, _FUNCTION_MARKER, True)
    setattr(_is_spanish_with_override, _FUNCTION_MARKER, True)
    setattr(_ci_boundary_markers, _FUNCTION_MARKER, True)
    setattr(_ci_lines, _FUNCTION_MARKER, True)

    final_truth._report_language = _authoritative_language
    final_truth._ci_boundary_markers = _ci_boundary_markers
    final_truth._ci_lines = _ci_lines
    legacy_completion._is_spanish = _is_spanish
    ci_boundary._is_spanish = _is_spanish_with_override
    ci_truth._is_spanish = _is_spanish_with_override
    publication._is_spanish = _is_spanish_with_override
    phase17._is_spanish = _is_spanish
    quality._is_spanish = _is_spanish

    current_validate = final_truth._validate_surfaces
    if not getattr(current_validate, _VALIDATOR_MARKER, False):

        @wraps(current_validate)
        def _validate_surfaces(result: Mapping[str, Any]) -> None:
            _validate_with_legacy_ci_compat(current_validate, result)

        setattr(_validate_surfaces, _VALIDATOR_MARKER, True)
        setattr(_validate_surfaces, "_nico_previous", current_validate)
        final_truth._validate_surfaces = _validate_surfaces

    return {
        "final_truth_language_bound": final_truth._report_language is _authoritative_language,
        "final_truth_ci_markers_bound": final_truth._ci_boundary_markers is _ci_boundary_markers,
        "final_truth_ci_lines_bound": final_truth._ci_lines is _ci_lines,
        "legacy_completion_language_bound": legacy_completion._is_spanish is _is_spanish,
        "ci_boundary_language_bound": ci_boundary._is_spanish is _is_spanish_with_override,
        "ci_truth_language_bound": ci_truth._is_spanish is _is_spanish_with_override,
        "publication_language_bound": publication._is_spanish is _is_spanish_with_override,
        "phase17_language_bound": phase17._is_spanish is _is_spanish,
        "quality_language_bound": quality._is_spanish is _is_spanish,
        "final_surface_validator_bound": getattr(
            final_truth._validate_surfaces,
            _VALIDATOR_MARKER,
            False,
        ),
    }


def _assert_terminal_authority() -> dict[str, Any]:
    from nico import comprehensive_client_truth_final_v1 as final_truth
    from nico import comprehensive_report_language_truth_v77 as language

    probe = {
        "report_language": "en",
        "locale": "en",
        "identity": {
            "run_id": "comprun_terminal_language_probe",
            "report_language": "es-MX",
        },
        "assessment": {
            "report_language": "en",
            "locale": "en",
            "sections": [],
        },
    }
    resolved = language.resolve_report_language(probe)
    final_resolved = final_truth._report_language(probe)
    markers = final_truth._ci_boundary_markers(probe)
    lines = final_truth._ci_lines(probe)
    if resolved != "es-MX" or final_resolved != "es-MX":
        raise RuntimeError(
            "terminal Comprehensive report-language authority does not preserve persisted es-MX"
        )
    if not markers or markers[0] != language._ES_BOUNDARY_MARKERS[0]:
        raise RuntimeError("terminal CI/CD marker authority is not Spanish for persisted es-MX")
    if not lines or not lines[0].startswith(language._ES_BOUNDARY_MARKERS[0]):
        raise RuntimeError("terminal CI/CD producer is not Spanish for persisted es-MX")
    return {
        "stale_root_english_probe_resolves_es_MX": True,
        "final_truth_resolves_es_MX": True,
        "spanish_ci_boundary_selected": True,
    }


def install_comprehensive_terminal_report_language_authority_v83() -> dict[str, Any]:
    """Establish final report language authority after all production bootstrap wrappers."""

    shared_bound = _patch_shared_language_authority()
    consumers = _patch_terminal_consumers()
    probe = _assert_terminal_authority()
    if not shared_bound or not all(consumers.values()):
        raise RuntimeError(
            "terminal Comprehensive report-language authority did not bind every final consumer"
        )
    return {
        "status": "installed",
        "version": VERSION,
        "shared_v77_resolver_is_authority": True,
        "persisted_run_identity_outranks_root_projection": True,
        "rendered_output_is_not_language_authority": True,
        "independent_markdown_html_pdf_validation": True,
        "mixed_language_structural_markers_fail_closed": True,
        **consumers,
        **probe,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_terminal_report_language_authority_v83",
]
