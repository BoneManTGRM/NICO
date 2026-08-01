from __future__ import annotations

from typing import Any, Callable

import nico.comprehensive_api_controller as controller_module

VERSION = "nico.comprehensive_mobile_score_projection.v3"

_ORIGINAL_REPORT_OUTPUTS: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]] | None = None
_INSTALLED = False


def _canonical_assessment_from_report(report: dict[str, Any]) -> dict[str, Any]:
    """Recover the canonical assessment without embedding the full report package.

    Comprehensive report generation stores the decision-grade assessment inside the
    canonical JSON artifact. Some terminal records do not duplicate that object on the
    stage itself. The bounded browser response still needs the compact score, maturity,
    coverage, and section projection, so the controller must resolve the same canonical
    source before the report package is reduced to an on-demand manifest.
    """

    json_value = report.get("json")
    if not isinstance(json_value, dict):
        return {}

    direct = json_value.get("assessment")
    if isinstance(direct, dict):
        return direct

    for key in ("report", "canonical_report", "decision_report"):
        nested = json_value.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("assessment"), dict):
            return nested["assessment"]
    return {}


def _report_outputs(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    assert _ORIGINAL_REPORT_OUTPUTS is not None
    report, assessment = _ORIGINAL_REPORT_OUTPUTS(record)
    if assessment or not report:
        return report, assessment
    return report, _canonical_assessment_from_report(report)


def _install_final_runtime_truth() -> dict[str, Any]:
    from nico.evidence_ledger_typescript_truth_v1 import (
        install_evidence_ledger_typescript_truth_v1,
    )
    from nico.osv_api_fallback_truth_v1 import install_osv_api_fallback_truth_v1
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    return {
        "scorecard_extraction_validation": install_scorecard_extraction_validation(),
        "osv_api_fallback_truth": install_osv_api_fallback_truth_v1(),
        "evidence_ledger_typescript_truth": (
            install_evidence_ledger_typescript_truth_v1()
        ),
    }


def install_comprehensive_mobile_score_projection_v2() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_REPORT_OUTPUTS
    if _INSTALLED:
        final_runtime_truth = _install_final_runtime_truth()
        return {
            "status": "already_installed",
            "version": VERSION,
            **final_runtime_truth,
        }

    _ORIGINAL_REPORT_OUTPUTS = controller_module._report_outputs
    controller_module._report_outputs = _report_outputs

    # This installer is the final report-related call in nico.__init__. Bind the
    # extraction-safe scorecard validator, scanner source-truth, and evidence
    # classification contracts here so no earlier compatibility module can
    # replace them afterward.
    final_runtime_truth = _install_final_runtime_truth()
    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_assessment_fallback": "report.json.assessment",
        "full_report_embedded": False,
        **final_runtime_truth,
        "wrapped_control_labels_supported": True,
        "all_canonical_rows_and_scores_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_mobile_score_projection_v2",
]
