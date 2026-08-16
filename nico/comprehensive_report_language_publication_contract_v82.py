from __future__ import annotations

import base64
from collections.abc import Mapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_report_language_truth_v77 as language_v77

VERSION = "nico.comprehensive-report-language-publication-contract.v82"
_RUN_RECORD_MARKER = "_nico_report_language_run_record_v82"
_SOURCE_MARKER = "_nico_report_language_canonical_source_v82"
_COMPLETION_VALIDATOR_MARKER = "_nico_report_language_completion_validator_v82"


def _canonical_language(value: Any, *, default: str = "") -> str:
    resolved = language_v77._language_from_value(value)
    if resolved:
        return resolved
    if default:
        return default
    raise ValueError(f"unsupported_report_language:{value}")


def _context_language(context: Mapping[str, Any]) -> str:
    identity = context.get("identity") if isinstance(context.get("identity"), Mapping) else {}
    for value in (
        identity.get("report_language"),
        identity.get("locale"),
        context.get("requested_report_language"),
        context.get("report_language"),
        context.get("locale"),
    ):
        resolved = language_v77._language_from_value(value)
        if resolved:
            return resolved
    # Compatibility callers that never had a language contract historically render
    # English. Production Comprehensive stage contexts always carry report_language.
    return "en"


def _bind_language_to_source(
    result: Mapping[str, Any],
    *,
    language: str,
) -> dict[str, Any]:
    output = deepcopy(dict(result))
    package = output.get("report_package")
    package = deepcopy(dict(package)) if isinstance(package, Mapping) else {}
    canonical = package.get("json")
    canonical = deepcopy(dict(canonical)) if isinstance(canonical, Mapping) else {}
    if not canonical:
        return output

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    identity = deepcopy(dict(identity))
    identity["report_language"] = language
    canonical["identity"] = identity
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["report_language"] = language
    assessment["locale"] = language
    canonical["assessment"] = assessment
    canonical["report_language"] = language
    canonical["locale"] = language

    package["json"] = canonical
    package["report_language"] = language
    package["locale"] = language
    output["report_package"] = package
    output["canonical_report"] = canonical
    output["report_language"] = language
    output["locale"] = language
    return output


def _patch_run_record_language() -> bool:
    from nico import comprehensive_run_record as run_record
    from nico import comprehensive_run_service as run_service

    current = run_record.create_comprehensive_run_record
    if getattr(current, _RUN_RECORD_MARKER, False):
        run_service.create_comprehensive_run_record = current
        return True

    @wraps(current)
    def create_comprehensive_run_record(*args: Any, **kwargs: Any) -> dict[str, Any]:
        normalized = dict(kwargs)
        normalized["report_language"] = _canonical_language(
            normalized.get("report_language", "en"),
            default="en",
        )
        return current(*args, **normalized)

    setattr(create_comprehensive_run_record, _RUN_RECORD_MARKER, True)
    setattr(create_comprehensive_run_record, "_nico_previous", current)
    run_record.create_comprehensive_run_record = create_comprehensive_run_record
    # comprehensive_run_service imported this callable by value at module import.
    run_service.create_comprehensive_run_record = create_comprehensive_run_record
    return (
        run_record.create_comprehensive_run_record is create_comprehensive_run_record
        and run_service.create_comprehensive_run_record is create_comprehensive_run_record
    )


def _patch_canonical_source_language() -> bool:
    from nico import comprehensive_canonical_report_source_v1 as source
    from nico import v2_production_authority as production

    current: Callable[[Mapping[str, Any]], dict[str, Any]] = source.build_canonical_report_source
    if getattr(current, _SOURCE_MARKER, False):
        production.build_canonical_report_source = current
        return True

    @wraps(current)
    def build_canonical_report_source(context: Mapping[str, Any]) -> dict[str, Any]:
        language = _context_language(context)
        return _bind_language_to_source(current(context), language=language)

    setattr(build_canonical_report_source, _SOURCE_MARKER, True)
    setattr(build_canonical_report_source, "_nico_previous", current)
    source.build_canonical_report_source = build_canonical_report_source
    # v2_production_authority also captured the builder through a static import.
    production.build_canonical_report_source = build_canonical_report_source
    return (
        source.build_canonical_report_source is build_canonical_report_source
        and production.build_canonical_report_source is build_canonical_report_source
    )


def _patch_production_language_resolver() -> bool:
    from nico import v2_production_authority as production

    def _report_language(context: Mapping[str, Any]) -> str:
        return _context_language(context)

    production._report_language = _report_language
    return production._report_language is _report_language


def _patch_static_renderer_language_aliases() -> bool:
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    from nico import v2_report_quality_repairs as quality

    def _is_spanish(canonical: Mapping[str, Any]) -> bool:
        return language_v77.resolve_report_language(canonical) == "es-MX"

    quality._is_spanish = _is_spanish
    # phase17 imported _is_spanish statically, so rebind that execution-time alias too.
    phase17._is_spanish = _is_spanish
    return phase17._is_spanish is _is_spanish and quality._is_spanish is _is_spanish


def _patch_completion_surface_validator() -> bool:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_rendered_ci_boundary_truth_v78 as rendered_truth

    current = completion._validate_final_surfaces
    if getattr(current, _COMPLETION_VALIDATOR_MARKER, False):
        return True

    @wraps(current)
    def _validate_final_surfaces(
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> dict[str, Any]:
        language = language_v77.resolve_report_language(canonical)
        rendered_truth._validate_authoritative_surfaces(
            {
                "json": canonical,
                "markdown": markdown,
                "html": rendered_html,
                "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            },
            language=language,
        )
        result = current(canonical, register, markdown, rendered_html, pdf)
        return {
            **result,
            "authoritative_report_language": language,
            "ci_cd_surfaces_validated_independently": True,
            "mixed_language_structural_markers_rejected": True,
        }

    setattr(_validate_final_surfaces, _COMPLETION_VALIDATOR_MARKER, True)
    setattr(_validate_final_surfaces, "_nico_previous", current)
    completion._validate_final_surfaces = _validate_final_surfaces
    return completion._validate_final_surfaces is _validate_final_surfaces


def install_comprehensive_report_language_publication_contract_v82() -> dict[str, Any]:
    """Make persisted run language authoritative from creation through publication."""

    run_record_bound = _patch_run_record_language()
    canonical_source_bound = _patch_canonical_source_language()
    production_resolver_bound = _patch_production_language_resolver()
    static_renderer_aliases_bound = _patch_static_renderer_language_aliases()
    completion_validator_bound = _patch_completion_surface_validator()
    return {
        "status": "installed",
        "version": VERSION,
        "run_record_language_canonicalized": run_record_bound,
        "canonical_source_language_bound": canonical_source_bound,
        "production_language_resolver_bound": production_resolver_bound,
        "static_renderer_language_aliases_bound": static_renderer_aliases_bound,
        "completion_surface_validator_bound": completion_validator_bound,
        "authoritative_languages": ["en", "es-MX"],
        "persisted_run_identity_is_authority": True,
        "rendered_output_is_not_language_authority": True,
        "independent_markdown_html_pdf_validation": True,
        "mixed_language_structural_markers_fail_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_language_publication_contract_v82",
]
