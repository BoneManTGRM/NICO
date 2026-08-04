from __future__ import annotations

from typing import Any, Callable

import nico.comprehensive_api_controller as controller_module

# Public compatibility identifier. Runtime behavior advances through
# RUNTIME_REVISION so existing mobile proof contracts remain valid.
VERSION = "nico.comprehensive_mobile_score_projection.v3"
RUNTIME_REVISION = "v72-exact-digest-approved-delivery"

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
    from nico.bandit_json_execution_v61 import install_bandit_json_execution_v61
    from nico.client_finding_priority_calibration_v1 import (
        install_client_finding_priority_calibration_v1,
    )
    from nico.client_pdf_status_sanitizer_v7 import (
        install_client_pdf_status_sanitizer_v7,
    )
    from nico.comprehensive_artifact_manifest_approval_v1 import (
        install_comprehensive_artifact_manifest_approval_v1,
    )
    from nico.comprehensive_candidate_identity_v1 import (
        install_comprehensive_candidate_identity_v1,
    )
    from nico.comprehensive_candidate_volume_assurance_v2 import (
        install_candidate_volume_assurance_v2,
    )
    from nico.comprehensive_client_readiness_v59 import (
        install_comprehensive_client_readiness_v59,
    )
    from nico.comprehensive_client_report_render_v60 import (
        install_comprehensive_client_report_render_v60,
    )
    from nico.comprehensive_client_review_companion_v4 import (
        install_comprehensive_review_companion_v4,
    )
    from nico.comprehensive_client_review_companion_v5 import (
        install_comprehensive_review_companion_v5,
    )
    from nico.comprehensive_client_truth_final_v1 import (
        install_comprehensive_client_truth_final_v1,
    )
    from nico.comprehensive_client_truth_validation_compat_v1 import (
        install_comprehensive_client_truth_validation_compat_v1,
    )
    from nico.comprehensive_exact_artifact_hash_binding_v1 import (
        install_comprehensive_exact_artifact_hash_binding_v1,
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
    from nico.comprehensive_final_register_scanner_truth_v62 import (
        install_comprehensive_final_register_scanner_truth_v62,
    )
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )
    from nico.comprehensive_report_truth_stabilization_v52 import (
        install_comprehensive_report_truth_stabilization_v52,
    )
    from nico.comprehensive_report_truth_v53 import (
        install_comprehensive_report_truth_v53,
    )
    from nico.comprehensive_requested_scanner_projection_v62 import (
        install_comprehensive_requested_scanner_projection_v62,
    )
    from nico.comprehensive_scoring_manifest_v54 import (
        install_comprehensive_scoring_manifest_v54,
    )
    from nico.comprehensive_source_anchor_location_v57 import (
        install_comprehensive_source_anchor_location_v57,
    )
    from nico.comprehensive_truth_reconciliation_v7_reentry import (
        install_comprehensive_truth_reconciliation_v7,
    )
    from nico.evidence_ledger_typescript_truth_v1 import (
        install_evidence_ledger_typescript_truth_v1,
    )
    from nico.full_assessment_delivery_digest_binding_v1 import (
        install_full_assessment_delivery_digest_binding_v1,
    )
    from nico.osv_api_fallback_truth_v1 import install_osv_api_fallback_truth_v1
    from nico.scorecard_extraction_validation_v1 import (
        install_scorecard_extraction_validation,
    )

    canonical_truth_reconciliation = install_comprehensive_truth_reconciliation_v7()
    candidate_identity = install_comprehensive_candidate_identity_v1()
    candidate_volume_assurance = install_candidate_volume_assurance_v2()
    bandit_json_execution = install_bandit_json_execution_v61()
    source_anchor_location = install_comprehensive_source_anchor_location_v57()
    requested_scanner_projection = (
        install_comprehensive_requested_scanner_projection_v62()
    )
    final_publication_truth = install_comprehensive_final_publication_truth_v58()
    client_readiness = install_comprehensive_client_readiness_v59()
    final_register_scanner_truth = (
        install_comprehensive_final_register_scanner_truth_v62()
    )
    client_report_render = install_comprehensive_client_report_render_v60()
    scoring_manifest = install_comprehensive_scoring_manifest_v54()
    compatibility_truth = install_comprehensive_report_truth_stabilization_v52()
    report_truth = install_comprehensive_report_truth_v53()
    final_artifact_truth_v53 = install_comprehensive_final_artifact_truth_v53()
    final_artifact_compat = install_comprehensive_final_artifact_truth_compat_v54()
    final_artifact_truth = install_comprehensive_final_artifact_truth_v54()
    final_artifact_v54_compat = install_comprehensive_final_artifact_truth_v54_compat()
    failure_diagnostics = install_comprehensive_failure_diagnostics_v1()

    # Preserve legacy compatibility first, then bind the substantive review,
    # evidence-based finding priority, final truth, complete manifest, and exact receipt.
    install_comprehensive_review_companion_v4()
    client_review_companion = install_comprehensive_review_companion_v5()
    client_pdf_sanitizer = install_client_pdf_status_sanitizer_v7()
    finding_priority_calibration = install_client_finding_priority_calibration_v1()
    client_truth_final = install_comprehensive_client_truth_final_v1()
    client_truth_validation_compat = (
        install_comprehensive_client_truth_validation_compat_v1()
    )
    manifest_navigation = install_comprehensive_manifest_navigation_v1()
    exact_artifact_hash_binding = install_comprehensive_exact_artifact_hash_binding_v1()
    artifact_manifest_approval = install_comprehensive_artifact_manifest_approval_v1()
    approved_delivery_digest_binding = (
        install_full_assessment_delivery_digest_binding_v1()
    )

    return {
        "runtime_revision": RUNTIME_REVISION,
        "canonical_truth_reconciliation": canonical_truth_reconciliation,
        "candidate_identity": candidate_identity,
        "candidate_volume_assurance": candidate_volume_assurance,
        "client_review_companion": client_review_companion,
        "client_pdf_sanitizer": client_pdf_sanitizer,
        "finding_priority_calibration": finding_priority_calibration,
        "client_truth_final": client_truth_final,
        "client_truth_validation_compat": client_truth_validation_compat,
        "manifest_navigation": manifest_navigation,
        "exact_artifact_hash_binding": exact_artifact_hash_binding,
        "artifact_manifest_approval": artifact_manifest_approval,
        "approved_delivery_digest_binding": approved_delivery_digest_binding,
        "bandit_json_execution": bandit_json_execution,
        "source_anchor_location": source_anchor_location,
        "requested_scanner_projection": requested_scanner_projection,
        "final_publication_truth": final_publication_truth,
        "client_readiness": client_readiness,
        "final_register_scanner_truth": final_register_scanner_truth,
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
        "final_register_scanner_truth_reconciled": True,
        "requested_scanner_projection_bound": True,
        "legacy_score_contract_reconciled_before_render": True,
        "existing_report_renderer_preserved": True,
        "existing_visual_design_preserved": True,
        "existing_section_order_preserved": True,
        "report_redesign_performed": False,
        "production_pdf_is_accuracy_acceptance_artifact": True,
        "bandit_csv_parser_dependency_removed": True,
        "bandit_json_artifact_required": True,
        "bandit_problem_dispatch_bound": True,
        "live_scanner_manifest_authoritative": True,
        "unrequested_stale_scanners_excluded_from_coverage": True,
        "missing_requested_scanners_retained_as_incomplete": True,
        "post_authoritative_projection_truth_reconciled": True,
        "full_pdf_text_validated": True,
        "weighted_score_recalculation_required": True,
        "legacy_final_artifact_fixtures_supported": True,
        "blocked_run_recovery_supported": True,
        "failure_checks_visible_to_ui": True,
        "finding_register_deduplicated": True,
        "ranged_source_anchor_paths_canonicalized": True,
        "scanner_state_reconciled": True,
        "authoritative_scanner_records_only": True,
        "analyzer_coverage_canonicalized": True,
        "maturity_terminology_unified": True,
        "identifier_integrity_repaired_before_render": True,
        "limited_evidence_status_separated_from_execution_status": True,
        "canonical_score_contract_reconciled": True,
        "candidate_volume_is_triage_workload_not_defect_severity": True,
        "candidate_dispositions_mutually_exclusive": True,
        "every_raw_candidate_has_stable_identity": True,
        "count_only_candidates_are_individually_auditable": True,
        "workflow_outcome_taxonomy_complete": True,
        "blank_numeric_score_inputs_allowed": False,
        "decision_useful_review_companion_pages": 8,
        "continuous_review_section_numbering": True,
        "continuous_physical_page_labels": True,
        "table_of_contents_present": True,
        "pdf_bookmarks_present": True,
        "filler_only_review_pages_allowed": False,
        "roadmap_claim_is_framework_only": True,
        "runtime_platform_parity_not_assessed_without_device_evidence": True,
        "complexity_alone_creates_p1": False,
        "p1_elevation_rationale_required": True,
        "priority_order_deterministic": True,
        "artifact_manifest_present": True,
        "markdown_and_html_in_manifest": True,
        "all_manifest_hashes_recomputed_from_final_bytes": True,
        "all_manifest_byte_sizes_recomputed_from_final_bytes": True,
        "markdown_manifest_hash_matches_final_bytes": True,
        "html_manifest_hash_matches_final_bytes": True,
        "detached_manifest_hash_matches_final_bytes": True,
        "detached_manifest_binds_final_pdf": True,
        "detached_manifest_binds_canonical_json": True,
        "approved_delivery_bound_to_three_digests": True,
        "digest_mismatch_blocks_delivery": True,
        "reviewer_role_required": True,
        "reviewer_authorization_required": True,
        "regeneration_invalidates_approval": True,
        "review_package_ready": True,
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "RUNTIME_REVISION",
    "VERSION",
    "install_comprehensive_mobile_score_projection_v2",
]
