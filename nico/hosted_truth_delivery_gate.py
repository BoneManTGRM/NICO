from __future__ import annotations

from typing import Any


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


def patch_client_acceptance_gate_for_report_truth() -> None:
    """Patch the final hosted gate without conflating run completion and delivery.

    Express, Mid, and Full can finish automated evidence collection, scoring, and
    artifact generation while remaining blocked from client delivery pending
    human review. Missing report formats, score, or sections still fail closed.
    """

    from nico import client_acceptance
    from nico.express_final_gate_completion_patch import normalize_assessment_completion

    original = getattr(client_acceptance, "_nico_original_attach_client_acceptance_gate", None)
    if original is None:
        original = client_acceptance.attach_client_acceptance_gate
        client_acceptance._nico_original_attach_client_acceptance_gate = original

    def attach_client_acceptance_gate_with_report_truth(result: dict[str, Any]) -> dict[str, Any]:
        accepted = original(result)
        gated = apply_final_hosted_truth_gate(accepted)
        return normalize_assessment_completion(accepted, gated)

    client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth
