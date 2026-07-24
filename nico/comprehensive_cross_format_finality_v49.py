from __future__ import annotations

import base64
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_cross_format_finality.v49"
_PATCH_MARKER = "_nico_comprehensive_cross_format_finality_v49"


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
        "service_id_is_comprehensive": package.get("service_id") == "comprehensive",
        "report_finality_is_final": package.get("report_finality") == "final",
        "approval_is_pending_human_review": package.get("approval_status") == "pending_human_approval",
        "delivery_status_is_blocked": package.get("delivery_status") == "blocked_pending_human_approval",
        "human_review_required": package.get("human_review_required") is True,
        "client_delivery_disallowed": package.get("client_delivery_allowed") is False,
    }


def finality_aware_cross_format_verification_provider(context: dict[str, Any]) -> dict[str, Any]:
    """Verify the current final-report contract rather than obsolete draft text.

    PR #770 intentionally changed ``CLIENT DELIVERY NOT AUTHORIZED`` into the
    final-report boundary ``CLIENT DELIVERY BLOCKED PENDING HUMAN APPROVAL``. The
    previous verifier still required the removed legacy phrase and therefore blocked
    every otherwise complete Comprehensive production run at 86.96 percent.
    """

    from nico import comprehensive_native_providers as providers

    final_stage = providers._prior(context, "final_comprehensive_report_generation")
    package = final_stage.get("report_package") if isinstance(final_stage.get("report_package"), dict) else {}
    checks = _required_checks(context, package)
    failed_checks = sorted(name for name, passed in checks.items() if passed is not True)
    payload = {
        "checks": checks,
        "failed_checks": failed_checks,
        "cross_format_contract_schema": VERSION,
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
            "pdf_sha256": __import__("hashlib").sha256(pdf).hexdigest(),
            "canonical_truth_sha256": package.get("canonical_truth_sha256"),
        },
    )


def install_comprehensive_cross_format_finality_v49() -> dict[str, Any]:
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
