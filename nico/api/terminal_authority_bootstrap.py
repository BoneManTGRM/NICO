from __future__ import annotations

from nico import snapshot_scanner_worker
from nico.comprehensive_storage_availability_patch_v1 import (
    install_comprehensive_storage_availability_patch_v1,
)

# Storage availability must be guarded before the production Comprehensive app is
# imported. A crashed or temporarily unreachable production database must leave the
# service fail-closed and diagnosable instead of aborting module import.
COMPREHENSIVE_STORAGE_AVAILABILITY = install_comprehensive_storage_availability_patch_v1()

from nico.api.comprehensive_production_bootstrap import app
from nico.ci_history_classification_v1 import install_ci_history_classification_v1
from nico.comprehensive_review_work_existing_app_v1 import (
    install_comprehensive_review_work_existing_app_v1,
)
from nico.comprehensive_terminal_report_language_authority_v83 import (
    install_comprehensive_terminal_report_language_authority_v83,
)
from nico.exact_commit_binding import install_exact_commit_binding
from nico.exact_scanner_checkout_reconciliation_v1 import install_exact_scanner_checkout_reconciliation_v1
from nico.express_failure_stage_truth_v3 import install_express_failure_stage_truth_v3
from nico.express_terminal_authority import install_express_terminal_authority
from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2
from nico.phase6_canonical_truth_v2 import install_phase6_canonical_truth_v2
from nico.phase6_cross_format_repair_v3 import install_phase6_cross_format_repair_v3
from nico.phase6_final_remediation_v1 import install_phase6_final_remediation_v1
from nico.scanner_determinism_v1 import (
    clone_repository_at_snapshot as deterministic_snapshot_clone,
    install_scanner_determinism,
)
from nico.scanner_evidence_pipeline_v1 import install_scanner_evidence_pipeline_v1
from nico.scanner_evidence_qualification_v1 import install_scanner_evidence_qualification_v1
from nico.scorecard_extraction_validation_v1 import install_scorecard_extraction_validation
from nico.v2_scanner_evidence_completion import install_v2_scanner_evidence_completion
from nico.v2_scanner_evidence_context_normalization import install_v2_scanner_evidence_context_normalization
from nico.v2_snapshot_scanner_authority import install_v2_snapshot_scanner_authority
from nico.workflow_supply_chain_policy_v1 import install_workflow_supply_chain_policy_v1

VERSION = "nico.api.terminal_authority_bootstrap.v24"

SCANNER_EVIDENCE_PIPELINE = install_scanner_evidence_pipeline_v1()
V2_SNAPSHOT_SCANNER_AUTHORITY = install_v2_snapshot_scanner_authority()
V2_SCANNER_EVIDENCE_COMPLETION = install_v2_scanner_evidence_completion()
V2_SCANNER_CONTEXT_NORMALIZATION = install_v2_scanner_evidence_context_normalization()
EXACT_COMMIT_BINDING = install_exact_commit_binding()
EXACT_SCANNER_CHECKOUT_RECONCILIATION = install_exact_scanner_checkout_reconciliation_v1()
SCANNER_EVIDENCE_QUALIFICATION = install_scanner_evidence_qualification_v1()
CI_HISTORY_CLASSIFICATION = install_ci_history_classification_v1()
WORKFLOW_SUPPLY_CHAIN_POLICY = install_workflow_supply_chain_policy_v1()
PHASE5_REPORT_TRUTH = install_phase5_report_truth_v2()
PHASE6_FINAL_REMEDIATION = install_phase6_final_remediation_v1()
PHASE6_CANONICAL_TRUTH = install_phase6_canonical_truth_v2()
PHASE6_CROSS_FORMAT_REPAIR = install_phase6_cross_format_repair_v3()
EXPRESS_TERMINAL_AUTHORITY = install_express_terminal_authority()
EXPRESS_FAILURE_STAGE_TRUTH = install_express_failure_stage_truth_v3()
# Install the extraction-order-safe validator after every report and compatibility
# installer. The production API must never fall back to the raw substring gate.
SCORECARD_EXTRACTION_VALIDATION = install_scorecard_extraction_validation()
# Reassert immutable scanner checkout authority after every legacy compatibility
# installer. No later wrapper may reintroduce mutable branches, remotes, or tags.
SCANNER_DETERMINISM = install_scanner_determinism()
snapshot_scanner_worker.clone_repository_at_snapshot = deterministic_snapshot_clone
SCANNER_DETERMINISM = {
    **SCANNER_DETERMINISM,
    "status": "installed",
    "terminal_exact_commit_ancestry_clone_bound": (
        snapshot_scanner_worker.clone_repository_at_snapshot
        is deterministic_snapshot_clone
    ),
    "terminal_binding_order": "after_all_scanner_and_report_compatibility_installers",
}
# Bind Phase 2 after the production Comprehensive routes and late compatibility
# installers are present. This is the terminal reviewer/approval/delivery boundary:
# exact protected review-work routes are added once, approval readiness is fail-closed,
# and approved delivery is normalized to one NICO Comprehensive client report.
PHASE2_REVIEW_WORK = install_comprehensive_review_work_existing_app_v1(app)
# Rebind the shared Comprehensive report-language resolver and the exact final client
# producers/validators after every late production bootstrap installer. This prevents
# a stale root/package English projection from outranking persisted es-MX run identity.
TERMINAL_REPORT_LANGUAGE_AUTHORITY = (
    install_comprehensive_terminal_report_language_authority_v83()
)

_INSTALLATIONS = {
    "nico_comprehensive_storage_availability": COMPREHENSIVE_STORAGE_AVAILABILITY,
    "nico_scanner_evidence_pipeline": SCANNER_EVIDENCE_PIPELINE,
    "nico_v2_snapshot_scanner_authority": V2_SNAPSHOT_SCANNER_AUTHORITY,
    "nico_v2_scanner_evidence_completion": V2_SCANNER_EVIDENCE_COMPLETION,
    "nico_v2_scanner_context_normalization": V2_SCANNER_CONTEXT_NORMALIZATION,
    "nico_exact_commit_binding": EXACT_COMMIT_BINDING,
    "nico_exact_scanner_checkout_reconciliation": EXACT_SCANNER_CHECKOUT_RECONCILIATION,
    "nico_scanner_evidence_qualification": SCANNER_EVIDENCE_QUALIFICATION,
    "nico_ci_history_classification": CI_HISTORY_CLASSIFICATION,
    "nico_workflow_supply_chain_policy": WORKFLOW_SUPPLY_CHAIN_POLICY,
    "nico_phase5_report_truth": PHASE5_REPORT_TRUTH,
    "nico_phase6_final_remediation": PHASE6_FINAL_REMEDIATION,
    "nico_phase6_canonical_truth": PHASE6_CANONICAL_TRUTH,
    "nico_phase6_cross_format_repair": PHASE6_CROSS_FORMAT_REPAIR,
    "nico_express_terminal_authority": EXPRESS_TERMINAL_AUTHORITY,
    "nico_express_failure_stage_truth": EXPRESS_FAILURE_STAGE_TRUTH,
    "nico_scorecard_extraction_validation": SCORECARD_EXTRACTION_VALIDATION,
    "nico_scanner_determinism": SCANNER_DETERMINISM,
    "nico_phase2_review_work": PHASE2_REVIEW_WORK,
    "nico_terminal_report_language_authority": TERMINAL_REPORT_LANGUAGE_AUTHORITY,
}

for state_name, installation in _INSTALLATIONS.items():
    if installation.get("status") not in {"installed", "already_installed"}:
        raise RuntimeError(f"Terminal authority component did not install: {state_name}={installation}")
    setattr(app.state, state_name, installation)

if COMPREHENSIVE_STORAGE_AVAILABILITY.get("startup_database_failure_becomes_blocked_runtime") is not True:
    raise RuntimeError("Comprehensive storage availability does not fail closed at production bootstrap")
if COMPREHENSIVE_STORAGE_AVAILABILITY.get("runtime_database_failure_returns_503") is not True:
    raise RuntimeError("Comprehensive storage availability does not expose bounded runtime failure")
if COMPREHENSIVE_STORAGE_AVAILABILITY.get("automatic_cross_store_fallback") is not False:
    raise RuntimeError("Comprehensive storage availability unexpectedly permits cross-store fallback")
if SCANNER_EVIDENCE_PIPELINE.get("full_output_capture") is not True:
    raise RuntimeError("Scanner evidence pipeline does not retain complete file-backed output")
if SCANNER_EVIDENCE_PIPELINE.get("durable_redacted_raw_artifacts") is not True:
    raise RuntimeError("Scanner evidence pipeline does not retain durable redacted raw artifacts")
if SCANNER_EVIDENCE_PIPELINE.get("frozen_sha_determinism_supported") is not True:
    raise RuntimeError("Scanner evidence pipeline cannot prove repeated execution on an immutable SHA")
