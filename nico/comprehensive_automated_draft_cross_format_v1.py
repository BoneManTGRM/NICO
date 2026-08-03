from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-automated-draft-cross-format.v1"
_CHECK_MARKER = "__nico_automated_draft_cross_format_checks_v1__"
_PROVIDER_MARKER = "__nico_automated_draft_cross_format_provider_v1__"


def install_automated_draft_cross_format_contract() -> dict[str, Any]:
    """Make cross-format verification validate a completed automated draft.

    Cross-format verification proves package integrity and score/status parity. It
    must complete before human review. Client-delivery authorization remains a
    separate, blocked approval transition and is never implied by verification.
    """

    from nico import comprehensive_cross_format_finality_v49 as cross_format
    from nico import comprehensive_native_providers as providers

    current_checks = cross_format._required_checks
    if not getattr(current_checks, _CHECK_MARKER, False):

        @wraps(current_checks)
        def checks(
            context: dict[str, Any],
            package: dict[str, Any],
            *,
            pdf: bytes,
            score_truth: dict[str, Any],
        ) -> dict[str, bool]:
            result = deepcopy(
                current_checks(
                    context,
                    package,
                    pdf=pdf,
                    score_truth=score_truth,
                )
            )
            result.pop("report_finality_is_final", None)
            result["report_finality_is_automated_draft"] = (
                cross_format._semantic_value(package, "report_finality")
                == "automated_draft"
            )
            return result

        setattr(checks, _CHECK_MARKER, True)
        setattr(checks, "_nico_previous", current_checks)
        cross_format._required_checks = checks

    current_provider: Callable[[dict[str, Any]], dict[str, Any]] = (
        cross_format.finality_aware_cross_format_verification_provider
    )
    if not getattr(current_provider, _PROVIDER_MARKER, False):

        @wraps(current_provider)
        def provider(context: dict[str, Any]) -> dict[str, Any]:
            result = deepcopy(current_provider(context))
            result["required_finality"] = "automated_draft"
            result["required_approval_status"] = "pending_human_approval"
            result["required_delivery_status"] = (
                "blocked_pending_human_approval"
            )
            if str(result.get("status") or "").casefold() not in {
                "blocked",
                "failed",
                "error",
                "unavailable",
                "timed_out",
            }:
                result["summary"] = (
                    "Markdown, HTML, and PDF artifacts passed immutable identity, "
                    "canonical score parity, automated-draft status, pending-human-"
                    "approval, and blocked-delivery verification."
                )
            evidence = (
                deepcopy(dict(result.get("evidence") or {}))
                if isinstance(result.get("evidence"), dict)
                else {}
            )
            evidence.update(
                {
                    "automated_draft_package_verified": (
                        str(result.get("status") or "").casefold()
                        not in {
                            "blocked",
                            "failed",
                            "error",
                            "unavailable",
                            "timed_out",
                        }
                    ),
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            )
            result["evidence"] = evidence
            return result

        setattr(provider, _PROVIDER_MARKER, True)
        setattr(provider, "_nico_previous", current_provider)
        cross_format.finality_aware_cross_format_verification_provider = provider
        providers.cross_format_verification_provider = provider

    return {
        "status": "installed",
        "version": VERSION,
        "checks_bound": getattr(
            cross_format._required_checks,
            _CHECK_MARKER,
            False,
        ),
        "provider_bound": getattr(
            cross_format.finality_aware_cross_format_verification_provider,
            _PROVIDER_MARKER,
            False,
        ),
        "required_finality": "automated_draft",
        "verification_completes_before_human_review": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_automated_draft_cross_format_contract"]
