from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nico.phase3_evidence_core_v1 import _field, _missing, _prior, _repo, _result, _state, _text

VERSION = "nico.phase3_planning_synthesis.v1"

def historical_trends_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context); activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), Mapping) else {}; workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), Mapping) else {}; incidents = _field(context, "incident_history", "incidents")
    missing = [] if incidents else [_missing("incident_and_recovery_history", "Workflow counts cannot distinguish incidents from cancellation/supersession/infrastructure noise.", "Change-failure rate, severity, rollback effectiveness, or measured recovery time.", "Incident, deployment/rollback, and measured recovery records.")]
    evidence = {"operational_history_state": "retained_verified", "captured_through": activity.get("captured_through"), "commits_returned": activity.get("commits_returned", 0), "pull_requests_returned": activity.get("pull_requests_returned", 0), "successful_runs": workflow.get("successful_runs", 0), "non_success_runs": workflow.get("non_success_runs", 0), "incident_evidence_state": _state(context, "incident_history") if incidents else "not_supplied", "supplied_incidents": incidents, "workflow_outcomes_technical_score_effect": "none", "change_failure_rate_established": False}
    return _result(context, summary="Bounded operational history and supplied incident evidence were reconciled without turning activity volume into quality or workflow counts into incident truth.", historical_trends=evidence, missing_evidence=missing, evidence=evidence, unavailable_data_notes=[x["cannot_conclude"] for x in missing])


def roadmap_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = _prior(context, "evidence_reconciliation_and_scoring"); assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), Mapping) else {}; sections = [x for x in assessment.get("sections") or [] if isinstance(x, Mapping) and isinstance(x.get("presented_score"), (int, float))]
    controls = [_text(x.get("label") or x.get("id"), 120) for x in sorted(sections, key=lambda x: (int(x.get("presented_score") or 0), _text(x.get("id"))))[:6]]
    req = _prior(context, "requirements_traceability").get("requirements_traceability") or {}; stakeholder = _prior(context, "stakeholder_and_business_alignment").get("stakeholder_alignment") or {}; constraints = list(stakeholder.get("constraints") or []) if isinstance(stakeholder, Mapping) else []; reqs = list(req.get("mappings") or []) if isinstance(req, Mapping) else []
    roadmap = [
        {"window": "0-30 days", "objective": "Address material security/assurance issues, highest exact-source maintainability risks, and decision-blocking evidence gaps.", "priority_controls": controls[:3]},
        {"window": "31-90 days", "objective": "Strengthen architecture boundaries, test/release automation, functional QA evidence, and remediation verification.", "priority_controls": controls[2:5]},
        {"window": "91-180 days", "objective": "Resolve remaining architectural debt, platform/runtime evidence gaps, and supplied stakeholder/requirements objectives.", "priority_controls": controls},
    ]
    for item in roadmap: item.update({"sequence_state": "nico_proposed", "date_state": "illustrative", "stakeholder_approved": False, "dependency_provenance": "evidence_inferred", "constraints": constraints[:8], "requirements": [r.get("requirement_id") for r in reqs[:8] if isinstance(r, Mapping)]})
    return _result(context, summary="The existing 0-30/31-90/91-180 roadmap framework was drafted from technical priorities, evidence gaps, supplied requirements, and supplied constraints without creating commitments.", roadmap=roadmap, roadmap_truth={"framework_only": True, "nico_proposed_sequence": True, "stakeholder_approved_sequence": False, "illustrative_dates_only": True, "approved_dates_present": False}, evidence={"roadmap_window_count": 3, "priority_controls": controls}, unavailable_data_notes=["Roadmap dates, owners, commitments, and budget remain pending authorized stakeholder approval."])


def resourcing_provider(context: dict[str, Any]) -> dict[str, Any]:
    roles = [
        {"role_category": "Cybersecurity specialist", "skill_category": "security triage, residual risk, remediation verification", "sequence": 1, "effort_band": "variable_by_confirmed_risk"},
        {"role_category": "Architecture / senior engineering", "skill_category": "architecture boundaries, maintainability, complex remediation", "sequence": 2, "effort_band": "medium_to_large"},
        {"role_category": "DevOps / platform", "skill_category": "CI/CD, deployment, observability, release controls", "sequence": 3, "effort_band": "small_to_medium"},
        {"role_category": "QA / product quality", "skill_category": "functional QA, platform parity, acceptance evidence", "sequence": 4, "effort_band": "evidence_dependent"},
    ]
    budget = _field(context, "budget_staffing", "constraints"); evidence = {"recommended_roles": roles, "client_capacity_inputs_state": _state(context, "budget_staffing") if budget else "not_supplied", "supplied_capacity_constraints": budget, "commercial_values_generated": False, "salary_rates_generated": False, "vendor_commitments_generated": False, "final_budget_generated": False}
    return _result(context, summary="Role and skill categories were derived from the technical roadmap without inventing salaries, rates, vendors, contracts, or budgets.", staffing_plan=roles, evidence=evidence, unavailable_data_notes=[] if budget else ["Capacity, delivery model, rates, and budget authority were not supplied; commercial totals remain uncommitted."])


def executive_briefing_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = _prior(context, "evidence_reconciliation_and_scoring"); assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), Mapping) else {}; maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}; sections = [x for x in assessment.get("sections") or [] if isinstance(x, Mapping) and isinstance(x.get("presented_score"), (int, float))]
    priorities = [{"control": _text(x.get("label") or x.get("id"), 120), "technical_score": int(x.get("presented_score") or 0), "reason": _text(x.get("summary"), 500), "evidence_state": "retained_verified"} for x in sorted(sections, key=lambda x: (int(x.get("presented_score") or 0), _text(x.get("id"))))[:5]]
    roadmap = _prior(context, "six_month_roadmap").get("roadmap") or []; staffing = _prior(context, "staffing_sequencing_and_cost").get("staffing_plan") or []; missing = []
    for stage_id in ("functional_qa", "platform_parity", "requirements_traceability", "stakeholder_and_business_alignment", "historical_trends_and_change_failure"):
        missing.extend([dict(x) for x in _prior(context, stage_id).get("missing_evidence") or [] if isinstance(x, Mapping)])
    briefing = {"engagement_mode": "internal" if str(context.get("customer_id")) == "default_customer" else "client", "maturity_level": maturity.get("level") or "Pending", "technical_score": maturity.get("presented_score", maturity.get("score")), "top_technical_priorities": priorities, "quick_wins": [x["control"] for x in priorities[:2]], "medium_term_actions": [x.get("objective") for x in roadmap[1:2] if isinstance(x, Mapping)], "recommended_roles": len(staffing), "missing_evidence": missing, "decision": "Proceed to professional human review; automated synthesis is not stakeholder approval, residual-risk acceptance, final approval, or client-delivery authorization."}
    return _result(context, summary="Evidence-backed priorities, quick wins, roadmap/resourcing context, and missing-evidence limits were condensed automatically for executive review.", executive_briefing=briefing, missing_evidence=missing, evidence=briefing)

PLANNING_PROVIDER_REPLACEMENTS = {
    "historical_trends": historical_trends_provider,
    "roadmap": roadmap_provider,
    "resourcing": resourcing_provider,
    "executive_briefing": executive_briefing_provider,
}

__all__ = ["VERSION", "PLANNING_PROVIDER_REPLACEMENTS", "executive_briefing_provider", "historical_trends_provider", "resourcing_provider", "roadmap_provider"]
