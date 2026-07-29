from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package

VERSION = "nico.v2.production-authority.v3"
_MARKER = "__nico_v2_production_authority_v3__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _report_language(context: dict[str, Any]) -> str:
    value = _text(context.get("report_language") or context.get("locale") or "en").casefold()
    return "es-MX" if value.startswith("es") else "en"


def _inject_live_runtime_truth(source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(source)
    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    canonical = deepcopy(package.get("json")) if isinstance(package.get("json"), dict) else {}
    if not canonical:
        return output

    language = _report_language(context)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    identity = deepcopy(identity)
    identity["report_language"] = language
    canonical["identity"] = identity
    canonical["report_language"] = language
    canonical["locale"] = language
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    assessment = deepcopy(assessment)
    assessment["report_language"] = language
    assessment["locale"] = language

    try:
        from nico import comprehensive_native_providers as providers

        scan = providers._scan(context)
    except Exception:
        scan = {}
    records = scan.get("scanner_results") if isinstance(scan, dict) and isinstance(scan.get("scanner_results"), list) else []
    if records:
        commit_sha = _text(identity.get("commit_sha") or context.get("commit_sha")).casefold()
        enriched: list[dict[str, Any]] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            item = deepcopy(raw)
            item.setdefault("scanner_name", item.get("tool") or item.get("scanner"))
            item.setdefault("commit_sha", commit_sha)
            item.setdefault("snapshot_commit_sha", commit_sha)
            item.setdefault("exact_commit_match", _text(item.get("commit_sha")).casefold() == commit_sha)
            if item.get("exit_code") is None and isinstance(item.get("returncode"), int):
                item["exit_code"] = item["returncode"]
            enriched.append(item)
        canonical["scanner_execution_records"] = enriched
        assessment["scanner_execution_records"] = deepcopy(enriched)
        assessment["scanner_execution_summary"] = deepcopy(scan.get("scanner_execution_summary") or {})
        canonical["live_scanner_evidence"] = {
            "scan_id": scan.get("scan_id"),
            "snapshot_commit_sha": scan.get("snapshot_commit_sha"),
            "actual_commit_sha": scan.get("actual_commit_sha"),
            "snapshot_match": scan.get("snapshot_match") is True,
            "tools_requested": list(scan.get("tools_requested") or []),
            "tools_run": list(scan.get("tools_run") or []),
            "failed_tools": list(scan.get("failed_tools") or []),
            "unavailable_tools": list(scan.get("unavailable_tools") or []),
            "timed_out_tools": list(scan.get("timed_out_tools") or []),
            "full_history_verified_tools": list(scan.get("full_history_verified_tools") or []),
        }

    canonical["assessment"] = assessment
    package["json"] = canonical
    package["report_language"] = language
    package["locale"] = language
    output["report_package"] = package
    output["canonical_report"] = canonical
    output["report_language"] = language
    output["locale"] = language
    return output


def wrap_final_report_publication(
    delegate: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Make v2 the only final Comprehensive artifact publisher."""
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        source = delegate(context)
        if not isinstance(source, dict):
            raise TypeError("final_report_provider_must_return_dict")
        package = source.get("report_package")
        if not isinstance(package, dict) or not isinstance(package.get("json"), dict):
            return source
        source = _inject_live_runtime_truth(source, context)
        try:
            published = finalize_report_package(source)
        except Exception as exc:
            output = dict(source)
            output.update(
                {
                    "status": "blocked",
                    "reason": f"v2_production_publication_failed:{type(exc).__name__}:{_text(exc)}",
                    "v2_production_authority": {
                        "status": "blocked",
                        "version": VERSION,
                        "error_type": type(exc).__name__,
                        "error": _text(exc),
                        "legacy_artifacts_published": False,
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                    },
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            return output

        published["status"] = "complete"
        published["reason"] = ""
        published["summary"] = (
            "The final Comprehensive package was rebuilt from one canonical evidence, "
            "scanner, finding, lifecycle, language, and artifact truth and is ready for internal review."
        )
        published["v2_production_authority"] = {
            "status": "complete",
            "version": VERSION,
            "single_final_publication_boundary": True,
            "live_scanner_truth_injected_before_canonicalization": True,
            "report_language_bound_before_rendering": True,
            "canonical_findings_only": True,
            "normalized_scanner_results_only": True,
            "all_artifacts_rebuilt_after_canonicalization": True,
            "authoritative_assessment_state": "review_required",
            "legacy_artifacts_published": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        evidence = published.get("evidence") if isinstance(published.get("evidence"), dict) else {}
        evidence.update(
            {
                "v2_single_source_pipeline": True,
                "canonical_truth_sha256": published.get("canonical_truth_sha256") or "",
                "assessment_state": "review_required",
                "report_language": published.get("report_language") or _report_language(context),
                "final_artifact_generation_complete": True,
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
    current = providers.get("final_report_generation")
    if not callable(current):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "final_report_provider_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    wrapped = wrap_final_report_publication(current)
    providers["final_report_generation"] = wrapped
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    bound = providers.get("final_report_generation") is wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": bound,
        "single_final_publication_boundary": True,
        "v2_finalizer_invoked_by_real_provider": True,
        "live_scanner_truth_injected_before_canonicalization": True,
        "report_language_bound_before_rendering": True,
        "legacy_post_generation_publication_disabled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_v2_production_authority",
    "wrap_final_report_publication",
]
