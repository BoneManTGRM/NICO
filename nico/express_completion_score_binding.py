from __future__ import annotations

from importlib import import_module
import re
import sys
from typing import Any, Callable

PATCH_VERSION = "nico.express_completion_score_binding.v5"
_RESPONSE_MARKER = "_nico_express_completion_score_response_v5"
_EXECUTE_MARKER = "_nico_express_completion_score_execute_v1"
_BOOTSTRAP_MARKER = "_nico_express_completion_score_bootstrap_v1"
_QUALITY_HEADING = "## Repository Quality and Governance Signals"
_REPAIR_HEADING = "## Prioritized Repair Intelligence"
_NON_REPAIR_SECTION_IDS = {"trust_readiness", "client_acceptance"}
_UNAVAILABLE_MEASUREMENT_PATTERN = re.compile(
    r"\b(max_function_cyclomatic|density|function_cyclomatic|complexity_density)=None\b"
)


def _sanitize_client_text(value: str) -> str:
    return _UNAVAILABLE_MEASUREMENT_PATTERN.sub(r"\1=unavailable", value)


def _sanitize_client_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_client_text(value)
    if isinstance(value, dict):
        return {key: _sanitize_client_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_client_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_client_value(item) for item in value)
    return value


def _section(payload: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in payload.get("sections", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == section_id
        ),
        None,
    )


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


def _dependency_is_clean(section: dict[str, Any] | None) -> bool:
    if not section:
        return False
    evidence = " ".join(str(item) for item in section.get("evidence", []) or []).lower()
    findings = " ".join(str(item) for item in section.get("findings", []) or []).lower()
    current_run = (
        "scanner-worker dependency tools completed" in evidence
        and ("verified score lift" in evidence or "current-run dependency scanner artifacts are clean" in evidence)
    )
    unresolved = any(
        marker in findings
        for marker in (
            "vulnerability record",
            "malformed osv",
            "dependency tools reported 1 finding",
            "dependency tools reported 2 finding",
            "dependency tools reported 3 finding",
            "dependency tools reported 4 finding",
            "dependency tools reported 5 finding",
        )
    )
    return current_run and not unresolved and str(section.get("status") or "").lower() == "green"


def _secrets_are_clean(section: dict[str, Any] | None) -> bool:
    if not section:
        return False
    evidence = " ".join(str(item) for item in section.get("evidence", []) or []).lower()
    findings = [str(item) for item in section.get("findings", []) or [] if str(item).strip()]
    return (
        not findings
        and str(section.get("status") or "").lower() == "green"
        and "gitleaks" in evidence
        and "trufflehog" in evidence
        and ("zero credential findings" in evidence or "artifacts are clean" in evidence)
    )


def _ci_is_clean(section: dict[str, Any] | None) -> bool:
    if not section or str(section.get("status") or "").lower() != "green":
        return False
    evidence = " ".join(str(item) for item in section.get("evidence", []) or []).lower()
    findings = " ".join(str(item) for item in section.get("findings", []) or []).lower()
    required_checks = all(
        marker in evidence
        for marker in ("nico ci=success", "codeql advanced=success", "audit evidence=success")
    )
    unresolved_current = any(
        marker in findings
        for marker in ("current release readiness is red", "latest required check failed", "required check is failing")
    )
    return required_checks and not unresolved_current


def _reconcile_final_section_truth(finalized: dict[str, Any]) -> None:
    dependency = _section(finalized, "dependency_health")
    if dependency and _dependency_is_clean(dependency):
        scanner_markers = (
            "pip-audit",
            "npm audit",
            "npm-audit",
            "osv scanner",
            "osv-scanner",
            "sandboxed worker",
            "scanner-clean dependency proof",
        )
        dependency["unavailable"] = [
            item
            for item in dependency.get("unavailable", []) or []
            if not any(marker in str(item).lower() for marker in scanner_markers)
        ]


