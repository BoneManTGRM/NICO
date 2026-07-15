from __future__ import annotations

from importlib import import_module
import sys
from typing import Any, Callable

PATCH_VERSION = "nico.express_completion_score_binding.v3"
_RESPONSE_MARKER = "_nico_express_completion_score_response_v3"
_EXECUTE_MARKER = "_nico_express_completion_score_execute_v1"
_BOOTSTRAP_MARKER = "_nico_express_completion_score_bootstrap_v1"
_QUALITY_HEADING = "## Repository Quality and Governance Signals"
_REPAIR_HEADING = "## Prioritized Repair Intelligence"
_NON_REPAIR_SECTION_IDS = {"trust_readiness", "client_acceptance"}


def _final_repair_source(finalized: dict[str, Any]) -> dict[str, Any]:
    source = dict(finalized)
    source["sections"] = [
        section
        for section in finalized.get("sections", []) or []
        if isinstance(section, dict)
        and str(section.get("id") or "") not in _NON_REPAIR_SECTION_IDS
    ]
    return source


def _final_quality_findings(finalized: dict[str, Any]) -> list[dict[str, Any]]:
    quality = finalized.get("repository_quality_signals")
    if not isinstance(quality, dict):
        return []
    return [
        item
        for item in quality.get("findings", []) or []
        if isinstance(item, dict)
    ]


def finalize_report_intelligence_at_response(value: Any) -> Any:
    """Attach, reconcile, and export report intelligence at the last response boundary.

    Repair candidates are rebuilt from the final reconciled section findings and the
    verified repository-quality findings. Early regex candidates, stale pre-polish
    wording, and superseded scanner observations cannot survive merely because an
    earlier assessment stage produced them. The finalizer never edits the assessed
    repository and never marks a proposed repair as verified or applied.
    """

    if not isinstance(value, dict) or value.get("status") != "complete" or not value.get("repository"):
        return value

    from nico import hosted_assessment as hosted
    from nico import hosted_report_intelligence_enrichment as enrichment
    from nico import report_intelligence_accuracy_patch as accuracy
    from nico.report_repair_intelligence import build_report_repair_intelligence

    original_score = (
        value.get("maturity_signal", {}).get("score")
        if isinstance(value.get("maturity_signal"), dict)
        else None
    )
    finalized = dict(value)
    prior_repairs = finalized.get("repair_intelligence")
    prior_candidate_count = (
        int(prior_repairs.get("candidate_count") or 0)
        if isinstance(prior_repairs, dict)
        else 0
    )

    if not isinstance(finalized.get("repository_quality_signals"), dict):
        finalized = enrichment.enrich_hosted_result(hosted, finalized)

    quality_findings = _final_quality_findings(finalized)
    repair_source = _final_repair_source(finalized)
    final_repairs = build_report_repair_intelligence(
        repair_source,
        structured_findings=quality_findings,
    )
    finalized["repair_intelligence"] = final_repairs
    finalized["repairs"] = [
        str(item.get("recommended_action"))
        for item in final_repairs.get("candidates", [])[:10]
        if isinstance(item, dict) and item.get("recommended_action")
    ]
    finalized["repair_intelligence_reconciliation"] = {
        "status": "reconciled",
        "source": "final_reconciled_sections_and_verified_repository_quality_findings",
        "excluded_workflow_only_sections": sorted(_NON_REPAIR_SECTION_IDS),
        "prior_candidate_count": prior_candidate_count,
        "final_candidate_count": int(final_repairs.get("candidate_count") or 0),
        "final_code_suggestion_count": int(final_repairs.get("code_suggestion_count") or 0),
        "early_source_regex_candidates_carried_forward": False,
        "superseded_pre_polish_findings_carried_forward": False,
        "human_review_required": True,
        "automatic_application_allowed": False,
    }

    # Rebuild unconditionally because final candidate reconciliation changes the
    # client-visible repair section even when an earlier export already had headings.
    finalized = accuracy.rebuild_enriched_reports(hosted, finalized)
    reports = finalized.get("reports") if isinstance(finalized.get("reports"), dict) else {}
    markdown = str(reports.get("markdown") or "")

    quality_present = isinstance(finalized.get("repository_quality_signals"), dict)
    repairs_present = isinstance(finalized.get("repair_intelligence"), dict)
    quality_exported = _QUALITY_HEADING in markdown
    repairs_exported = _REPAIR_HEADING in markdown
    candidate_count = int(final_repairs.get("candidate_count") or 0)
    code_suggestion_count = int(final_repairs.get("code_suggestion_count") or 0)

    final_score = (
        finalized.get("maturity_signal", {}).get("score")
        if isinstance(finalized.get("maturity_signal"), dict)
        else None
    )
    finalized["report_intelligence_export"] = {
        "status": "complete" if quality_present and repairs_present and quality_exported and repairs_exported else "incomplete",
        "final_response_boundary_applied": True,
        "repair_intelligence_reconciled_from_final_findings": True,
        "repository_quality_signals_attached": quality_present,
        "repair_intelligence_attached": repairs_present,
        "repository_quality_markdown_exported": quality_exported,
        "repair_intelligence_markdown_exported": repairs_exported,
        "repair_candidate_count": candidate_count,
        "code_suggestion_count": code_suggestion_count,
        "score_before": original_score,
        "score_after": final_score,
        "score_changed": original_score != final_score,
        "mode": "report_only",
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
    }
    finalized["human_review_required"] = True
    finalized["client_ready"] = False
    return finalized


