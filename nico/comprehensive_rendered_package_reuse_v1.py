from __future__ import annotations

import base64
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-rendered-package-reuse.v1.1"
_MARKER = "__nico_comprehensive_rendered_package_reuse_v1__"


def _has_bound_rendered_surfaces(package: Mapping[str, Any]) -> bool:
    canonical = package.get("json")
    if not isinstance(canonical, Mapping):
        return False
    if not str(package.get("markdown") or "").strip():
        return False
    if not str(package.get("html") or "").strip():
        return False
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception:
        return False
    if not pdf.startswith(b"%PDF"):
        return False

    renderer = (
        package.get("premium_report_renderer")
        if isinstance(package.get("premium_report_renderer"), Mapping)
        else {}
    )
    phase17 = (
        package.get("phase17_artifact_rebuild")
        if isinstance(package.get("phase17_artifact_rebuild"), Mapping)
        else {}
    )
    # Empty compatibility dictionaries are not proof that rendering completed.
    # Skip the legacy renderer only after the single-pass compiler records an
    # explicit finished-render marker. Otherwise legacy completion must still
    # install the canonical register and provenance surfaces.
    return bool(
        renderer.get("single_pass_renderer") is True
        or phase17.get("single_review_pdf_generation") is True
    )


def install_comprehensive_rendered_package_reuse_v1() -> dict[str, Any]:
    """Prevent the legacy completion layer from replacing a finished renderer.

    Phase 17 already produces canonical Markdown, HTML, and PDF bytes before the
    completion layer adds the review worksheets, compact register, and approval
    gate. Calling the legacy renderer again at that point reintroduced an older
    cover and stale lifecycle language. Reuse only a complete rendered package;
    unrendered inputs continue through the legacy compatibility path.
    """

    from nico import client_report_completion_v2 as completion

    current = completion.legacy.finalize_client_report_package
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
        if _has_bound_rendered_surfaces(package):
            result = deepcopy(dict(package))
            contract = deepcopy(dict(result.get("client_report_completion") or {}))
            contract.update(
                {
                    "rendered_package_reuse_version": VERSION,
                    "legacy_rerender_skipped": True,
                    "canonical_rendered_bytes_preserved": True,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            result["client_report_completion"] = contract
            return result
        return current(package)

    setattr(finalize_client_report_package, _MARKER, True)
    setattr(finalize_client_report_package, "_nico_previous", current)
    completion.legacy.finalize_client_report_package = finalize_client_report_package
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_rerender_skipped_for_complete_package": True,
        "unrendered_compatibility_path_preserved": True,
        "canonical_rendered_bytes_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_rendered_package_reuse_v1",
]
