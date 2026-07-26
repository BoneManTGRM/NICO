from __future__ import annotations

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
from nico.comprehensive_report_scanner_scoring_v51 import (
    _normalize_assessment,
    _scanner_execution_objects,
)
from nico.comprehensive_report_spanish_artifacts_v51 import _localize_package

VERSION = "nico.comprehensive_report_finality.v51"
_PATCH_MARKER = "_nico_comprehensive_report_finality_v51"
_LOCALE: ContextVar[str] = ContextVar("nico_comprehensive_report_locale", default="en")
_SCANNER_TRUTH: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "nico_comprehensive_scanner_truth", default={}
)

def install_comprehensive_report_finality_v51() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_report_package as base_report
    from nico import decision_grade_contract_v1 as contract_module
    from nico import comprehensive_cross_format_finality_v49 as cross_format

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
        contract = original_contract_builder(*args, **kwargs)
        assessment = kwargs.get("assessment")
        if not isinstance(assessment, dict) and len(args) > 1 and isinstance(args[1], dict):
            assessment = args[1]
        records = assessment.get("scanner_execution_records") if isinstance(assessment, dict) else []
        objects = _scanner_execution_objects(records if isinstance(records, list) else [])
        if objects:
            payload = contract.model_dump(mode="json")
            payload["scanner_executions"] = [item.model_dump(mode="json") for item in objects]
            contract = contract_module.DecisionGradeContract.model_validate(payload)
        return contract

    report.build_decision_grade_contract = build_contract
    contract_module.build_decision_grade_contract = build_contract

    original_identity = providers._identity

    @wraps(original_identity)
    def identity(context: dict[str, Any]) -> dict[str, str]:
        value = original_identity(context)
        value["report_language"] = _locale(context.get("report_language") or context.get("language") or context.get("locale"))
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
            if isinstance(result, dict):
                result["report_language"] = language
                if language == "es-MX":
                    result = _localize_package(result)
            return result
        finally:
            _SCANNER_TRUTH.reset(truth_token)
            _LOCALE.reset(locale_token)

    setattr(build_package, _PATCH_MARKER, True)
    setattr(build_package, "_nico_previous", current)
    report.build_comprehensive_report_package = build_package
    base_report.build_comprehensive_report_package = build_package
    providers.build_comprehensive_report_package = build_package

    original_delivery_boundary = cross_format._delivery_boundary_present

    @wraps(original_delivery_boundary)
    def delivery_boundary(markdown: str) -> bool:
        if original_delivery_boundary(markdown):
            return True
        upper = _text(markdown).upper()
        return (
            any(phrase in upper for phrase in ("ENTREGA AL CLIENTE BLOQUEADA", "ENTREGA AL CLIENTE NO AUTORIZADA"))
            and any(phrase in upper for phrase in ("APROBACIÓN HUMANA PENDIENTE", "PENDIENTE DE REVISIÓN HUMANA"))
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
        "spanish_client_artifacts": True,
        "spanish_cross_format_finality": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_report_finality_v51"]
