from __future__ import annotations

import hashlib
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import Any

from nico.comprehensive_report_scanner_detection_v51 import (
    _extract_report_language,
    _locale,
    _scanner_truth,
    _text,
)
from nico.comprehensive_report_scanner_scoring_v51 import _normalize_assessment
from nico.comprehensive_report_spanish_artifacts_v51 import _localize_package

VERSION = "nico.comprehensive_report_finality.v51"
_PATCH_MARKER = "_nico_comprehensive_report_finality_v51"
_LOCALE: ContextVar[str] = ContextVar("nico_comprehensive_report_locale", default="en")
_SCANNER_TRUTH: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "nico_comprehensive_scanner_truth", default={}
)


def install_comprehensive_report_finality_v51() -> dict[str, Any]:
    from nico import comprehensive_cross_format_finality_v49 as cross_format
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_report_package as base_report
    from nico import decision_grade_contract_v1 as contract_module

    current = report.build_comprehensive_report_package
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    original_reconcile = report.reconcile_comprehensive_assessment

    @wraps(original_reconcile)
    def reconcile(assessment: dict[str, Any]) -> dict[str, Any]:
        normalized = original_reconcile(assessment)
        return _normalize_assessment(normalized, _SCANNER_TRUTH.get())

    report.reconcile_comprehensive_assessment = reconcile

    original_contract_builder = report.build_decision_grade_contract

    @wraps(original_contract_builder)
    def build_contract(*args: Any, **kwargs: Any) -> Any:
        assessment = kwargs.get("assessment")
        records = assessment.get("scanner_execution_records") if isinstance(assessment, dict) else []
        if isinstance(records, list) and records:
            stage_summaries = deepcopy(kwargs.get("stage_summaries") or [])
            stage_summaries.append(
                {
                    "stage": "comprehensive_report_scanner_reconciliation_v51",
                    "scanner_results": [
                        {
                            "tool": record.get("scanner_name"),
                            "status": record.get("status"),
                            "required": bool(record.get("required")),
                            "category": (record.get("evidence_categories_affected") or [None])[0],
                            "failure_type": record.get("failure_type"),
                            "error": record.get("failure_message"),
                            "retry_count": int(record.get("retry_count") or 0),
                        }
                        for record in records
                        if isinstance(record, dict) and record.get("scanner_name")
                    ],
                }
            )
            kwargs["stage_summaries"] = stage_summaries
        return original_contract_builder(*args, **kwargs)

    report.build_decision_grade_contract = build_contract
    contract_module.build_decision_grade_contract = build_contract

    original_identity = providers._identity

    @wraps(original_identity)
    def identity(context: dict[str, Any]) -> dict[str, str]:
        value = original_identity(context)
        value["report_language"] = _locale(
            context.get("report_language") or context.get("language") or context.get("locale")
        )
        return value

    providers._identity = identity

    @wraps(current)
    def build_package(*, identity: dict[str, Any], stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        language = _extract_report_language(identity, stage_results)
        truth = _scanner_truth(stage_results)
        locale_token = _LOCALE.set(language)
        truth_token = _SCANNER_TRUTH.set(truth)
        try:
            augmented_identity = dict(identity)
            augmented_identity["report_language"] = language
            augmented_identity["locale"] = language
            result = current(identity=augmented_identity, stage_results=deepcopy(stage_results))
            if not isinstance(result, dict):
                return result
            result["report_language"] = language
            if language == "es-MX":
                result = _localize_package(result)

            package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
            canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
            previous_readiness = package.get("delivery_status") or canonical.get("delivery_status")
            markdown = str(package.get("markdown") or "")
            rendered_html = str(package.get("html") or "")
            boundary_comment = "<!-- CLIENT DELIVERY BLOCKED · PENDING HUMAN APPROVAL -->"
            if boundary_comment not in markdown:
                markdown = markdown.rstrip() + "\n\n" + boundary_comment + "\n"
            if boundary_comment not in rendered_html:
                rendered_html = rendered_html.rstrip() + boundary_comment

            canonical["evidence_readiness_status"] = previous_readiness
            canonical["report_finality"] = "final"
            canonical["approval_status"] = "pending_human_approval"
            canonical["delivery_status"] = "blocked_pending_human_approval"
            canonical["human_review_required"] = True
            canonical["client_delivery_allowed"] = False
            canonical["report_language"] = language
            canonical["locale"] = language
            truth_sha = base_report._canonical_hash(canonical)

            quality = dict(package.get("report_quality_contract") or {})
            quality.update(
                {
                    "report_finality": "final",
                    "approval_status": "pending_human_approval",
                    "delivery_status": "blocked_pending_human_approval",
                    "cross_format_finality_semantics_present": True,
                    "cross_format_boundary_present": True,
                }
            )
            package.update(
                {
                    "markdown": markdown,
                    "html": rendered_html,
                    "json": canonical,
                    "canonical_truth_sha256": truth_sha,
                    "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
                    "evidence_readiness_status": previous_readiness,
                    "report_finality": "final",
                    "approval_status": "pending_human_approval",
                    "delivery_status": "blocked_pending_human_approval",
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                    "report_quality_contract": quality,
                    "report_language": language,
                    "locale": language,
                }
            )
            result.update(
                {
                    "report_package": package,
                    "canonical_truth_sha256": truth_sha,
                    "evidence_readiness_status": previous_readiness,
                    "report_finality": "final",
                    "approval_status": "pending_human_approval",
                    "delivery_status": "blocked_pending_human_approval",
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                    "report_language": language,
                    "locale": language,
                }
            )
            return result
        finally:
            _SCANNER_TRUTH.reset(truth_token)
            _LOCALE.reset(locale_token)

    setattr(build_package, _PATCH_MARKER, True)
    setattr(build_package, "_nico_previous", current)
    report.build_comprehensive_report_package = build_package
    providers.build_comprehensive_report_package = build_package

    original_delivery_boundary = cross_format._delivery_boundary_present

    @wraps(original_delivery_boundary)
    def delivery_boundary(markdown: str) -> bool:
        if original_delivery_boundary(markdown):
            return True
        upper = _text(markdown).upper()
        return (
            any(
                phrase in upper
                for phrase in ("ENTREGA AL CLIENTE BLOQUEADA", "ENTREGA AL CLIENTE NO AUTORIZADA")
            )
            and any(
                phrase in upper
                for phrase in ("APROBACIÓN HUMANA PENDIENTE", "PENDIENTE DE REVISIÓN HUMANA")
            )
        )

    cross_format._delivery_boundary_present = delivery_boundary

    return {
        "status": "installed",
        "version": VERSION,
        "bound": providers.build_comprehensive_report_package is build_package,
        "structured_scanner_completion_records": True,
        "per_control_execution_and_assurance": True,
        "bounded_static_analysis_score": True,
        "canonical_score_parity": True,
        "cross_format_finality_semantics": True,
        "spanish_client_artifacts": True,
        "spanish_cross_format_finality": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_report_finality_v51"]
