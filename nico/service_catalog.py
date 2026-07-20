from __future__ import annotations

from copy import deepcopy
from typing import Any

CATALOG_VERSION = "nico.service_catalog.v2"

SERVICE_ALIASES = {
    "express": "express",
    "rapid": "express",
    "baseline": "express",
    "mid": "comprehensive",
    "full": "comprehensive",
    "deep": "comprehensive",
    "comprehensive": "comprehensive",
    "retainer": "monitor_execute",
    "monitor": "monitor_execute",
    "execute": "monitor_execute",
    "monitor_execute": "monitor_execute",
    "monitor+execute": "monitor_execute",
}

SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    "express": {
        "id": "express",
        "label": "NICO Express Technical Assessment",
        "category": "assessment",
        "customer_selectable": True,
        "target_coverage": "90-95%",
        "best_for": "Fast evidence-bound repository diagnosis, prioritized risks, and a human-review-bound decision report.",
        "required_evidence": [
            "authorized repository owner/name",
            "explicit authorization statement",
            "scanner worker evidence or hosted scanner access",
            "dependency, security, static-analysis, CI/CD, architecture, and complexity evidence",
            "final human review and client acceptance signoff",
        ],
        "deliverables": [
            "executive decision and canonical maturity signal",
            "ranked priority actions and evidence-backed quick wins",
            "dependency, security, static-analysis, CI/CD, architecture, complexity, ownership, churn, and velocity evidence",
            "30/60/90-day repair plan, resourcing, risk register, and verification checklist",
            "exact-snapshot evidence bundle and client acceptance gate",
            "equivalent PDF, Markdown, HTML, JSON, and dashboard truth",
        ],
        "workflow_endpoint": "POST /assessment/github",
        "internal_execution_profiles": ["express"],
    },
    "comprehensive": {
        "id": "comprehensive",
        "label": "NICO Comprehensive Technical Assessment",
        "category": "assessment",
        "customer_selectable": True,
        "target_coverage": "75-85% initially; increases with connected QA, stakeholder, platform, and production evidence",
        "best_for": "Complete technical diligence, QA, operating-model analysis, roadmap, staffing, sequencing, and executive decision support.",
        "required_evidence": [
            "authorized repository and immutable snapshot",
            "deep scanner and evidence-triage access",
            "functional QA or representative user-flow evidence",
            "platform parity evidence where applicable",
            "deployment and infrastructure evidence",
            "stakeholder, requirements, roadmap, cost, and known-risk context",
            "final human review and client acceptance signoff",
        ],
        "deliverables": [
            "everything included in Express",
            "deep technical dossiers and scanner dispositions",
            "functional QA, platform parity, deployment, infrastructure, and operational-readiness review",
            "developer workflow, ownership, PR latency, historical trend, and change-failure analysis",
            "stakeholder alignment, requirements traceability, and work-vs-expected analysis",
            "six-month roadmap, staffing, sequencing, cost, risk-reduction, and executive briefing",
            "one snapshot, one run ID, one evidence ledger, one canonical score, and one final report package",
        ],
        "workflow_endpoint": "POST /assessment/mid-run",
        "internal_execution_profiles": ["mid", "full", "deep"],
    },
    "monitor_execute": {
        "id": "monitor_execute",
        "label": "NICO Monitor + Execute",
        "category": "recurring_operations",
        "customer_selectable": False,
        "target_coverage": "Measured from connected operating evidence",
        "best_for": "Ongoing oversight, approved remediation, release verification, roadmap execution, and auditable operating evidence.",
        "required_evidence": [
            "explicit operating authorization",
            "commit, pull request, issue, release, blocker, roadmap, and approval evidence",
            "defined execution scope and rollback authority",
        ],
        "deliverables": [
            "continuous monitoring and weekly operating status",
            "approved repair execution and retesting",
            "release readiness and verification",
            "roadmap delivery evidence and approval history",
        ],
        "workflow_endpoint": "POST /retainer/ops",
        "internal_execution_profiles": ["retainer", "monitor", "execute"],
    },
}

INTAKE_FIELDS: dict[str, tuple[str, ...]] = {
    "express": (
        "repository",
        "authorized",
        "authorized_by",
        "authorization_scope",
        "scanner_worker_artifact",
    ),
    "comprehensive": (
        "repository",
        "authorized",
        "authorized_by",
        "authorization_scope",
        "qa_evidence",
        "parity_notes",
        "stakeholder_notes",
        "roadmap_notes",
        "known_risks",
    ),
    "monitor_execute": (
        "authorized",
        "commit_summary",
        "pr_summary",
        "issue_summary",
        "release_notes",
        "roadmap_notes",
        "client_update",
        "retainer_metrics",
        "blockers",
    ),
}


def normalize_service_id(value: Any, *, default: str = "express") -> str:
    key = str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
    return SERVICE_ALIASES.get(key, default)


def _has_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (dict, list)):
        return bool(value)
    return bool(str(value or "").strip())


def list_service_catalog() -> dict[str, Any]:
    assessments = {
        service_id: deepcopy(item)
        for service_id, item in SERVICE_CATALOG.items()
        if item.get("category") == "assessment" and item.get("customer_selectable") is True
    }
    recurring = {
        service_id: deepcopy(item)
        for service_id, item in SERVICE_CATALOG.items()
        if item.get("category") == "recurring_operations"
    }
    return {
        "status": "ok",
        "artifact_schema": CATALOG_VERSION,
        "services": assessments,
        "assessment_services": assessments,
        "recurring_services": recurring,
        "customer_assessment_count": len(assessments),
        "legacy_aliases": {key: value for key, value in SERVICE_ALIASES.items() if key != value},
        "safety_boundary": "All services require authorization, evidence-bound outputs, human review, and approval for client-facing or production-impacting decisions.",
    }


def get_service_catalog_item(workflow: str) -> dict[str, Any]:
    requested = str(workflow or "").strip().casefold()
    canonical = normalize_service_id(requested, default="")
    item = SERVICE_CATALOG.get(canonical)
    if not item:
        return {
            "status": "not_found",
            "workflow": requested,
            "available_workflows": sorted(SERVICE_CATALOG),
            "available_customer_assessments": ["express", "comprehensive"],
        }
    return {
        "status": "ok",
        "workflow": canonical,
        "requested_workflow": requested,
        "legacy_alias_used": bool(requested and requested != canonical),
        "internal_execution_profile": requested if requested in {"mid", "full", "deep", "retainer", "monitor", "execute"} else canonical,
        "service": deepcopy(item),
        "required_fields": list(INTAKE_FIELDS.get(canonical, ())),
    }


def build_service_intake_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    requested = str(payload.get("workflow") or payload.get("assessment_mode") or payload.get("service_tier") or "").strip().casefold()
    workflow = normalize_service_id(requested, default="")
    if workflow not in SERVICE_CATALOG:
        workflow = _recommend_workflow(payload)

    required = list(INTAKE_FIELDS.get(workflow, ()))
    present = [key for key in required if _has_value(payload, key)]
    missing = [key for key in required if key not in present]
    readiness_score = round((len(present) / max(1, len(required))) * 100)

    blockers: list[str] = []
    if workflow in {"express", "comprehensive", "monitor_execute"} and not _has_value(payload, "authorized"):
        blockers.append(f"{SERVICE_CATALOG[workflow]['label']} requires explicit authorization before running.")

    if blockers:
        status = "blocked_missing_authorization"
    elif missing:
        status = "needs_more_intake_evidence"
    else:
        status = "ready_for_workflow_request"

    return {
        "status": status,
        "artifact_schema": "nico.service_intake_readiness.v2",
        "recommended_workflow": workflow,
        "requested_workflow": requested,
        "legacy_alias_used": bool(requested and requested != workflow),
        "internal_execution_profile": requested if requested in {"mid", "full", "deep", "retainer", "monitor", "execute"} else workflow,
        "service": deepcopy(SERVICE_CATALOG[workflow]),
        "readiness_score": readiness_score,
        "required_fields": required,
        "present_fields": present,
        "missing_fields": missing,
        "blockers": blockers,
        "next_action": _next_action(workflow, missing, blockers),
        "human_review_required": True,
    }


def _recommend_workflow(payload: dict[str, Any]) -> str:
    scores = {
        service_id: sum(1 for key in INTAKE_FIELDS[service_id] if _has_value(payload, key))
        for service_id in INTAKE_FIELDS
    }
    if any(scores.values()):
        return max(scores, key=lambda key: scores[key])
    return "express"


def _next_action(workflow: str, missing: list[str], blockers: list[str]) -> str:
    if blockers:
        return "Collect explicit authorization before running the workflow."
    if missing:
        return f"Collect missing intake fields for {workflow}: {', '.join(missing[:8])}."
    endpoint = SERVICE_CATALOG[workflow]["workflow_endpoint"]
    return f"Submit the evidence to {endpoint}."


__all__ = [
    "CATALOG_VERSION",
    "INTAKE_FIELDS",
    "SERVICE_ALIASES",
    "SERVICE_CATALOG",
    "build_service_intake_readiness",
    "get_service_catalog_item",
    "list_service_catalog",
    "normalize_service_id",
]
