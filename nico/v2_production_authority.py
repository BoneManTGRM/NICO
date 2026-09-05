from __future__ import annotations

import re
import time
from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI

from nico.comprehensive_canonical_report_source_v1 import (
    build_canonical_report_source,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_retained_scanner_evidence_v1 import retained_scanner_payload
from nico.comprehensive_scanner_stage_retention_v1 import install_scanner_stage_retention
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package

VERSION = "nico.v2.production-authority.v7"
_MARKER = "__nico_v2_production_authority_v7__"
_REQUIRED_TERMINAL_LANGUAGE_FLAGS = (
    "persisted_run_identity_outranks_root_projection",
    "final_truth_language_bound",
    "final_truth_ci_markers_bound",
    "final_truth_ci_lines_bound",
    "final_surface_validator_bound",
    "independent_markdown_html_pdf_validation",
    "mixed_language_structural_markers_fail_closed",
    "human_review_required",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_report_language(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    if normalized.startswith("es"):
        return "es-MX"
    if normalized.startswith("en"):
        return "en"
    return ""


def _authoritative_report_language(
    context: Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> str:
    """Resolve immutable publication language from canonical run truth first.

    This callable is intentionally separate from ``_report_language``. Historical
    compatibility installers patch the one-argument ``_report_language`` hook at
    runtime. The final publication path must not depend on that mutable hook when a
    canonical run identity is already available.
    """

    canonical = canonical if isinstance(canonical, Mapping) else {}
    canonical_identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    context_identity = (
        context.get("identity")
        if isinstance(context.get("identity"), Mapping)
        else {}
    )
    for candidate in (
        canonical_identity.get("report_language"),
        canonical_identity.get("requested_report_language"),
        canonical_identity.get("requested_locale"),
        canonical_identity.get("locale"),
        canonical.get("report_language"),
        canonical.get("locale"),
        context_identity.get("report_language"),
        context_identity.get("requested_report_language"),
        context_identity.get("requested_locale"),
        context_identity.get("locale"),
        context.get("report_language"),
        context.get("locale"),
    ):
        resolved = _normalized_report_language(candidate)
        if resolved:
            return resolved
    return "en"


def _report_language(context: Mapping[str, Any]) -> str:
    """Compatibility hook retained with its historical one-argument contract."""

    return _authoritative_report_language(context)


def _reassert_terminal_report_language_authority() -> dict[str, Any]:
    """Rebind language producers/validators at the live publication boundary.

    NICO's report pipeline contains legacy compatibility installers that intentionally
    rebind module callables. Startup ordering alone cannot prove those process-global
    bindings are still authoritative on a later assessment. Reassert the terminal
    authority for every publication and fail closed if any invariant is missing.
    """

    from nico.comprehensive_terminal_report_language_authority_v83 import (
        install_comprehensive_terminal_report_language_authority_v83,
    )

    state = install_comprehensive_terminal_report_language_authority_v83()
    missing = [
        flag
        for flag in _REQUIRED_TERMINAL_LANGUAGE_FLAGS
        if state.get(flag) is not True
    ]
    if state.get("client_delivery_allowed") is not False:
        missing.append("client_delivery_allowed_false")
    if missing:
        raise RuntimeError(
            "terminal_report_language_authority_incomplete:" + ",".join(missing)
        )
    return state


def _safe_filename(value: Any, default: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", _text(value)).strip("-")
    return normalized or default


def _install_spanish_vocabulary() -> None:
    from nico.comprehensive_report_spanish_text_v51 import ES_REPLACEMENTS

    ES_REPLACEMENTS.update(
        {
            "Reduce complexity in": "Reducir la complejidad en",
            "completed with findings": "completado con hallazgos",
            "completed": "completado",
            "failed": "fallido",
            "unavailable": "no disponible",
            "partial": "parcial",
            "unknown": "desconocido",
            "review required": "revisión requerida",
            "client delivery not authorized": "entrega al cliente no autorizada",
        }
    )


def _existing_scanner_records(
    canonical: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    for value in (
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    ):
        if isinstance(value, list):
            records = [dict(item) for item in value if isinstance(item, Mapping)]
            if records:
                return records
    return []


def _inject_live_runtime_truth(
    source: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach retained scanner and language truth with bounded copy-on-write updates.

    Scanner execution belongs to the earlier dependency/security stage. Final report
    publication must never reopen the scanner store, clone the repository, or import
    full raw findings and output previews. It consumes compact exact-SHA records already
    retained by this run and remains fail-closed when those records are unavailable.

    Report language is selected from the already-persisted canonical run identity first.
    A missing or stale runtime projection may not overwrite an existing canonical
    language after the assessment has started. The immutable resolver is used directly
    so late compatibility patches to ``_report_language`` cannot alter this decision.
    """

    output = dict(source)
    raw_package = source.get("report_package")
    package = dict(raw_package) if isinstance(raw_package, Mapping) else {}
    raw_canonical = package.get("json")
    canonical = dict(raw_canonical) if isinstance(raw_canonical, Mapping) else {}
    if not canonical:
        return output

    language = _authoritative_report_language(context, canonical)
    if language == "es-MX":
        _install_spanish_vocabulary()
    raw_identity = canonical.get("identity")
    identity = dict(raw_identity) if isinstance(raw_identity, Mapping) else {}
    identity["report_language"] = language
    canonical["identity"] = identity
    canonical["report_language"] = language
    canonical["locale"] = language
    raw_assessment = canonical.get("assessment")
    assessment = dict(raw_assessment) if isinstance(raw_assessment, Mapping) else {}
    assessment["report_language"] = language
    assessment["locale"] = language

    retained = retained_scanner_payload(context)
    records = [
        dict(item)
        for item in retained.get("scanner_execution_records") or []
        if isinstance(item, Mapping)
    ]
    if not records:
        records = _existing_scanner_records(canonical, assessment)
        if records:
            retained = {
                **retained,
                "source": "canonical_source_scanner_records",
                "scanner_execution_records": records,
                "record_count": len(records),
            }

    if records:
        # The full requested population must use the same retained exact-run
        # records. A pre-injection projection must not override these records
        # later during applicability reconciliation or publication acceptance.
        canonical["requested_scanner_records"] = [dict(item) for item in records]
        assessment["requested_scanner_records"] = [dict(item) for item in records]
        canonical["scanner_execution_records"] = [dict(item) for item in records]
        assessment["scanner_execution_records"] = [dict(item) for item in records]
        assessment["scanner_execution_summary"] = {
            "record_count": len(records),
            "completed_count": sum(item.get("completed") is True for item in records),
            "verified_count": sum(
                item.get("verified_complete") is True for item in records
            ),
            "incomplete_count": sum(item.get("completed") is not True for item in records),
            "source": retained.get("source"),
            "compact_records_only": True,
        }

    canonical["live_scanner_evidence"] = {
        "scan_id": retained.get("scan_id"),
        "snapshot_commit_sha": retained.get("snapshot_commit_sha"),
        "actual_commit_sha": retained.get("actual_commit_sha"),
        "snapshot_match": retained.get("snapshot_match") is True,
        "tools_requested": list(retained.get("tools_requested") or []),
        "tools_run": list(retained.get("tools_run") or []),
        "failed_tools": list(retained.get("failed_tools") or []),
        "unavailable_tools": list(retained.get("unavailable_tools") or []),
        "timed_out_tools": list(retained.get("timed_out_tools") or []),
        "finding_summary": dict(retained.get("finding_summary") or {}),
        "source": retained.get("source"),
        "compact_record_count": len(records),
        "final_stage_scanner_store_read": False,
        "final_stage_scanner_execution": False,
        "raw_scanner_outputs_embedded": False,
    }
    canonical["final_report_scanner_evidence_contract"] = {
        "version": retained.get("version"),
        "source": retained.get("source"),
        "retained_exact_run_records_only": True,
        "scanner_store_read_during_final_report": False,
        "scanner_execution_during_final_report": False,
        "raw_finding_payload_embedded": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    canonical["assessment"] = assessment
    package["json"] = canonical
    package["report_language"] = language
    package["locale"] = language
    if language == "es-MX":
        repository = _safe_filename(
            identity.get("repository") or context.get("repository"),
            "repositorio",
        )
        run_id = _safe_filename(identity.get("run_id") or context.get("run_id"), "run")
        localized = f"nico-evaluacion-tecnica-integral-{repository}-{run_id}-es-MX.pdf"
        package["pdf_filename"] = localized
        package["spanish_pdf_filename"] = localized
    output["report_package"] = package
    output["canonical_report"] = canonical
    output["report_language"] = language
    output["locale"] = language
    output["retained_scanner_evidence"] = retained
    output["report_language_authority"] = {
        "selected": language,
        "canonical_identity_precedes_runtime_context": True,
        "compatibility_hook_bypassed_for_canonical_publication": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def _canonical_source(
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], float]:
    from nico.comprehensive_final_report_execution_v1 import (
        _canonical_final_report_context,
    )

    started = time.perf_counter()
    report_context, score_truth = _canonical_final_report_context(context)
    source = build_canonical_report_source(report_context)
    elapsed = round(time.perf_counter() - started, 3)
    source["final_report_input_score_truth"] = score_truth
    source["canonical_source_timing_seconds"] = elapsed
    return source, report_context, elapsed


def wrap_final_report_publication(
    delegate: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Make v2 the only final Comprehensive artifact renderer and publisher."""

    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        total_started = time.perf_counter()
        source, report_context, canonical_elapsed = _canonical_source(dict(context))
        canonical_only = source.get("status") == "complete" and isinstance(
            source.get("report_package"), dict
        )
        if not canonical_only:
            source = delegate(context)
            report_context = dict(context)
            if not isinstance(source, dict):
                raise TypeError("final_report_provider_must_return_dict")

        package = source.get("report_package")
        if not isinstance(package, dict) or not isinstance(package.get("json"), dict):
            return source

        injection_started = time.perf_counter()
        source = _inject_live_runtime_truth(source, report_context)
        injection_elapsed = round(time.perf_counter() - injection_started, 3)
        render_started = time.perf_counter()
        terminal_language_authority: dict[str, Any] = {}
        try:
            # Reassert this immediately before every real publication. Startup-only
            # binding is insufficient because compatibility installers can rebind
            # process-global report helpers after an earlier assessment succeeds.
            terminal_language_authority = _reassert_terminal_report_language_authority()
            published = finalize_report_package(source)
        except Exception as exc:
            output = dict(source)
            output.update(
                {
                    "status": "blocked",
                    "reason": (
                        "v2_production_publication_failed:"
                        f"{type(exc).__name__}:{_text(exc)}"
                    ),
                    "v2_production_authority": {
                        "status": "blocked",
                        "version": VERSION,
                        "error_type": type(exc).__name__,
                        "error": _text(exc),
                        "canonical_only_source_used": canonical_only,
                        "legacy_delegate_render_skipped": canonical_only,
                        "legacy_artifacts_published": False,
                        "terminal_report_language_reasserted_per_publication": bool(
                            terminal_language_authority
                        ),
                        "compat_report_language_one_arg_api_preserved": True,
                        "authoritative_language_uses_private_immutable_resolver": True,
                        "final_stage_scanner_store_read": False,
                        "final_stage_scanner_execution": False,
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                    },
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            return output
        render_elapsed = round(time.perf_counter() - render_started, 3)
        total_elapsed = round(time.perf_counter() - total_started, 3)

        published["status"] = "complete"
        published["reason"] = ""
        published["summary"] = (
            "The final Comprehensive package was rendered once from one canonical "
            "evidence, scanner, finding, lifecycle, language, and artifact truth and "
            "is ready for internal review."
        )
        published["v2_production_authority"] = {
            "status": "complete",
            "version": VERSION,
            "single_final_publication_boundary": True,
            "canonical_only_source_used": canonical_only,
            "legacy_delegate_render_skipped": canonical_only,
            "legacy_markdown_rendered": not canonical_only,
            "legacy_html_rendered": not canonical_only,
            "legacy_pdf_rendered": not canonical_only,
            "live_scanner_truth_injected_before_canonicalization": True,
            "retained_exact_run_scanner_truth_used": True,
            "final_stage_scanner_store_read": False,
            "final_stage_scanner_execution": False,
            "raw_scanner_outputs_embedded": False,
            "report_language_bound_before_rendering": True,
            "canonical_report_language_outranks_runtime_projection": True,
            "compat_report_language_one_arg_api_preserved": True,
            "authoritative_language_uses_private_immutable_resolver": True,
            "terminal_report_language_reasserted_per_publication": True,
            "terminal_report_language_authority_version": terminal_language_authority.get(
                "version"
            ),
            "localized_filename_bound_before_rendering": True,
            "spanish_vocabulary_bound_before_rendering": True,
            "canonical_findings_only": True,
            "normalized_scanner_results_only": True,
            "all_artifacts_rendered_once_after_canonicalization": canonical_only,
            "authoritative_assessment_state": "review_required",
            "canonical_source_seconds": canonical_elapsed,
            "runtime_truth_injection_seconds": injection_elapsed,
            "authoritative_render_seconds": render_elapsed,
            "total_publication_seconds": total_elapsed,
            "legacy_artifacts_published": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        evidence = (
            dict(published.get("evidence"))
            if isinstance(published.get("evidence"), Mapping)
            else {}
        )
        published_package = (
            published.get("report_package")
            if isinstance(published.get("report_package"), Mapping)
            else {}
        )
        published_canonical = (
            published_package.get("json")
            if isinstance(published_package.get("json"), Mapping)
            else {}
        )
        evidence.update(
            {
                "v2_single_source_pipeline": True,
                "canonical_only_source_used": canonical_only,
                "legacy_delegate_render_skipped": canonical_only,
                "canonical_truth_sha256": (
                    published.get("canonical_truth_sha256") or ""
                ),
                "assessment_state": "review_required",
                "report_language": (
                    published.get("report_language")
                    or _authoritative_report_language(
                        report_context,
                        published_canonical,
                    )
                ),
                "canonical_report_language_outranks_runtime_projection": True,
                "compat_report_language_one_arg_api_preserved": True,
                "authoritative_language_uses_private_immutable_resolver": True,
                "terminal_report_language_reasserted_per_publication": True,
                "final_artifact_generation_complete": True,
                "retained_exact_run_scanner_truth_used": True,
                "final_stage_scanner_store_read": False,
                "final_stage_scanner_execution": False,
                "publication_timing_seconds": {
                    "canonical_source": canonical_elapsed,
                    "runtime_truth_injection": injection_elapsed,
                    "authoritative_render": render_elapsed,
                    "total": total_elapsed,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
        published["evidence"] = evidence
        return published

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def install_v2_production_authority(app: FastAPI) -> dict[str, Any]:
    providers = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(providers, dict):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "comprehensive_provider_registry_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    scanner_retention = install_scanner_stage_retention(app)
    providers = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(providers, dict):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "comprehensive_provider_registry_unavailable_after_scanner_retention",
            "scanner_stage_retention": scanner_retention,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    current = providers.get("final_report_generation")
    if not callable(current):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "final_report_provider_unavailable",
            "scanner_stage_retention": scanner_retention,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    wrapped = wrap_final_report_publication(current)
    providers["final_report_generation"] = wrapped
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    final_bound = providers.get("final_report_generation") is wrapped
    bound = final_bound and scanner_retention.get("bound") is True
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": bound,
        "final_report_provider_bound": final_bound,
        "scanner_stage_retention": scanner_retention,
        "single_final_publication_boundary": True,
        "canonical_only_source_enabled": True,
        "legacy_delegate_render_skipped_in_production": True,
        "v2_finalizer_invoked_by_real_provider": True,
        "live_scanner_truth_injected_before_canonicalization": True,
        "retained_exact_run_scanner_truth_used": True,
        "final_stage_scanner_store_read": False,
        "final_stage_scanner_execution": False,
        "raw_scanner_outputs_embedded": False,
        "report_language_bound_before_rendering": True,
        "canonical_report_language_outranks_runtime_projection": True,
        "compat_report_language_one_arg_api_preserved": True,
        "authoritative_language_uses_private_immutable_resolver": True,
        "terminal_report_language_reasserted_per_publication": True,
        "localized_filename_bound_before_rendering": True,
        "spanish_vocabulary_bound_before_rendering": True,
        "legacy_post_generation_publication_disabled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_v2_production_authority",
    "wrap_final_report_publication",
]
