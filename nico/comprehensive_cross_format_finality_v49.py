from __future__ import annotations

import base64
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_cross_format_finality.v50"
_PATCH_MARKER = "_nico_comprehensive_cross_format_finality_v50"
_PACKAGE_KEYS = (
    "report_package",
    "reports",
    "report",
    "final_report",
    "final_package",
    "artifacts",
    "output",
    "result",
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split())


def _delivery_boundary_present(markdown: str) -> bool:
    """Accept the current final-report boundary without reviving stale draft wording."""

    upper = _normalized(markdown).upper()
    blocked = any(
        phrase in upper
        for phrase in (
            "CLIENT DELIVERY BLOCKED",
            "CLIENT DELIVERY IS BLOCKED",
            "CLIENT DELIVERY NOT AUTHORIZED",
        )
    )
    pending_approval = "PENDING HUMAN APPROVAL" in upper
    return blocked and pending_approval


def _identity_present(markdown: str, identity: dict[str, str]) -> bool:
    normalized = _normalized(markdown)
    return all(
        value in normalized
        for value in (
            identity["run_id"],
            identity["repository"],
            identity["commit_sha"],
        )
    )


def _looks_like_report_package(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        str(value.get("markdown") or "").strip()
        and str(value.get("html") or "").strip()
        and str(value.get("pdf_base64") or "").strip()
    )


def _report_package(final_stage: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Resolve the generated package from supported stage-envelope shapes.

    Final-report execution wrappers may retain the package directly or beneath one
    bounded result/artifact envelope. Cross-format verification must inspect the exact
    generated package instead of treating an envelope-shape change as missing output.
    """

    if _looks_like_report_package(final_stage):
        return final_stage, "stage"

    queue: list[tuple[dict[str, Any], str, int]] = [(final_stage, "stage", 0)]
    visited: set[int] = set()
    while queue:
        current, source, depth = queue.pop(0)
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        if depth >= 3:
            continue
        for key in _PACKAGE_KEYS:
            candidate = current.get(key)
            if not isinstance(candidate, dict):
                continue
            candidate_source = f"{source}.{key}"
            if _looks_like_report_package(candidate):
                return candidate, candidate_source
            queue.append((candidate, candidate_source, depth + 1))
    return {}, "unresolved"


def _semantic_value(package: dict[str, Any], key: str) -> Any:
    """Read finality metadata from the package or its canonical JSON truth."""

    direct = package.get(key)
    if direct is not None:
        return direct
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    canonical_value = canonical.get(key)
    if canonical_value is not None:
        return canonical_value
    quality = package.get("report_quality_contract")
    if isinstance(quality, dict) and quality.get(key) is not None:
        return quality.get(key)
    return None


def _required_checks(context: dict[str, Any], package: dict[str, Any]) -> dict[str, bool]:
    from nico import comprehensive_native_providers as providers

    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")
    try:
        pdf = base64.b64decode(encoded_pdf, validate=True) if encoded_pdf else b""
    except Exception:
        pdf = b""

    identity = providers._identity(context)
    return {
        "markdown_available": bool(markdown),
        "html_available": bool(rendered_html),
        "pdf_available": pdf.startswith(b"%PDF"),
        "identity_present_in_markdown": _identity_present(markdown, identity),
        "final_delivery_boundary_present_in_markdown": _delivery_boundary_present(markdown),
        "service_id_is_comprehensive": _semantic_value(package, "service_id") == "comprehensive",
        "report_finality_is_final": _semantic_value(package, "report_finality") == "final",
        "approval_is_pending_human_review": _semantic_value(package, "approval_status") == "pending_human_approval",
        "delivery_status_is_blocked": _semantic_value(package, "delivery_status") == "blocked_pending_human_approval",
        "human_review_required": _semantic_value(package, "human_review_required") is True,
        "client_delivery_disallowed": _semantic_value(package, "client_delivery_allowed") is False,
    }


def finality_aware_cross_format_verification_provider(context: dict[str, Any]) -> dict[str, Any]:
    """Verify the exact generated final package and keep delivery fail-closed."""

    from nico import comprehensive_native_providers as providers

    final_stage = providers._prior(context, "final_comprehensive_report_generation")
    package, package_source = _report_package(final_stage)
    checks = _required_checks(context, package)
    failed_checks = sorted(name for name, passed in checks.items() if passed is not True)
    payload = {
        "checks": checks,
        "failed_checks": failed_checks,
        "cross_format_contract_schema": VERSION,
        "report_package_source": package_source,
        "required_finality": "final",
        "required_approval_status": "pending_human_approval",
        "required_delivery_status": "blocked_pending_human_approval",
    }

    if failed_checks:
        return providers._result(
            context,
            "blocked",
            reason="cross_format_final_report_verification_failed",
            **payload,
        )

    encoded_pdf = str(package.get("pdf_base64") or "")
    pdf = base64.b64decode(encoded_pdf, validate=True)
    return providers._result(
        context,
        summary=(
            "Markdown, HTML, and PDF artifacts passed immutable identity, final-report "
            "status, pending-human-approval, and blocked-delivery verification."
        ),
        **payload,
        evidence={
            **checks,
            "report_package_source": package_source,
            "pdf_sha256": __import__("hashlib").sha256(pdf).hexdigest(),
            "canonical_truth_sha256": package.get("canonical_truth_sha256"),
        },
    )


def install_comprehensive_cross_format_finality_v49() -> dict[str, Any]:
    """Retain the public installer name while installing the corrected v50 contract."""

    from nico import comprehensive_native_providers as providers

    current: Callable[[dict[str, Any]], dict[str, Any]] = providers.cross_format_verification_provider
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "legacy_draft_phrase_required": False,
        }

    @wraps(current)
    def verify(context: dict[str, Any]) -> dict[str, Any]:
        return finality_aware_cross_format_verification_provider(context)

    setattr(verify, _PATCH_MARKER, True)
    setattr(verify, "_nico_previous", current)
    providers.cross_format_verification_provider = verify
    return {
        "status": "installed",
        "version": VERSION,
        "bound": providers.cross_format_verification_provider is verify,
        "legacy_draft_phrase_required": False,
        "nested_report_package_supported": True,
        "canonical_semantic_fallback_supported": True,
        "final_report_semantics_required": True,
        "failed_checks_exposed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "finality_aware_cross_format_verification_provider",
    "install_comprehensive_cross_format_finality_v49",
]
