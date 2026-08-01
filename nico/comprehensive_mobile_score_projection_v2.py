from __future__ import annotations

from typing import Any, Callable

import nico.comprehensive_api_controller as controller_module

VERSION = "nico.comprehensive_mobile_score_projection.v4"

_ORIGINAL_REPORT_OUTPUTS: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]] | None = None
_INSTALLED = False


def _canonical_assessment_from_report(report: dict[str, Any]) -> dict[str, Any]:
    """Recover the canonical assessment without embedding the full report package."""

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
    from nico.comprehensive_failure_diagnostics_v1 import (
        install_comprehensive_failure_diagnostics_v1,
    )
    from nico.comprehensive_final_artifact_truth_compat_v54 import (
        install_comprehensive_final_artifact_truth_compat_v54,
    )
    from nico.comprehensive_final_artifact_truth_v53 import (
        install_comprehensive_final_artifact_truth_v53,
    )
    from nico.comprehensive_final_artifact_truth_v54 import (
        install_comprehensive_final_artifact_truth_v54,
    )
    from nico.comprehensive_report_truth_stabilization_v52 import (
        install_comprehensive_report_truth_stabilization_v52,
    )
    from nico.comprehensive_report_truth_v53 import (
        install_comprehensive_report_truth_v53,
    )
    from nico.comprehensive_scoring_manifest_v54 import (
        install_comprehensive_scoring_manifest_v54,
    )
    from nico.evidence_ledger_typescript_truth_v1 import (
        install_evidence_ledger_typescript_truth_v1,
    )
    from nico.osv_api_fallback_truth_v1 import install_osv_api_fallback_truth_v1
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    scoring_manifest = install_comprehensive_scoring_manifest_v54()
    compatibility_truth = install_comprehensive_report_truth_stabilization_v52()
    report_truth = install_comprehensive_report_truth_v53()
    final_artifact_truth_v53 = install_comprehensive_final_artifact_truth_v53()
    final_artifact_compat = install_comprehensive_final_artifact_truth_compat_v54()
    final_artifact_truth = install_comprehensive_final_artifact_truth_v54()
    failure_diagnostics = install_comprehensive_failure_diagnostics_v1()
    return {
        "scoring_manifest": scoring_manifest,
        "report_truth_compatibility": compatibility_truth,
        "report_truth_stabilization": report_truth,
        "final_artifact_truth_v53": final_artifact_truth_v53,
        "final_artifact_compat": final_artifact_compat,
        "final_artifact_truth": final_artifact_truth,
        "failure_diagnostics": failure_diagnostics,
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

    # This is the final report-related installer in nico.__init__. Bind pre-render
    # report reconciliation and full-artifact verification here so no earlier
    # compatibility layer can replace either boundary afterward.
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
        "explicit_assurance_factors_retained": True,
        "pre_render_truth_reconciliation": True,
        "full_pdf_text_validated": True,
        "weighted_score_recalculation_required": True,
        "legacy_final_artifact_fixtures_supported": True,
        "blocked_run_recovery_supported": True,
        "failure_checks_visible_to_ui": True,
        "finding_register_deduplicated": True,
        "scanner_state_reconciled": True,
        "canonical_score_contract_reconciled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_mobile_score_projection_v2",
]
