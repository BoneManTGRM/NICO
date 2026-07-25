from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico import comprehensive_native_providers as providers
from nico import snapshot_repository_evidence as snapshot_evidence
from nico.comprehensive_code_remediation_appendix_v1 import (
    install_comprehensive_code_remediation_appendix_v1,
)
from nico.comprehensive_code_remediation_outline_v1 import (
    install_comprehensive_code_remediation_outline_v1,
)
from nico.comprehensive_decision_grade_assessment_v5 import (
    build_decision_grade_assessment, canonical_scoring_provider,
)
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION
from nico.comprehensive_decision_grade_roadmap_v5 import (
    build_roadmap, executive_briefing_provider, resourcing_provider, roadmap_provider,
)
from nico.comprehensive_evidence_quality_v1 import (
    normalize_assessment, wrap_evidence_quality_provider,
)
from nico.comprehensive_final_pdf_front_matter_v1 import (
    install_comprehensive_final_pdf_front_matter_v1,
)
from nico.comprehensive_final_report_filename_v48 import (
    install_comprehensive_final_report_filename_v48,
)
from nico.comprehensive_final_report_semantics_v47 import (
    install_comprehensive_final_report_semantics_v47,
)
from nico.comprehensive_report_clarity_v8 import install_comprehensive_report_clarity_v8
from nico.comprehensive_report_polish_v1 import install_comprehensive_report_polish_v1
from nico.comprehensive_score_truth_v1 import wrap_report_builder, wrap_scoring_provider
from nico.decision_grade_history_store_v1 import (
    VERSION as DECISION_GRADE_HISTORY_STORE_VERSION,
    wrap_report_builder_with_persisted_history,
)
from nico.full_source_archive_profile_v1 import install_full_source_archive_profile_v1
from nico.typescript_ast_complexity_v1 import install_typescript_ast_complexity_v1

_SCAN_DETAILS: ContextVar[dict[str, Any] | None] = ContextVar("nico_v5_scan_details", default=None)
_ORIGINAL_COLLECT = snapshot_evidence.collect_snapshot_repository_evidence
_WRAPPER_MARKER = "__nico_decision_grade_safe_samples__"


def _safe_sample_wrapper(delegate: Callable[[dict[str, str]], dict[str, Any]]) -> Callable[[dict[str, str]], dict[str, Any]]:
    """Decorate the scanner currently installed by earlier calibration layers."""
    if getattr(delegate, _WRAPPER_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(files: dict[str, str]) -> dict[str, Any]:
        result = delegate(files)
        _SCAN_DETAILS.set({
            "risk_pattern_samples": list(result.get("risks") or [])[:20],
            "potential_secret_pattern_samples": list(result.get("secrets") or [])[:20],
            "todo_fixme_security_samples": list(result.get("todos") or [])[:20],
        })
        return result

    setattr(wrapped, _WRAPPER_MARKER, True)
    return wrapped


def _collect_with_safe_samples(*args: Any, **kwargs: Any):
    token = _SCAN_DETAILS.set(None)
    try:
        bundle, complexity = _ORIGINAL_COLLECT(*args, **kwargs)
        details = _SCAN_DETAILS.get() or {}
        signals = bundle.get("code_signal_evidence") if isinstance(bundle, dict) else None
        if isinstance(signals, dict):
            signals.update(details)
        return bundle, complexity
    finally:
        _SCAN_DETAILS.reset(token)


def _quality_report_builder(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        assessment = result.get("assessment")
        if isinstance(assessment, dict):
            normalized = normalize_assessment(assessment)
            result["assessment"] = normalized
            package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
            package["technical_score"] = normalized.get("technical_score")
            package["evidence_adjusted_score"] = normalized.get("canonical_evidence_adjusted_score")
            package["canonical_evidence_adjusted_score"] = normalized.get("canonical_evidence_adjusted_score")
            result["report_package"] = package
        return result

    return wrapped


def install_decision_grade_binding() -> dict[str, Any]:
    global build_comprehensive_report_package

    full_source_profile = install_full_source_archive_profile_v1()
    typescript_ast_complexity = install_typescript_ast_complexity_v1()
    final_report_semantics = install_comprehensive_final_report_semantics_v47()
    final_report_filename = install_comprehensive_final_report_filename_v48()
    report_clarity = install_comprehensive_report_clarity_v8()
    report_polish = install_comprehensive_report_polish_v1()
    code_remediation = install_comprehensive_code_remediation_appendix_v1()
    code_outline = install_comprehensive_code_remediation_outline_v1()
    final_pdf_front_matter = install_comprehensive_final_pdf_front_matter_v1()

    evidence_quality_provider = wrap_evidence_quality_provider(canonical_scoring_provider)
    score_truth_provider = wrap_scoring_provider(evidence_quality_provider)
    history_builder = wrap_report_builder_with_persisted_history(report_module.build_comprehensive_report_package)
    quality_builder = _quality_report_builder(history_builder)
    build_comprehensive_report_package = wrap_report_builder(quality_builder)

    current_scanner = snapshot_evidence.scan_files
    scanner_with_samples = _safe_sample_wrapper(current_scanner)
    snapshot_evidence.scan_files = scanner_with_samples
    snapshot_evidence.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.canonical_scoring_provider = score_truth_provider
    providers.roadmap_provider = roadmap_provider
    providers.resourcing_provider = resourcing_provider
    providers.executive_briefing_provider = executive_briefing_provider
    providers.build_comprehensive_report_package = build_comprehensive_report_package
    return {
        "artifact_schema": VERSION,
        "bound": providers.build_comprehensive_report_package is build_comprehensive_report_package,
        "canonical_scoring_bound": providers.canonical_scoring_provider is score_truth_provider,
        "repository_evidence_samples_bound": providers.collect_snapshot_repository_evidence is _collect_with_safe_samples,
        "scanner_wrapper_name": getattr(scanner_with_samples, "__name__", "scan_files"),
        "scanner_wrapper_composed": True,
        "full_source_profile": full_source_profile,
        "typescript_ast_complexity": typescript_ast_complexity,
        "final_report_semantics": final_report_semantics,
        "final_report_filename": final_report_filename,
        "report_clarity": report_clarity,
        "report_polish": report_polish,
        "code_remediation": code_remediation,
        "code_remediation_outline": code_outline,
        "final_pdf_front_matter": final_pdf_front_matter,
        "full_source_profile_bound": full_source_profile.get("status") in {"installed", "already_installed"},
        "typescript_ast_complexity_bound": typescript_ast_complexity.get("status") in {"installed", "already_installed"},
        "final_report_semantics_bound": final_report_semantics.get("bound") is True,
        "final_report_filename_bound": final_report_filename.get("bound") is True,
        "report_clarity_bound": report_clarity.get("status") in {"installed", "already_installed"},
        "report_polish_bound": report_polish.get("status") in {"installed", "already_installed"},
        "code_remediation_bound": code_remediation.get("status") in {"installed", "already_installed"},
        "code_remediation_outline_bound": code_outline.get("status") in {"installed", "already_installed"},
        "final_pdf_front_matter_bound": final_pdf_front_matter.get("status") in {"installed", "already_installed"},
        "exact_location_code_remediation_plan": code_remediation.get("exact_location_code_plan") is True,
        "pdf_code_remediation_appendix": code_remediation.get("pdf_code_pages") is True,
        "pdf_outline_preserved_after_appendix": code_outline.get("base_outline_preserved") is True,
        "front_matter_pages_replaced_not_overlaid": final_pdf_front_matter.get("front_matter_pages_replaced_not_overlaid") is True,
        "unverified_candidates_not_p1": report_polish.get("unverified_candidates_not_p1") is True,
        "equivalent_review_candidates_grouped": report_polish.get("equivalent_review_candidates_grouped") is True,
        "canonical_score_truth_reconciled": True,
        "canonical_evidence_adjusted_score_immutable": True,
        "control_specific_assurance": True,
        "blanket_incomplete_removed": True,
        "report_score_drift_blocks_package": True,
        "decision_grade_history_store_version": DECISION_GRADE_HISTORY_STORE_VERSION,
        "persisted_historical_comparison_bound": True,
        "historical_comparison_uses_authorized_storage_scope": True,
        "synthetic_historical_delta_allowed": False,
        "automatic_code_merge_allowed": False,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "stale_draft_language_allowed": False,
        "score_band_separated_from_assurance": True,
        "secret_category_isolated": True,
        "structured_findings_register": True,
        "named_architecture_hotspots": True,
        "explicit_limitation_accounting": True,
        "executable_roadmap": True,
        "machine_readable_csv_exports": True,
        "pdf_outline_bookmarks": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


build_comprehensive_report_package = report_module.build_comprehensive_report_package

__all__ = [
    "APPENDIX_HEADING", "REVIEW_HEADING", "VERSION",
    "build_comprehensive_report_package", "build_decision_grade_assessment",
    "build_roadmap", "canonical_scoring_provider", "install_decision_grade_binding",
]
