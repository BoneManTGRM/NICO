from __future__ import annotations

import base64
import io
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive_final_report_execution.v4"
_MARKER = "__nico_comprehensive_final_report_execution_v4__"


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


def _pdf_is_parseable(package: dict[str, Any]) -> bool:
    pdf = _decode_pdf(package)
    if not pdf.startswith(b"%PDF"):
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf))
        return bool(reader.pages)
    except Exception:
        return False


def _apply_local_finality(result: dict[str, Any]) -> dict[str, Any]:
    """Finalize the exact generated package without mutating global report builders.

    Production report generation previously returned a valid PDF whose cover still said
    "Draft only" even though the strict cross-format verifier required final-report,
    pending-human-approval semantics. Apply the established semantic finalizer to this
    one provider result only. Synthetic or malformed PDFs remain untouched so readiness
    continues to fail closed at the existing artifact boundary.
    """

    package = _package(result)
    if not _pdf_is_parseable(package):
        output = dict(result)
        output["local_finality"] = {
            "status": "skipped",
            "version": VERSION,
            "reason": "generated_pdf_not_parseable",
            "global_report_builder_mutated": False,
        }
        return output

    from nico.comprehensive_final_report_semantics_v47 import (
        VERSION as FINALITY_VERSION,
        finalize_comprehensive_report_result,
    )

    output = finalize_comprehensive_report_result(result)
    output["local_finality"] = {
        "status": "complete"
        if output.get("report_finality") == "final"
        and output.get("approval_status") == "pending_human_approval"
        and output.get("delivery_status") == "blocked_pending_human_approval"
        else "blocked",
        "version": VERSION,
        "semantic_finality_version": FINALITY_VERSION,
        "report_finality": output.get("report_finality"),
        "approval_status": output.get("approval_status"),
        "delivery_status": output.get("delivery_status"),
        "global_report_builder_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def _canonical_final_report_context(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy canonical score truth into the final report input without global mutation.

    Earlier report layers can legitimately retain an Evidence-Adjusted score that differs
    from technical maturity. The final package must receive one synchronized assessment
    before Markdown, HTML, JSON, and PDF are rendered. Applying this at the production
    provider boundary avoids process-global monkey patches while guaranteeing that every
    final format starts from the same score pair.
    """

    from nico.comprehensive_cross_format_finality_v49 import (
        synchronize_comprehensive_score_truth,
    )

    output = dict(context)
    source_stages = context.get("prior_stage_results")
    if not isinstance(source_stages, dict):
        return output, {
            "status": "unavailable",
            "reason": "prior_stage_results_unavailable",
        }

    stages = deepcopy(source_stages)
    scoring = stages.get("evidence_reconciliation_and_scoring")
    if not isinstance(scoring, dict):
        output["prior_stage_results"] = stages
        return output, {
            "status": "unavailable",
            "reason": "canonical_scoring_stage_unavailable",
        }

    assessment = scoring.get("assessment")
    if not isinstance(assessment, dict):
        output["prior_stage_results"] = stages
        return output, {
            "status": "unavailable",
            "reason": "canonical_scoring_assessment_unavailable",
        }

    synchronized = synchronize_comprehensive_score_truth(assessment)
    scoring["assessment"] = synchronized
    maturity = (
        synchronized.get("maturity_signal")
        if isinstance(synchronized.get("maturity_signal"), dict)
        else {}
    )
    technical = synchronized.get("technical_score", maturity.get("technical_score"))
    adjusted = synchronized.get(
        "canonical_evidence_adjusted_score",
        maturity.get("canonical_evidence_adjusted_score"),
    )
    evidence = scoring.get("evidence") if isinstance(scoring.get("evidence"), dict) else {}
    evidence.update(
        {
            "technical_score": technical,
            "evidence_adjusted_score": adjusted,
            "canonical_evidence_adjusted_score": adjusted,
            "final_report_input_scores_synchronized": True,
        }
    )
    scoring["evidence"] = evidence
    scoring["canonical_evidence_adjusted_score"] = adjusted
    stages["evidence_reconciliation_and_scoring"] = scoring
    output["prior_stage_results"] = stages
    truth = {
        "status": "complete" if technical is not None and adjusted is not None else "incomplete",
        "version": VERSION,
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "technical_presented_score": maturity.get("presented_score"),
        "input_assessment_synchronized": True,
        "global_report_builder_mutated": False,
    }
    output["final_report_input_score_truth"] = truth
    return output, truth


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
        report_context, score_truth = _canonical_final_report_context(context)
        provider_result = provider(report_context)
        if not isinstance(provider_result, dict):
            return provider_result

        source_status = _text(provider_result.get("status") or "blocked", 80).lower()
        source_reason = _text(provider_result.get("reason") or "")
        result = _apply_local_finality(provider_result)
        result["final_report_input_score_truth"] = score_truth
        readiness = final_report_execution_readiness(result)
        result["final_report_execution_readiness"] = readiness
        status = str(result.get("status") or "").strip().lower()
        if status not in {"blocked", "failed", "error", "unavailable", "timed_out"}:
            return result
        if readiness["artifacts_ready"] is not True:
            return result

        original_status = source_status or readiness["original_status"]
        original_reason = source_reason or readiness["original_reason"] or "final_report_requires_human_review"
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
                "final_report_input_score_truth": score_truth,
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
                "final_report_input_score_truth": score_truth,
            }
        )
        output["evidence"] = evidence
        return output

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_comprehensive_final_report_execution(target: FastAPI) -> dict[str, Any]:
    """Bind synchronized local finality and fail-closed cross-format verification."""

    from nico.comprehensive_cross_format_finality_v49 import (
        VERSION as CROSS_FORMAT_VERSION,
        finality_aware_cross_format_verification_provider,
    )

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

    previous_verifier = raw.get("cross_format_verification")
    wrapped = wrap_final_report_provider(provider)
    raw["final_report_generation"] = wrapped
    raw["cross_format_verification"] = finality_aware_cross_format_verification_provider
    setattr(target.state, PROVIDER_STATE_KEY, raw)

    final_bound = raw.get("final_report_generation") is wrapped
    verifier_bound = (
        raw.get("cross_format_verification")
        is finality_aware_cross_format_verification_provider
    )
    changed = wrapped is not provider or previous_verifier is not finality_aware_cross_format_verification_provider
    bound = final_bound and verifier_bound
    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "bound": bound,
        "final_report_provider_bound": final_bound,
        "cross_format_provider_bound": verifier_bound,
        "cross_format_contract_schema": CROSS_FORMAT_VERSION,
        "canonical_score_parity_required": True,
        "canonical_score_synchronized_before_render": True,
        "local_finality_applied_after_render": True,
        "pdf_finality_semantics_required": True,
        "failed_checks_exposed": True,
        "global_report_builder_mutated": False,
        "valid_final_artifacts_complete_execution": True,
        "quality_and_evidence_issues_still_visible": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_apply_local_finality",
    "_canonical_final_report_context",
    "final_report_execution_readiness",
    "install_comprehensive_final_report_execution",
    "wrap_final_report_provider",
]
