from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package

VERSION = "nico.v2.production-authority.v1"
_MARKER = "__nico_v2_production_authority_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def wrap_final_report_publication(
    delegate: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Make v2 the only final Comprehensive artifact publisher.

    The existing provider may collect evidence and create an intermediate report,
    but the returned client package is always canonicalized, deduplicated, rendered,
    hashed, and lifecycle-bound through ``finalize_report_package`` before it can be
    persisted as the completed final-report stage.
    """
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
            "scanner, finding, lifecycle, and artifact truth and is ready for internal review."
        )
        published["v2_production_authority"] = {
            "status": "complete",
            "version": VERSION,
            "single_final_publication_boundary": True,
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
        "legacy_post_generation_publication_disabled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_v2_production_authority",
    "wrap_final_report_publication",
]
