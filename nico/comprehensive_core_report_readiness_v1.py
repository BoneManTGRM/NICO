from __future__ import annotations

import base64
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive_core_report_readiness.v1"
_MARKER = "__nico_comprehensive_core_report_readiness_v1__"


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _report_package(result: dict[str, Any]) -> dict[str, Any]:
    package = result.get("report_package")
    return package if isinstance(package, dict) else {}


def _valid_pdf(package: dict[str, Any]) -> bool:
    encoded = str(package.get("pdf_base64") or "")
    if not encoded or package.get("pdf_error"):
        return False
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception:
        return False
    return payload.startswith(b"%PDF")


def core_report_artifact_readiness(result: dict[str, Any]) -> dict[str, Any]:
    """Classify whether the core decision-report artifacts were actually generated.

    The early core-report stage is an intermediate artifact boundary. A stricter
    decision-grade quality gate may correctly keep the package review-limited, but it
    must not erase valid Markdown, HTML, JSON, and PDF artifacts or stop later
    Strategic stages. The final report provider remains unchanged and fail-closed.
    """

    package = _report_package(result)
    checks = {
        "report_id_present": bool(str(package.get("report_id") or "").strip()),
        "markdown_present": bool(str(package.get("markdown") or "").strip()),
        "html_present": bool(str(package.get("html") or "").strip()),
        "canonical_json_present": isinstance(package.get("json"), dict) and bool(package.get("json")),
        "pdf_valid": _valid_pdf(package),
        "human_review_required": package.get("human_review_required") is True,
        "client_delivery_blocked": package.get("client_delivery_allowed") is False,
    }
    return {
        "artifact_schema": VERSION,
        "status": "ready" if all(checks.values()) else "blocked",
        "checks": checks,
        "artifacts_ready": all(checks.values()),
        "report_contract_status": str(result.get("status") or "blocked"),
        "report_contract_reason": _text(result.get("reason") or package.get("pdf_error") or ""),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def wrap_core_report_provider(provider: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if getattr(provider, _MARKER, False):
        return provider

    @wraps(provider)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        result = provider(context)
        if not isinstance(result, dict):
            return result
        readiness = core_report_artifact_readiness(result)
        result["core_report_artifact_readiness"] = readiness
        if str(result.get("status") or "").lower() not in {"blocked", "failed", "error"}:
            return result
        if readiness["artifacts_ready"] is not True:
            return result

        output = dict(result)
        original_status = str(result.get("status") or "blocked")
        original_reason = _text(result.get("reason") or "decision_grade_report_contract_review_limited")
        output.update(
            {
                "status": "complete",
                "summary": (
                    "The core decision-report artifacts were generated and retained. "
                    "One or more strict package-quality conditions remain review-limited; "
                    "later Strategic and final-report gates must still run."
                ),
                "reason": "",
                "report_contract_status": original_status,
                "report_contract_reason": original_reason,
                "core_artifact_generation_complete": True,
                "final_package": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "core_report_artifact_readiness": {
                    **readiness,
                    "status": "review_limited",
                    "report_contract_status": original_status,
                    "report_contract_reason": original_reason,
                },
            }
        )
        evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
        package = _report_package(output)
        evidence.update(
            {
                "report_id": package.get("report_id") or "",
                "core_artifact_generation_complete": True,
                "report_contract_status": original_status,
                "report_contract_reason": original_reason,
                "pdf_page_count": package.get("pdf_page_count") or 0,
                "canonical_truth_sha256": package.get("canonical_truth_sha256") or "",
                "final_package": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
        output["evidence"] = evidence
        return output

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_comprehensive_core_report_readiness(target: FastAPI) -> dict[str, Any]:
    raw = getattr(target.state, PROVIDER_STATE_KEY, None)
    if not isinstance(raw, dict):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "comprehensive_provider_registry_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    provider = raw.get("report_generation")
    if not callable(provider):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "core_report_provider_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    wrapped = wrap_core_report_provider(provider)
    raw["report_generation"] = wrapped
    setattr(target.state, PROVIDER_STATE_KEY, raw)
    return {
        "status": "installed" if wrapped is not provider else "already_installed",
        "version": VERSION,
        "bound": raw.get("report_generation") is wrapped,
        "core_artifacts_can_proceed_review_limited": True,
        "final_report_provider_unchanged": True,
        "invalid_or_missing_artifacts_still_block": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "core_report_artifact_readiness",
    "install_comprehensive_core_report_readiness",
    "wrap_core_report_provider",
]
