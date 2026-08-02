from __future__ import annotations

from typing import Any, Callable

import nico.comprehensive_api_controller as controller_module

VERSION = "nico.comprehensive_mobile_score_projection.v3"
RUNTIME_REVISION = "v60-client-ready-accuracy"

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
    from nico.comprehensive_client_readiness_v59 import (
        install_comprehensive_client_readiness_v59,
    )
    from nico.comprehensive_client_report_render_v60 import (
        install_comprehensive_client_report_render_v60,
    )
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
    from nico.comprehensive_final_artifact_truth_v54_compat import (
        install_comprehensive_final_artifact_truth_v54_compat,
    )
    from nico.comprehensive_final_publication_truth_v58 import (
        install_comprehensive_final_publication_truth_v58,
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
    from nico.comprehensive_source_anchor_location_v57 import (
        install_comprehensive_source_anchor_location_v57,
    )
    from nico.evidence_ledger_typescript_truth_v1 import (
        install_evidence_ledger_typescript_truth_v1,
    )
    from nico.osv_api_fallback_truth_v1 import install_osv_api_fallback_truth_v1
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    source_anchor_location = install_comprehensive_source_anchor_location_v57()
    final_publication_truth = install_comprehensive_final_publication_truth_v58()
    client_readiness = install_comprehensive_client_readiness_v59()
    client_report_render = install_comprehensive_client_report_render_v60()
    scoring_manifest = install_comprehensive_scoring_manifest_v54()
    compatibility_truth = install_comprehensive_report_truth_stabilization_v52()
    report_truth = install_comprehensive_report_truth_v53()
    final_artifact_truth_v53 = install_comprehensive_final_artifact_truth_v53()
    final_artifact_compat = install_comprehensive_final_artifact_truth_compat_v54()
    final_artifact_truth = install_comprehensive_final_artifact_truth_v54()
    final_artifact_v54_compat = install_comprehensive_final_artifact_truth_v54_compat()
    failure_diagnostics = install_comprehensive_failure_diagnostics_v1()
    return {
        "runtime_revision": RUNTIME_REVISION,
        "source_anchor_location": source_anchor_location,
        "final_publication_truth": final_publication_truth,
        "client_readiness": client_readiness,
        "client_report_render": client_report_render,
        "scoring_manifest": scoring_manifest,
        "report_truth_compatibility": compatibility_truth,
        "report_truth_stabilization": report_truth,
        "final_artifact_truth_v53": final_artifact_truth_v53,
        "final_artifact_compat": final_artifact_compat,
        "final_artifact_truth": final_artifact_truth,
        "final_artifact_v54_compat": final_artifact_v54_compat,
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
        "final_register_count_synchronized_before_render": True,
        "legacy_score_contract_reconciled_before_render": True,
        "existing_report_renderer_preserved": True,
        "existing_visual_design_preserved": True,
        "existing_section_order_preserved": True,
        "report_redesign_performed": False,
        "production_pdf_is_accuracy_acceptance_artifact": True,
        "full_pdf_text_validated": True,
        "weighted_score_recalculation_required": True,
        "legacy_final_artifact_fixtures_supported": True,
        "blocked_run_recovery_supported": True,
        "failure_checks_visible_to_ui": True,
        "finding_register_deduplicated": True,
        "ranged_source_anchor_paths_canonicalized": True,
        "scanner_state_reconciled": True,
        "analyzer_coverage_canonicalized": True,
        "maturity_terminology_unified": True,
        "identifier_integrity_repaired_before_render": True,
        "limited_evidence_status_separated_from_execution_status": True,
        "canonical_score_contract_reconciled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "RUNTIME_REVISION",
    "VERSION",
    "install_comprehensive_mobile_score_projection_v2",
]
