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
    from nico.report_final_qa import apply_final_report_qa
    from nico.report_score_lift_plan import attach_score_lift_plan
    from nico.report_truth_runtime_patch import (
        apply_dependency_score_consistency,
        rebuild_reports,
        refresh_project_trend_score,
    )
    from nico.report_truth_status import build_report_truth_status
    from nico.service_tier_workflows import attach_service_tier_workflows

    result = apply_dependency_score_consistency(result)
    result = apply_final_report_qa(result)
    result = refresh_project_trend_score(result)
    result = attach_score_lift_plan(result)
    result = attach_service_tier_workflows(result)
    result["report_truth_guard"] = build_report_truth_status()
    return rebuild_reports(result)


def patch_client_acceptance_gate_for_report_truth() -> None:
    """Patch the last function used by POST /assessment/github.

    This avoids relying only on final_report_consistency monkey patching. The API
    route calls attach_client_acceptance_gate after finalization, so this is the
    final stable hook before the result is stored and returned to the frontend.
    """

    from nico import client_acceptance

    original = getattr(client_acceptance, "_nico_original_attach_client_acceptance_gate", None)
    if original is None:
        original = client_acceptance.attach_client_acceptance_gate
        client_acceptance._nico_original_attach_client_acceptance_gate = original

    def attach_client_acceptance_gate_with_report_truth(result: dict[str, Any]) -> dict[str, Any]:
        return apply_final_hosted_truth_gate(original(result))

    client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth
