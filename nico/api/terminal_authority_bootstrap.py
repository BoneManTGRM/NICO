from __future__ import annotations

from nico.api.comprehensive_production_bootstrap import app
from nico.ci_history_classification_v1 import install_ci_history_classification_v1
from nico.exact_commit_binding import install_exact_commit_binding
from nico.exact_scanner_checkout_reconciliation_v1 import install_exact_scanner_checkout_reconciliation_v1
from nico.express_failure_stage_truth_v3 import install_express_failure_stage_truth_v3
from nico.express_terminal_authority import install_express_terminal_authority
from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2
from nico.phase6_canonical_truth_v2 import install_phase6_canonical_truth_v2
from nico.phase6_cross_format_repair_v3 import install_phase6_cross_format_repair_v3
from nico.phase6_final_remediation_v1 import install_phase6_final_remediation_v1
from nico.scanner_evidence_pipeline_v1 import install_scanner_evidence_pipeline_v1
from nico.scanner_evidence_qualification_v1 import install_scanner_evidence_qualification_v1
from nico.v2_snapshot_scanner_authority import install_v2_snapshot_scanner_authority
from nico.workflow_supply_chain_policy_v1 import install_workflow_supply_chain_policy_v1

VERSION = "nico.api.terminal_authority_bootstrap.v17"

SCANNER_EVIDENCE_PIPELINE = install_scanner_evidence_pipeline_v1()
V2_SNAPSHOT_SCANNER_AUTHORITY = install_v2_snapshot_scanner_authority()
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

_INSTALLATIONS = {
    "nico_scanner_evidence_pipeline": SCANNER_EVIDENCE_PIPELINE,
    "nico_v2_snapshot_scanner_authority": V2_SNAPSHOT_SCANNER_AUTHORITY,
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
}

for state_name, installation in _INSTALLATIONS.items():
    if installation.get("status") not in {"installed", "already_installed"}:
        raise RuntimeError(f"Terminal authority component did not install: {state_name}={installation}")
    setattr(app.state, state_name, installation)

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
    raise RuntimeError("History-aware secret scans are not bound to full-history restoration")
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
    "SCANNER_EVIDENCE_PIPELINE",
    "V2_SNAPSHOT_SCANNER_AUTHORITY",
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
    "VERSION",
]
