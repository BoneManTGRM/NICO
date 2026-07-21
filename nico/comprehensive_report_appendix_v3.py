from __future__ import annotations

from typing import Any

from nico import comprehensive_native_providers as providers
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION
from nico.comprehensive_decision_grade_report_v5 import build_comprehensive_report_package as _decision_grade_builder
from nico.comprehensive_decision_grade_v5 import install_decision_grade_binding

LEGACY_REVIEW_HEADING = "## Human Review Checklist"


def build_comprehensive_report_package(
    *, identity: dict[str, Any], stage_results: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Build the decision-grade Comprehensive package with appendix parity."""

    return _decision_grade_builder(identity=identity, stage_results=stage_results)


def install_native_provider_binding() -> dict[str, Any]:
    """Install score, evidence, roadmap, and report bindings before providers."""

    status = install_decision_grade_binding()
    providers.build_comprehensive_report_package = build_comprehensive_report_package
    return {
        **status,
        "artifact_schema": VERSION,
        "bound": providers.build_comprehensive_report_package is build_comprehensive_report_package,
        "markdown_evidence_appendix": True,
        "html_evidence_appendix": True,
        "pdf_evidence_appendix": True,
        "markdown_human_review_acceptance_gate": True,
        "html_human_review_acceptance_gate": True,
        "pdf_human_review_acceptance_gate": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "APPENDIX_HEADING",
    "LEGACY_REVIEW_HEADING",
    "REVIEW_HEADING",
    "VERSION",
    "build_comprehensive_report_package",
    "install_native_provider_binding",
]
