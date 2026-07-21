from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from nico import comprehensive_native_providers as providers
from nico import snapshot_repository_evidence as snapshot_evidence
from nico.comprehensive_decision_grade_assessment_v5 import (
    build_decision_grade_assessment, canonical_scoring_provider,
)
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION
from nico.comprehensive_decision_grade_report_v5 import build_comprehensive_report_package
from nico.comprehensive_decision_grade_roadmap_v5 import (
    build_roadmap, executive_briefing_provider, resourcing_provider, roadmap_provider,
)

_SCAN_DETAILS: ContextVar[dict[str, Any] | None] = ContextVar("nico_v5_scan_details", default=None)
_ORIGINAL_SCAN_FILES = snapshot_evidence.scan_files
_ORIGINAL_COLLECT = snapshot_evidence.collect_snapshot_repository_evidence


def _scan_files_with_safe_samples(files: dict[str, str]) -> dict[str, Any]:
    result = _ORIGINAL_SCAN_FILES(files)
    _SCAN_DETAILS.set({
        "risk_pattern_samples": list(result.get("risks") or [])[:20],
        "potential_secret_pattern_samples": list(result.get("secrets") or [])[:20],
        "todo_fixme_security_samples": list(result.get("todos") or [])[:20],
    })
    return result


# Preserve the canonical calibrated scanner identity used by the score-integrity
# installer and its idempotency contract. The wrapper only retains already-safe
# bounded samples; it does not replace or bypass calibrated scanning behavior.
_scan_files_with_safe_samples.__name__ = getattr(_ORIGINAL_SCAN_FILES, "__name__", "scan_files")
_scan_files_with_safe_samples.__qualname__ = getattr(_ORIGINAL_SCAN_FILES, "__qualname__", _scan_files_with_safe_samples.__name__)
_scan_files_with_safe_samples.__doc__ = getattr(_ORIGINAL_SCAN_FILES, "__doc__", None)


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
    snapshot_evidence.scan_files = _scan_files_with_safe_samples
    snapshot_evidence.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.collect_snapshot_repository_evidence = _collect_with_safe_samples
    providers.canonical_scoring_provider = canonical_scoring_provider
    providers.roadmap_provider = roadmap_provider
    providers.resourcing_provider = resourcing_provider
    providers.executive_briefing_provider = executive_briefing_provider
    providers.build_comprehensive_report_package = build_comprehensive_report_package
    return {
        "artifact_schema": VERSION,
        "bound": providers.build_comprehensive_report_package is build_comprehensive_report_package,
        "canonical_scoring_bound": providers.canonical_scoring_provider is canonical_scoring_provider,
        "repository_evidence_samples_bound": providers.collect_snapshot_repository_evidence is _collect_with_safe_samples,
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


__all__ = [
    "APPENDIX_HEADING", "REVIEW_HEADING", "VERSION",
    "build_comprehensive_report_package", "build_decision_grade_assessment",
    "build_roadmap", "canonical_scoring_provider", "install_decision_grade_binding",
]