def _refresh_client_actions(finalized: dict[str, Any], final_repairs: dict[str, Any]) -> None:
    dependency_clean = _dependency_is_clean(_section(finalized, "dependency_health"))
    secrets_clean = _secrets_are_clean(_section(finalized, "secrets_review"))
    ci_clean = _ci_is_clean(_section(finalized, "ci_cd"))
    existing = [str(item) for item in finalized.get("quick_wins", []) or [] if str(item).strip()]
    retained: list[str] = []
    for item in existing:
        lower = item.lower()
        if secrets_clean and any(marker in lower for marker in ("secret-pattern hit", "rotate real credentials", "confirmed secret")):
            continue
        if dependency_clean and any(marker in lower for marker in ("add lockfiles or tighter dependency pinning", "missing dependency proof")):
            continue
        if ci_clean and any(
            marker in lower
            for marker in (
                "add or strengthen ci checks",
                "add ci checks",
                "where missing",
            )
        ):
            continue
        if item not in retained:
            retained.append(item)

    candidate_actions: list[str] = []
    immediate = 0
    planned = 0
    monitor = 0
    for item in final_repairs.get("candidates", []) or []:
        if not isinstance(item, dict):
            continue
        score = float(item.get("priority_score") or 0)
        if score >= 60:
            immediate += 1
        elif score >= 40:
            planned += 1
        else:
            monitor += 1
        recommendation = str(item.get("recommended_action") or "").strip()
        if score >= 45 and recommendation and recommendation not in candidate_actions:
            candidate_actions.append(recommendation)

    actions = candidate_actions[:4]
    for item in retained:
        if item not in actions and len(actions) < 5:
            actions.append(item)
    review_action = "Complete the required human review and approve only evidence-supported repair candidates after the stated tests pass."
    if review_action not in actions:
        actions.append(review_action)
    finalized["quick_wins"] = actions[:6]
    finalized["repair_action_summary"] = {
        "immediate_count": immediate,
        "planned_count": planned,
        "monitor_count": monitor,
        "advisory_count": len(final_repairs.get("advisories", []) or []),
        "top_actions": candidate_actions[:4],
        "secret_quick_win_suppressed_because_scanners_clean": secrets_clean,
        "dependency_quick_win_suppressed_because_scanners_clean": dependency_clean,
        "generic_ci_quick_win_suppressed_because_required_checks_green": ci_clean,
        "human_review_required": True,
    }


def finalize_report_intelligence_at_response(value: Any) -> Any:
    """Attach, reconcile, sanitize, and export intelligence at the last response boundary.

    Repair candidates are rebuilt from final reconciled findings, generic evidence
    contradictions are removed, client actions are derived from the final portfolio,
    and unavailable measurements are rendered truthfully. The finalizer never edits
    the assessed repository and never marks a proposed repair as verified or applied.
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
    finalized = _sanitize_client_value(dict(value))

    if not isinstance(finalized.get("repository_quality_signals"), dict):
        finalized = enrichment.enrich_hosted_result(hosted, finalized)
    finalized = _sanitize_client_value(finalized)

    _reconcile_final_section_truth(finalized)
    prior_repairs = finalized.get("repair_intelligence")
    prior_candidate_count = (
        int(prior_repairs.get("candidate_count") or 0)
        if isinstance(prior_repairs, dict)
        else 0
    )
    quality_findings = _final_quality_findings(finalized)
    repair_source = _final_repair_source(finalized)
    final_repairs = build_report_repair_intelligence(
        repair_source,
        structured_findings=quality_findings,
    )
    final_repairs = _sanitize_client_value(final_repairs)
    finalized["repair_intelligence"] = final_repairs
    finalized["repairs"] = [
        str(item.get("recommended_action"))
        for item in final_repairs.get("candidates", [])[:10]
        if isinstance(item, dict) and item.get("recommended_action")
    ]
    _refresh_client_actions(finalized, final_repairs)
    finalized["repair_intelligence_reconciliation"] = {
        "status": "reconciled",
        "source": "final_reconciled_sections_and_verified_repository_quality_findings",
        "priority_model": str(final_repairs.get("priority_model") or "unknown"),
        "excluded_workflow_only_sections": sorted(_NON_REPAIR_SECTION_IDS),
        "prior_candidate_count": prior_candidate_count,
        "final_candidate_count": int(final_repairs.get("candidate_count") or 0),
        "final_code_suggestion_count": int(final_repairs.get("code_suggestion_count") or 0),
        "final_advisory_count": len(final_repairs.get("advisories", []) or []),
        "early_source_regex_candidates_carried_forward": False,
        "superseded_pre_polish_findings_carried_forward": False,
        "repository_size_ranked_as_defect": False,
        "human_review_required": True,
        "automatic_application_allowed": False,
    }

    # Rebuild unconditionally because final candidate, action, and display truth
    # changes the client-visible Markdown, HTML, and professional PDF.
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
        "priority_model": str(final_repairs.get("priority_model") or "unknown"),
        "repair_candidate_count": candidate_count,
        "code_suggestion_count": code_suggestion_count,
        "advisory_count": len(final_repairs.get("advisories", []) or []),
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
        "client_actions_reconciled_from_final_findings": True,
        "client_output_measurements_sanitized": True,
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
