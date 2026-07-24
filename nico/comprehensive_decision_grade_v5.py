from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_report_v5 as report_module
from nico import comprehensive_native_providers as providers
from nico import snapshot_repository_evidence as snapshot_evidence
from nico.comprehensive_decision_grade_assessment_v5 import (
    build_decision_grade_assessment, canonical_scoring_provider,
)
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION
from nico.comprehensive_decision_grade_roadmap_v5 import (
    build_roadmap, executive_briefing_provider, resourcing_provider, roadmap_provider,
)
from nico.comprehensive_final_report_filename_v48 import (
    install_comprehensive_final_report_filename_v48,
)
from nico.comprehensive_final_report_semantics_v47 import (
    install_comprehensive_final_report_semantics_v47,
)

_SCAN_DETAILS: ContextVar[dict[str, Any] | None] = ContextVar("nico_v5_scan_details", default=None)
_ORIGINAL_COLLECT = snapshot_evidence.collect_snapshot_repository_evidence
_WRAPPER_MARKER = "__nico_decision_grade_safe_samples__"


def _safe_sample_wrapper(delegate: Callable[[dict[str, str]], dict[str, Any]]) -> Callable[[dict[str, str]], dict[str, Any]]:
    """Decorate the scanner currently installed by earlier calibration layers.

    The installer must compose with later attachment/calibration wrappers rather than
    restoring the function that happened to exist when this module was imported.
    ``wraps`` deliberately preserves the delegate name and identity metadata expected
    by the score-integrity and idempotency contracts.
    """
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


def install_decision_grade_binding() -> dict[str, Any]:
    global build_comprehensive_report_package

    final_report_semantics = install_comprehensive_final_report_semantics_v47()
    final_report_filename = install_comprehensive_final_report_filename_v48()
    build_comprehensive_report_package = report_module.build_comprehensive_report_package
    current_scanner = snapshot_evidence.scan_files
    scanner_with_samples = _safe_sample_wrapper(current_scanner)
    snapshot_evidence.scan_files = scanner_with_samples
    snapshot_evidence.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.canonical_scoring_provider = canonical_scoring_provider
    providers.roadmap_provider = roadmap_provider
    providers.resourcing_provider = resourcing_provider
    providers.executive_briefing_provider = executive_briefing_provider
    providers.build_comprehensive_report_package = build_comprehensive_report_package
    return {
        "artifact_schema": VERSION,
        "bound": providers.build_comprehensive_report_package is report_module.build_comprehensive_report_package,
        "canonical_scoring_bound": providers.canonical_scoring_provider is canonical_scoring_provider,
        "repository_evidence_samples_bound": providers.collect_snapshot_repository_evidence is _collect_with_safe_samples,
        "scanner_wrapper_name": getattr(scanner_with_samples, "__name__", "scan_files"),
        "scanner_wrapper_composed": True,
        "final_report_semantics": final_report_semantics,
        "final_report_filename": final_report_filename,
        "final_report_semantics_bound": final_report_semantics.get("bound") is True,
        "final_report_filename_bound": final_report_filename.get("bound") is True,
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
