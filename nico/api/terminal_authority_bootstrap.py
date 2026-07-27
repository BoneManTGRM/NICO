from __future__ import annotations

from nico.api.comprehensive_production_bootstrap import app
from nico.scanner_evidence_pipeline_v1 import install_scanner_evidence_pipeline_v1
from nico.scanner_evidence_qualification_v1 import install_scanner_evidence_qualification_v1
from nico.exact_commit_binding import install_exact_commit_binding
from nico.exact_scanner_checkout_reconciliation_v1 import (
    install_exact_scanner_checkout_reconciliation_v1,
)
from nico.express_failure_stage_truth_v3 import install_express_failure_stage_truth_v3
from nico.express_terminal_authority import install_express_terminal_authority

VERSION = "nico.api.terminal_authority_bootstrap.v7"
SCANNER_EVIDENCE_PIPELINE = install_scanner_evidence_pipeline_v1()
EXACT_COMMIT_BINDING = install_exact_commit_binding()
EXACT_SCANNER_CHECKOUT_RECONCILIATION = install_exact_scanner_checkout_reconciliation_v1()
SCANNER_EVIDENCE_QUALIFICATION = install_scanner_evidence_qualification_v1()
EXPRESS_TERMINAL_AUTHORITY = install_express_terminal_authority()
EXPRESS_FAILURE_STAGE_TRUTH = install_express_failure_stage_truth_v3()
app.state.nico_scanner_evidence_pipeline = SCANNER_EVIDENCE_PIPELINE
app.state.nico_exact_commit_binding = EXACT_COMMIT_BINDING
app.state.nico_exact_scanner_checkout_reconciliation = EXACT_SCANNER_CHECKOUT_RECONCILIATION
app.state.nico_scanner_evidence_qualification = SCANNER_EVIDENCE_QUALIFICATION
app.state.nico_express_terminal_authority = EXPRESS_TERMINAL_AUTHORITY
app.state.nico_express_failure_stage_truth = EXPRESS_FAILURE_STAGE_TRUTH

if SCANNER_EVIDENCE_PIPELINE.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError(f"Scanner evidence pipeline did not install: {SCANNER_EVIDENCE_PIPELINE}")
if SCANNER_EVIDENCE_PIPELINE.get("full_output_capture") is not True:
    raise RuntimeError("Scanner evidence pipeline does not retain complete file-backed output")
if SCANNER_EVIDENCE_PIPELINE.get("durable_redacted_raw_artifacts") is not True:
    raise RuntimeError("Scanner evidence pipeline does not retain redacted raw artifacts durably")
if SCANNER_EVIDENCE_PIPELINE.get("frozen_sha_determinism_supported") is not True:
    raise RuntimeError("Scanner evidence pipeline cannot prove repeated execution on an immutable SHA")
if SCANNER_EVIDENCE_PIPELINE.get("public_scanner_tool_api_unchanged") is not True:
    raise RuntimeError("Scanner evidence pipeline unexpectedly replaced the public scanner API")

if EXACT_COMMIT_BINDING.get("status") != "installed":
    raise RuntimeError(f"Exact commit binding did not install: {EXACT_COMMIT_BINDING}")
if EXACT_COMMIT_BINDING.get("repository_files_bound_to_exact_commit") is not True:
    raise RuntimeError("Repository file evidence is not bound to the exact immutable commit")
if EXACT_COMMIT_BINDING.get("scanner_bound_to_exact_commit") is not True:
    raise RuntimeError("Scanner execution is not bound to the exact immutable commit")
if EXACT_COMMIT_BINDING.get("conflicting_commit_metadata_authoritative") is not False:
    raise RuntimeError("Conflicting derived commit metadata can still replace verified commit truth")
if EXACT_COMMIT_BINDING.get("human_review_required") is not True:
    raise RuntimeError("Exact commit binding must preserve required human review")
if EXACT_COMMIT_BINDING.get("client_delivery_allowed") is not False:
    raise RuntimeError("Exact commit binding must block client delivery")

if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError(
        "Exact scanner checkout reconciliation did not install: "
        f"{EXACT_SCANNER_CHECKOUT_RECONCILIATION}"
    )
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("checkout_identity_retained") is not True:
    raise RuntimeError("Hosted scanner checkout identity is still discarded during normalization")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("completed_autorun_required") is not True:
    raise RuntimeError("Exact scanner reconciliation can accept a non-completed or external artifact")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("exact_sha_match_required") is not True:
    raise RuntimeError("Exact scanner reconciliation can accept a mismatched checkout SHA")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("mismatched_or_untrusted_artifacts_blocked") is not True:
    raise RuntimeError("Mismatched or untrusted scanner artifacts are not fail-closed")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("human_review_required") is not True:
    raise RuntimeError("Exact scanner reconciliation must preserve required human review")
if EXACT_SCANNER_CHECKOUT_RECONCILIATION.get("client_delivery_allowed") is not False:
    raise RuntimeError("Exact scanner reconciliation must block client delivery")

if SCANNER_EVIDENCE_QUALIFICATION.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError(f"Scanner evidence qualification did not install: {SCANNER_EVIDENCE_QUALIFICATION}")
if SCANNER_EVIDENCE_QUALIFICATION.get("blocking_tool_diagnostics") is not True:
    raise RuntimeError("Scanner evidence qualification does not expose blocking-tool diagnostics")
if SCANNER_EVIDENCE_QUALIFICATION.get("retained_artifact_integrity_required") is not True:
    raise RuntimeError("Scanner evidence qualification does not require retained artifact integrity")
if SCANNER_EVIDENCE_QUALIFICATION.get("exact_commit_provenance_required") is not True:
    raise RuntimeError("Scanner evidence qualification does not require exact-commit provenance")
if SCANNER_EVIDENCE_QUALIFICATION.get("missing_evidence_is_not_clean") is not True:
    raise RuntimeError("Scanner evidence qualification can still represent missing evidence as clean")
if SCANNER_EVIDENCE_QUALIFICATION.get("client_delivery_blocked_when_incomplete") is not True:
    raise RuntimeError("Scanner evidence qualification does not block incomplete client delivery")

if EXPRESS_TERMINAL_AUTHORITY.get("status") != "installed":
    raise RuntimeError(f"Express terminal authority did not install: {EXPRESS_TERMINAL_AUTHORITY}")
if EXPRESS_TERMINAL_AUTHORITY.get("compact_terminal_precedes_rich_record") is not True:
    raise RuntimeError("Express compact terminal evidence is not persisted before the rich record")
if EXPRESS_TERMINAL_AUTHORITY.get("exact_run_readback_required") is not True:
    raise RuntimeError("Express exact-run terminal readback is not required")
if EXPRESS_TERMINAL_AUTHORITY.get("browser_terminalization_from_active_status_allowed") is not False:
    raise RuntimeError("Active backend status can still be terminalized by the browser")
if EXPRESS_TERMINAL_AUTHORITY.get("human_review_required") is not True:
    raise RuntimeError("Express terminal authority must require human review")
if EXPRESS_TERMINAL_AUTHORITY.get("client_delivery_allowed") is not False:
    raise RuntimeError("Express terminal authority must block client delivery")

if EXPRESS_FAILURE_STAGE_TRUTH.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError(f"Express failure-stage truth did not install: {EXPRESS_FAILURE_STAGE_TRUTH}")
if EXPRESS_FAILURE_STAGE_TRUTH.get("actual_failure_stage_preserved") is not True:
    raise RuntimeError("Express terminal failures can still erase the actual failed stage")
if EXPRESS_FAILURE_STAGE_TRUTH.get("backend_stage_mapped_to_ui_stage") is not True:
    raise RuntimeError("Express backend diagnostic stages are not mapped to the truthful UI stage")
if EXPRESS_FAILURE_STAGE_TRUTH.get("later_pending_stages_remain_pending") is not True:
    raise RuntimeError("Express terminal failures can still relabel later pending stages as failed")
if EXPRESS_FAILURE_STAGE_TRUTH.get("safe_failure_code_exposed") is not True:
    raise RuntimeError("Express terminal failures do not expose a bounded safe failure code")
if EXPRESS_FAILURE_STAGE_TRUTH.get("human_review_required") is not True:
    raise RuntimeError("Express failure-stage truth must preserve required human review")
if EXPRESS_FAILURE_STAGE_TRUTH.get("client_delivery_allowed") is not False:
    raise RuntimeError("Express failure-stage truth must block client delivery")

__all__ = [
    "app",
    "SCANNER_EVIDENCE_PIPELINE",
    "EXACT_COMMIT_BINDING",
    "EXACT_SCANNER_CHECKOUT_RECONCILIATION",
    "SCANNER_EVIDENCE_QUALIFICATION",
    "EXPRESS_TERMINAL_AUTHORITY",
    "EXPRESS_FAILURE_STAGE_TRUTH",
    "VERSION",
]
