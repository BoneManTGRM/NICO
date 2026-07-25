from __future__ import annotations

import base64
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive_final_report_execution.v1"
_MARKER = "__nico_comprehensive_final_report_execution_v1__"


def _text(value: Any, limit: int = 1600) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _package(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("report_package")
    return value if isinstance(value, dict) else {}


def _decode_pdf(package: dict[str, Any]) -> bytes:
    encoded = str(package.get("pdf_base64") or "")
    if not encoded or package.get("pdf_error"):
        return b""
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception:
        return b""


def final_report_execution_readiness(result: dict[str, Any]) -> dict[str, Any]:
    """Determine whether final report generation executed successfully.

    Report generation and delivery authorization are separate decisions. A final report
    that accurately records evidence gaps, critical validation issues, or pending human
    approval is still a successfully generated assessment artifact. Those conditions
    must block delivery, not mislabel the assessment execution as failed.
    """

    package = _package(result)
    pdf = _decode_pdf(package)
    canonical = package.get("json")
    checks = {
        "report_id_present": bool(str(package.get("report_id") or "").strip()),
        "markdown_present": bool(str(package.get("markdown") or "").strip()),
        "html_present": bool(str(package.get("html") or "").strip()),
        "canonical_json_present": isinstance(canonical, dict) and bool(canonical),
        "pdf_valid": pdf.startswith(b"%PDF"),
        "human_review_required": package.get("human_review_required") is True,
        "client_delivery_blocked": package.get("client_delivery_allowed") is False,
    }
    artifacts_ready = all(checks.values())
    return {
        "artifact_schema": VERSION,
        "status": "generated_review_required" if artifacts_ready else "generation_failed",
        "artifacts_ready": artifacts_ready,
        "checks": checks,
        "original_status": _text(result.get("status") or "blocked", 80).lower(),
        "original_reason": _text(result.get("reason") or package.get("pdf_error") or ""),
        "delivery_readiness": _text(
            package.get("delivery_status")
            or package.get("readiness_status")
            or package.get("approval_status")
            or "human_review_required",
            240,
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def wrap_final_report_provider(
    provider: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if getattr(provider, _MARKER, False):
        return provider

    @wraps(provider)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        result = provider(context)
        if not isinstance(result, dict):
            return result
        readiness = final_report_execution_readiness(result)
        result["final_report_execution_readiness"] = readiness
        status = str(result.get("status") or "").strip().lower()
        if status not in {"blocked", "failed", "error", "unavailable", "timed_out"}:
            return result
        if readiness["artifacts_ready"] is not True:
            return result

        original_status = readiness["original_status"]
        original_reason = readiness["original_reason"] or "final_report_requires_human_review"
        output = dict(result)
        output.update(
            {
                "status": "complete",
                "summary": (
                    "The final Comprehensive report artifacts were generated and retained. "
                    "The package remains review-gated and client delivery remains blocked "
                    "until its evidence, validation issues, assumptions, and exact artifact are approved."
                ),
                "reason": "",
                "report_contract_status": original_status,
                "report_contract_reason": original_reason,
                "final_artifact_generation_complete": True,
                "final_package": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "final_report_execution_readiness": {
                    **readiness,
                    "status": "generated_review_required",
                },
            }
        )
        evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
        package = _package(output)
        evidence.update(
            {
                "report_id": package.get("report_id") or "",
                "final_artifact_generation_complete": True,
                "report_contract_status": original_status,
                "report_contract_reason": original_reason,
                "pdf_page_count": package.get("pdf_page_count") or 0,
                "canonical_truth_sha256": package.get("canonical_truth_sha256") or "",
                "final_package": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        )
        output["evidence"] = evidence
        return output

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_comprehensive_final_report_execution(target: FastAPI) -> dict[str, Any]:
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
    provider = raw.get("final_report_generation")
    if not callable(provider):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "final_report_provider_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    wrapped = wrap_final_report_provider(provider)
    raw["final_report_generation"] = wrapped
    setattr(target.state, PROVIDER_STATE_KEY, raw)
    return {
        "status": "installed" if wrapped is not provider else "already_installed",
        "version": VERSION,
        "bound": raw.get("final_report_generation") is wrapped,
        "valid_final_artifacts_complete_execution": True,
        "quality_and_evidence_issues_still_visible": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "final_report_execution_readiness",
    "install_comprehensive_final_report_execution",
    "wrap_final_report_provider",
]