if SCANNER_EVIDENCE_PIPELINE.get("public_scanner_tool_api_unchanged") is not True:
    raise RuntimeError("Scanner evidence pipeline unexpectedly replaced the public scanner tool API")
if V2_SNAPSHOT_SCANNER_AUTHORITY.get("bound") is not True:
    raise RuntimeError("Comprehensive snapshot scans are not bound to canonical scanner authority")
if V2_SNAPSHOT_SCANNER_AUTHORITY.get("snapshot_worker_uses_canonical_scanner_runner") is not True:
    raise RuntimeError("Comprehensive snapshot worker still uses the legacy scanner runner")
if V2_SNAPSHOT_SCANNER_AUTHORITY.get("raw_artifacts_retained_before_workspace_deletion") is not True:
    raise RuntimeError("Comprehensive scanner artifacts are not retained before temporary workspace deletion")
if V2_SNAPSHOT_SCANNER_AUTHORITY.get("full_history_restoration_bound") is not True:
    raise RuntimeError("History-aware secret scans are not bound to exact-commit ancestry restoration")
if V2_SCANNER_EVIDENCE_COMPLETION.get("bound") is not True:
    raise RuntimeError("Scanner evidence completion is not bound to the production snapshot worker")
if V2_SCANNER_EVIDENCE_COMPLETION.get("osv_package_version_path_context_retained") is not True:
    raise RuntimeError("OSV evidence loses package, installed-version, or dependency-path context")
if V2_SCANNER_EVIDENCE_COMPLETION.get("full_object_store_repacked_and_verified") is not True:
    raise RuntimeError("History-aware scanners are not bound to a verified complete Git object store")
if V2_SCANNER_EVIDENCE_COMPLETION.get("trufflehog_internal_clone_supported") is not True:
    raise RuntimeError("TruffleHog remains bound to a partial or lazy Git object store")
if V2_SCANNER_CONTEXT_NORMALIZATION.get("bound") is not True:
    raise RuntimeError("Nested OSV source and manifest context is not normalized")
if V2_SCANNER_CONTEXT_NORMALIZATION.get("nested_source_path_normalized") is not True:
    raise RuntimeError("Nested OSV source paths are not retained as canonical dependency paths")
if EXACT_COMMIT_BINDING.get("repository_files_bound_to_exact_commit") is not True:
    raise RuntimeError("Repository file evidence is not bound to the exact immutable commit")
if EXACT_COMMIT_BINDING.get("scanner_bound_to_exact_commit") is not True:
    raise RuntimeError("Scanner execution is not bound to the exact immutable commit")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("checkout_identity_retained") is not True:
    raise RuntimeError("Hosted scanner checkout identity is still discarded")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("exact_sha_match_required") is not True:
    raise RuntimeError("Exact scanner reconciliation does not require the assessed SHA")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("mismatched_or_untrusted_artifacts_blocked") is not True:
    raise RuntimeError("Mismatched or untrusted scanner artifacts are not blocked")
if SCANNER_DETERMINISM.get("terminal_exact_commit_ancestry_clone_bound") is not True:
    raise RuntimeError("A late compatibility installer replaced exact-commit scanner checkout authority")
if snapshot_scanner_worker.clone_repository_at_snapshot is not deterministic_snapshot_clone:
    raise RuntimeError("Terminal scanner checkout is not the immutable exact-SHA ancestry clone")
if SCORECARD_EXTRACTION_VALIDATION.get("column_extraction_order_independent") is not True:
    raise RuntimeError("Production scorecard validation still depends on PDF column extraction order")
if SCORECARD_EXTRACTION_VALIDATION.get("multi_page_scorecard_supported") is not True:
    raise RuntimeError("Production scorecard validation does not support continuation pages")
if SCORECARD_EXTRACTION_VALIDATION.get("all_canonical_rows_and_scores_required") is not True:
    raise RuntimeError("Production scorecard validation does not fail closed on missing canonical rows")
if SCORECARD_EXTRACTION_VALIDATION.get("spanish_and_english_supported") is not True:
    raise RuntimeError("Production scorecard validation is not bound for both report languages")
if PHASE2_REVIEW_WORK.get("review_work_get_route_count") != 1:
    raise RuntimeError("Phase 2 review-work GET route is not bound exactly once")
if PHASE2_REVIEW_WORK.get("review_work_post_route_count") != 1:
    raise RuntimeError("Phase 2 review-work POST route is not bound exactly once")
if PHASE2_REVIEW_WORK.get("protected_admin_authorization") is not True:
    raise RuntimeError("Phase 2 review-work routes are not protected by admin authorization")
if PHASE2_REVIEW_WORK.get("bulk_review_fails_closed_for_individual_attention") is not True:
    raise RuntimeError("Phase 2 grouped human disposition does not fail closed")
if PHASE2_REVIEW_WORK.get("report_truth_synchronized_before_approval") is not True:
    raise RuntimeError("Phase 2 report truth is not synchronized before final approval")
if PHASE2_REVIEW_WORK.get("approved_delivery_has_one_client_report") is not True:
    raise RuntimeError("Phase 2 approved delivery is not bound to one Comprehensive client report")
if PHASE2_REVIEW_WORK.get("human_review_required") is not True:
    raise RuntimeError("Phase 2 must preserve human review")
if PHASE2_REVIEW_WORK.get("client_delivery_allowed") is not False:
    raise RuntimeError("Phase 2 must block client delivery before authorized approval")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("persisted_run_identity_outranks_root_projection") is not True:
    raise RuntimeError("Terminal report language does not preserve persisted run identity")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("stale_root_english_probe_resolves_es_MX") is not True:
    raise RuntimeError("Terminal report language allows stale English projection to outrank es-MX")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("independent_markdown_html_pdf_validation") is not True:
    raise RuntimeError("Terminal report language does not validate every final client surface")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("mixed_language_structural_markers_fail_closed") is not True:
    raise RuntimeError("Terminal report language does not reject mixed CI/CD structure")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("human_review_required") is not True:
    raise RuntimeError("Terminal report language authority must preserve human review")
if TERMINAL_REPORT_LANGUAGE_AUTHORITY.get("client_delivery_allowed") is not False:
    raise RuntimeError("Terminal report language authority must block unapproved client delivery")

_REQUIRED_TRUTH_FLAGS = {
    "PHASE6_FINAL_REMEDIATION": (
        PHASE6_FINAL_REMEDIATION,
        "phase_numbered_customer_sections_removed",
        "express_comparison_customer_language_removed",
        "canonical_finding_identity",
        "idempotent_report_filename",
    ),
    "PHASE6_CANONICAL_TRUTH": (
        PHASE6_CANONICAL_TRUTH,
        "canonical_model_precedes_all_renderers",
        "cross_format_truth_build_gate",
        "language_factual_parity_projection",
    ),
    "PHASE6_CROSS_FORMAT_REPAIR": (
        PHASE6_CROSS_FORMAT_REPAIR,
        "canonical_json_and_csv_projection_reconciled",
        "completed_scanners_visible_in_markdown_and_html",
        "terminal_filename_recomputed_after_truth_validation",
    ),
}
for component, values in _REQUIRED_TRUTH_FLAGS.items():
    installation, *flags = values
    missing = [flag for flag in flags if installation.get(flag) is not True]
    if missing:
        raise RuntimeError(f"{component} is missing required truth controls: {missing}")
    if installation.get("human_review_required") is not True:
        raise RuntimeError(f"{component} must preserve human review")
    if installation.get("client_delivery_allowed") is not False:
        raise RuntimeError(f"{component} must block unapproved client delivery")

__all__ = [
    "app",
    "COMPREHENSIVE_STORAGE_AVAILABILITY",
    "SCANNER_EVIDENCE_PIPELINE",
    "V2_SNAPSHOT_SCANNER_AUTHORITY",
    "V2_SCANNER_EVIDENCE_COMPLETION",
    "V2_SCANNER_CONTEXT_NORMALIZATION",
    "EXACT_COMMIT_BINDING",
    "EXACT_SCANNER_CHECKOUT_RECONCILIATION",
    "SCANNER_EVIDENCE_QUALIFICATION",
    "CI_HISTORY_CLASSIFICATION",
    "WORKFLOW_SUPPLY_CHAIN_POLICY",
    "PHASE5_REPORT_TRUTH",
    "PHASE6_FINAL_REMEDIATION",
    "PHASE6_CANONICAL_TRUTH",
    "PHASE6_CROSS_FORMAT_REPAIR",
    "EXPRESS_TERMINAL_AUTHORITY",
    "EXPRESS_FAILURE_STAGE_TRUTH",
    "SCORECARD_EXTRACTION_VALIDATION",
    "SCANNER_DETERMINISM",
    "PHASE2_REVIEW_WORK",
    "TERMINAL_REPORT_LANGUAGE_AUTHORITY",
    "VERSION",
]
