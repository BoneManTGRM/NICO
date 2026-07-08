from __future__ import annotations

from typing import Any

SERVICE_CATALOG: dict[str, dict[str, Any]] = {
    "express": {
        "label": "Express Technical Health Assessment",
        "target_coverage": "90-95%",
        "best_for": "Fast evidence-bound repo audit, maturity signal, and client-ready technical report after human review.",
        "required_evidence": [
            "authorized repository owner/name",
            "explicit authorization statement",
            "scanner worker evidence or hosted scanner access",
            "dependency and static-analysis evidence",
            "final human review and client acceptance signoff",
        ],
        "deliverables": [
            "maturity semaphore",
            "scanner evidence summary",
            "dependency and security summary",
            "architecture and complexity evidence",
            "evidence bundle",
            "client acceptance gate",
        ],
        "workflow_endpoint": "POST /assessment/github",
    },
    "mid": {
        "label": "Mid Product and QA Assessment",
        "target_coverage": "75-85%",
        "best_for": "Product QA, platform parity, stakeholder discovery, and six-month roadmap planning.",
        "required_evidence": [
            "QA evidence or test cases",
            "platform parity notes",
            "stakeholder discovery notes",
            "roadmap notes or milestones",
            "known risks and constraints",
        ],
        "deliverables": [
            "QA and parity intake artifact",
            "stakeholder discovery artifact",
            "six-month roadmap artifact",
            "mid assessment report",
            "human review checklist",
        ],
        "workflow_endpoint": "POST /assessment/mid",
    },
    "retainer": {
        "label": "Ongoing Product Engineering Retainer",
        "target_coverage": "55-70%",
        "best_for": "Weekly delivery tracking, monthly strategy, release readiness, blocker escalation, and renewal evidence.",
        "required_evidence": [
            "commit summary",
            "pull request summary",
            "issue or backlog summary",
            "release notes if release work exists",
            "roadmap notes, client update notes, or retainer metrics",
            "blocker and approval needs",
        ],
        "deliverables": [
            "weekly health module",
            "monthly strategy module",
            "release readiness module",
            "blocker escalation module",
            "renewal signal module",
            "approval gates",
        ],
        "workflow_endpoint": "POST /retainer/ops",
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
    "mid": (
        "qa_evidence",
        "parity_notes",
        "stakeholder_notes",
        "roadmap_notes",
        "known_risks",
    ),
    "retainer": (
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


def _has_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) or isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def list_service_catalog() -> dict[str, Any]:
    return {
        "status": "ok",
        "artifact_schema": "nico.service_catalog.v1",
        "services": SERVICE_CATALOG,
        "safety_boundary": "All services require authorization, evidence-bound outputs, human review, and approval for client-facing or production-impacting decisions.",
    }


def get_service_catalog_item(workflow: str) -> dict[str, Any]:
    key = str(workflow or "").strip().lower()
    item = SERVICE_CATALOG.get(key)
    if not item:
        return {
            "status": "not_found",
            "workflow": key,
            "available_workflows": sorted(SERVICE_CATALOG),
        }
    return {
        "status": "ok",
        "workflow": key,
        "service": item,
        "required_fields": list(INTAKE_FIELDS.get(key, ())),
    }


def build_service_intake_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = str(payload.get("workflow") or payload.get("assessment_mode") or "").strip().lower()
    if workflow not in SERVICE_CATALOG:
        workflow = _recommend_workflow(payload)

    required = list(INTAKE_FIELDS.get(workflow, ()))
    present = [key for key in required if _has_value(payload, key)]
    missing = [key for key in required if key not in present]
    readiness_score = round((len(present) / max(1, len(required))) * 100)

    blockers: list[str] = []
    if workflow == "express" and not _has_value(payload, "authorized"):
        blockers.append("Express assessment requires explicit authorization before running.")
    if workflow in {"mid", "retainer"} and payload.get("authorized") is False:
        blockers.append("Workflow requires explicit authorization before running.")

    if blockers:
        status = "blocked_missing_authorization"
    elif missing:
        status = "needs_more_intake_evidence"
    else:
        status = "ready_for_workflow_request"

    return {
        "status": status,
        "artifact_schema": "nico.service_intake_readiness.v1",
        "recommended_workflow": workflow,
        "service": SERVICE_CATALOG[workflow],
        "readiness_score": readiness_score,
        "required_fields": required,
        "present_fields": present,
        "missing_fields": missing,
        "blockers": blockers,
        "next_action": _next_action(workflow, missing, blockers),
        "human_review_required": True,
    }


def _recommend_workflow(payload: dict[str, Any]) -> str:
    express_hits = sum(1 for key in INTAKE_FIELDS["express"] if _has_value(payload, key))
    mid_hits = sum(1 for key in INTAKE_FIELDS["mid"] if _has_value(payload, key))
    retainer_hits = sum(1 for key in INTAKE_FIELDS["retainer"] if _has_value(payload, key))
    scores = {"express": express_hits, "mid": mid_hits, "retainer": retainer_hits}
    return max(scores, key=lambda key: scores[key]) if any(scores.values()) else "express"


def _next_action(workflow: str, missing: list[str], blockers: list[str]) -> str:
    if blockers:
        return "Collect authorization before running the workflow."
    if missing:
        return f"Collect missing intake fields for {workflow}: {', '.join(missing[:6])}."
    endpoint = SERVICE_CATALOG[workflow]["workflow_endpoint"]
    return f"Submit the evidence to {endpoint}."
