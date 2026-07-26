from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico import comprehensive_native_providers as providers
from nico import comprehensive_report_package as base_report

VERSION = "nico.accepted_edition_report_identity.v1"
_MARKER = "__nico_accepted_edition_report_identity_v1__"


def wrap_report_builder_with_accepted_edition_identity(
    delegate: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        identity = kwargs.get("identity") if isinstance(kwargs.get("identity"), dict) else {}
        package = result.get("report_package")
        if not isinstance(package, dict):
            return result
        canonical = package.get("json")
        if not isinstance(canonical, dict):
            return result
        canonical_identity = canonical.get("identity")
        if not isinstance(canonical_identity, dict):
            canonical_identity = {}
            canonical["identity"] = canonical_identity
        canonical_identity["report_language"] = str(identity.get("report_language") or "").strip()
        canonical_identity["assessment_depth"] = str(identity.get("assessment_depth") or "").strip()
        missing = [
            field
            for field in ("report_language", "assessment_depth")
            if not canonical_identity.get(field)
        ]
        truth_sha = base_report._canonical_hash(canonical)
        package["canonical_truth_sha256"] = truth_sha
        result["canonical_truth_sha256"] = truth_sha
        quality = package.get("report_quality_contract")
        if not isinstance(quality, dict):
            quality = package.get("quality") if isinstance(package.get("quality"), dict) else {}
        quality.update(
            {
                "accepted_edition_report_identity_version": VERSION,
                "report_language_bound": "report_language" not in missing,
                "assessment_depth_bound": "assessment_depth" not in missing,
                "accepted_edition_identity_complete": not missing,
                "client_delivery_allowed": False,
            }
        )
        package["report_quality_contract"] = quality
        package["quality"] = quality
        result["report_quality_contract"] = quality
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        return result

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_accepted_edition_report_identity() -> dict[str, Any]:
    current = providers.build_comprehensive_report_package
    wrapped = wrap_report_builder_with_accepted_edition_identity(current)
    providers.build_comprehensive_report_package = wrapped
    return {
        "artifact_schema": VERSION,
        "status": "installed" if wrapped is not current else "already_installed",
        "bound": providers.build_comprehensive_report_package is wrapped,
        "report_language_required": True,
        "assessment_depth_required": True,
        "report_regeneration_during_review_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_accepted_edition_report_identity",
    "wrap_report_builder_with_accepted_edition_identity",
]