def bind_api_main_response(api_main: Any) -> dict[str, Any]:
    """Bind score and report reconciliation to the final response boundary."""

    current = getattr(api_main, "safe_assessment_response_payload", None)
    if not callable(current):
        return {
            "status": "unavailable",
            "reason": "safe_assessment_response_payload_not_loaded",
        }
    if getattr(current, _RESPONSE_MARKER, False):
        return {
            "status": "already_installed",
            "response_boundary_reconciled": True,
            "report_intelligence_export_bound": True,
        }
    original: Callable[[Any], dict[str, Any]] = current

    def safe_response_with_final_reconciliation(value: Any) -> dict[str, Any]:
        from nico.post_polish_score_reconciliation_patch import reconcile_after_polish

        reconciled = (
            reconcile_after_polish(value)
            if isinstance(value, dict) and value.get("status") == "complete"
            else value
        )
        finalized = finalize_report_intelligence_at_response(reconciled)
        return original(finalized)

    setattr(safe_response_with_final_reconciliation, _RESPONSE_MARKER, True)
    setattr(safe_response_with_final_reconciliation, "_nico_previous", original)
    api_main.safe_assessment_response_payload = safe_response_with_final_reconciliation
    return {
        "status": "installed",
        "response_boundary_reconciled": True,
        "report_intelligence_export_bound": True,
    }


def _patch_async_execute() -> dict[str, Any]:
    from nico import express_async_api

    current = express_async_api._execute
    if getattr(current, _EXECUTE_MARKER, False):
        return {
            "status": "already_installed",
            "async_execute_bound": True,
        }
    original = current

    def execute_with_final_response_binding(
        run_id: str,
        request_payload: dict[str, Any],
    ) -> None:
        api_main = import_module("nico.api.main")
        bind_api_main_response(api_main)
        original(run_id, request_payload)

    setattr(execute_with_final_response_binding, _EXECUTE_MARKER, True)
    setattr(execute_with_final_response_binding, "_nico_previous", original)
    express_async_api._execute = execute_with_final_response_binding
    return {
        "status": "installed",
        "async_execute_bound": True,
    }


def _patch_production_bootstrap() -> dict[str, Any]:
    from nico import assessment_score_integrity

    current = assessment_score_integrity.install_assessment_score_integrity
    if getattr(current, _BOOTSTRAP_MARKER, False):
        return {
            "status": "already_installed",
            "production_bootstrap_bound": True,
        }
    original = current

    def install_score_integrity_with_response_binding() -> dict[str, Any]:
        result = original()
        api_main = import_module("nico.api.main")
        binding = bind_api_main_response(api_main)
        if isinstance(result, dict):
            enriched = dict(result)
            enriched["express_completion_score_binding"] = binding
            return enriched
        return {
            "status": "installed",
            "score_integrity_result_type": type(result).__name__,
            "express_completion_score_binding": binding,
        }

    setattr(install_score_integrity_with_response_binding, _BOOTSTRAP_MARKER, True)
    setattr(install_score_integrity_with_response_binding, "_nico_previous", original)
    assessment_score_integrity.install_assessment_score_integrity = install_score_integrity_with_response_binding
    return {
        "status": "installed",
        "production_bootstrap_bound": True,
    }


def install_express_completion_score_binding() -> dict[str, Any]:
    bootstrap = _patch_production_bootstrap()
    async_execute = _patch_async_execute()

    immediate = {
        "status": "not_loaded",
        "reason": "nico.api.main_not_loaded_during_package_install",
    }
    api_main = sys.modules.get("nico.api.main")
    if api_main is not None:
        immediate = bind_api_main_response(api_main)

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "production_bootstrap": bootstrap,
        "async_execute": async_execute,
        "immediate_api_binding": immediate,
        "final_response_boundary": "safe_assessment_response_payload",
        "report_intelligence_export_bound": True,
        "repair_intelligence_reconciled_from_final_findings": True,
        "score_inflation_allowed": False,
        "guardrail": (
            "The response-bound reconciliation and report export can only use final evidence present in, or fetched for, "
            "the authorized completed assessment. They cannot edit the assessed repository, retain contradicted early "
            "candidates, create scanner proof, invent test evidence, fabricate acceptance, bypass human approval, or set "
            "client-ready state."
        ),
    }


__all__ = [
    "PATCH_VERSION",
    "bind_api_main_response",
    "finalize_report_intelligence_at_response",
    "install_express_completion_score_binding",
]
