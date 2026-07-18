from __future__ import annotations

from typing import Any
from uuid import uuid4

_PATCH_MARKER = "_nico_hosted_truth_completion_bound_v3"
_STORAGE_PATCH_MARKER = "_nico_assessment_storage_truth_bound_v1"


def apply_final_hosted_truth_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Apply report truth guards at the last hosted delivery step.

    The hosted API endpoint imports several functions directly. This final gate
    runs after client-acceptance attachment so the returned JSON plus Markdown,
    HTML, and PDF exports are rebuilt from the same corrected result state.
    """

    if result.get("status") != "complete":
        return result
    from nico.bandit_triage_workflow import attach_bandit_triage_to_report
    from nico.complexity_artifact_integration import attach_complexity_artifact_to_report
    from nico.evidence_ledger import attach_evidence_ledger
    from nico.export_truth_gate import apply_export_truth_gate
    from nico.hosted_full_evidence_runtime_v2 import ensure_hosted_runtime_evidence
    from nico.report_evidence_consistency_runtime import apply_report_evidence_consistency_gate
    from nico.report_final_qa import apply_final_report_qa
    from nico.report_pdf_display_patch import apply_pdf_display_patch
    from nico.report_presentation_normalization import normalize_report_presentation_lists
    from nico.report_score_lift_plan import attach_score_lift_plan
    from nico.report_truth_runtime_patch import (
        apply_dependency_score_consistency,
        rebuild_reports,
        refresh_project_trend_score,
    )
    from nico.report_truth_status import build_report_truth_status
    from nico.scanner_artifact_integration import attach_scanner_artifacts_to_report
    from nico.scanner_score_lifts import apply_verified_scanner_score_lifts
    from nico.service_tier_workflows import attach_service_tier_workflows
    from nico.trust_engine import apply_strict_trust_engine
    from nico.trust_report_display import attach_trust_report_display

    result = apply_dependency_score_consistency(result)
    result = ensure_hosted_runtime_evidence(result)
    result = attach_scanner_artifacts_to_report(result)
    result = attach_bandit_triage_to_report(result)
    result = attach_complexity_artifact_to_report(result)
    result = apply_verified_scanner_score_lifts(result)
    result = apply_report_evidence_consistency_gate(result)
    result = apply_final_report_qa(result)
    result = ensure_hosted_runtime_evidence(result)
    result = attach_scanner_artifacts_to_report(result)
    result = attach_bandit_triage_to_report(result)
    result = attach_complexity_artifact_to_report(result)
    result = apply_verified_scanner_score_lifts(result)
    result = apply_report_evidence_consistency_gate(result)
    result = apply_strict_trust_engine(result)
    result = apply_report_evidence_consistency_gate(result)
    result = attach_evidence_ledger(result)
    result = refresh_project_trend_score(result)
    result = attach_score_lift_plan(result)
    result = attach_service_tier_workflows(result)
    result["report_truth_guard"] = build_report_truth_status()
    result = attach_trust_report_display(result)
    result = normalize_report_presentation_lists(result)
    apply_pdf_display_patch()
    result = rebuild_reports(result)
    result = apply_export_truth_gate(result)
    result = normalize_report_presentation_lists(result)
    return attach_trust_report_display(result)


def _latest_assessment_result(api_main: Any, workflow: str) -> dict[str, Any]:
    source_by_workflow = {
        "express": "_LAST_HOSTED_ASSESSMENT",
        "mid": "_LAST_MID_ASSESSMENT",
        "retainer": "_LAST_RETAINER_OPS",
        "full": "_LAST_FULL_ASSESSMENT",
    }
    source_name = source_by_workflow.get(str(workflow).lower(), "")
    value = getattr(api_main, source_name, {}) if source_name else {}
    return value if isinstance(value, dict) else {}


def _patch_assessment_storage_truth(api_main: Any) -> None:
    """Preserve run history and persist the actual terminal state for every tier."""

    current = api_main.assessment_storage_record
    if getattr(current, _STORAGE_PATCH_MARKER, False):
        return

    def truthful_assessment_storage_record(req: Any, workflow: str) -> tuple[str, dict[str, Any]]:
        customer_id = str(getattr(req, "customer_id", "default_customer") or "default_customer")
        project_id = str(getattr(req, "project_id", "default_project") or "default_project")
        repository = str(getattr(req, "repository", "") or "")
        result = _latest_assessment_result(api_main, workflow)
        status = str(result.get("status") or "unknown")
        run_id = str(
            result.get("run_id")
            or result.get("assessment_id")
            or result.get("report_id")
            or result.get("scan_id")
            or uuid4().hex
        )
        record_id = f"{workflow}_{customer_id}_{project_id}_{run_id}"
        payload = {
            "status": status,
            "workflow": workflow,
            "tier": workflow,
            "run_id": run_id,
            "repository": repository or str(result.get("repository") or ""),
            "customer_id": customer_id,
            "project_id": project_id,
        }
        return record_id, {
            "workflow": workflow,
            "customer_id": customer_id,
            "project_id": project_id,
            "run_id": run_id,
            "status": status,
            "payload": payload,
        }

    setattr(truthful_assessment_storage_record, _STORAGE_PATCH_MARKER, True)
    setattr(truthful_assessment_storage_record, "_nico_previous", current)
    api_main.assessment_storage_record = truthful_assessment_storage_record


def patch_client_acceptance_gate_for_report_truth() -> None:
    """Bind the final completion wrapper to the current production gate.

    This function is intentionally safe to call again after all other installers.
    Later runtime patches mutate ``nico.client_acceptance`` first, while the API
    module can retain an older directly imported reference. Re-entry therefore
    wraps the current module function and then synchronizes the API reference.
    """

    from nico import client_acceptance
    from nico.api import main as api_main
    from nico.express_final_gate_completion_patch import normalize_assessment_completion

    _patch_assessment_storage_truth(api_main)

    current = client_acceptance.attach_client_acceptance_gate
    if getattr(current, _PATCH_MARKER, False):
        api_main.attach_client_acceptance_gate = current
        return

    if not hasattr(client_acceptance, "_nico_original_attach_client_acceptance_gate"):
        client_acceptance._nico_original_attach_client_acceptance_gate = current

    def attach_client_acceptance_gate_with_report_truth(result: dict[str, Any]) -> dict[str, Any]:
        accepted = current(result)
        gated = apply_final_hosted_truth_gate(accepted)
        return normalize_assessment_completion(accepted, gated)

    setattr(attach_client_acceptance_gate_with_report_truth, _PATCH_MARKER, True)
    setattr(attach_client_acceptance_gate_with_report_truth, "_nico_previous", current)
    client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth
    api_main.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth
