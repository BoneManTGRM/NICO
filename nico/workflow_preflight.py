from __future__ import annotations

from typing import Any

from nico.service_catalog import build_service_intake_readiness


def _has_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, (dict, list)):
        return bool(value)
    return bool(str(value or "").strip())


def _field_status(required_fields: list[str], payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": field, "present": _has_value(payload, field), "required": True} for field in required_fields]


def _request_template(workflow: str, payload: dict[str, Any]) -> dict[str, Any]:
    if workflow == "express":
        return {
            "endpoint": "POST /assessment/express-run",
            "payload": {
                "repository": payload.get("repository", "owner/repo"),
                "authorized": bool(payload.get("authorized", False)),
                "authorized_by": payload.get("authorized_by", ""),
                "authorization_scope": payload.get("authorization_scope", "repository assessment only"),
                "client_name": payload.get("client_name", ""),
                "project_name": payload.get("project_name", ""),
                "assessment_mode": "express",
            },
        }
    if workflow == "comprehensive":
        return {
            "endpoint": "POST /assessment/mid-run",
            "payload": {
                "repository": payload.get("repository", "owner/repo"),
                "authorized": bool(payload.get("authorized", False)),
                "authorized_by": payload.get("authorized_by", ""),
                "authorization_scope": payload.get("authorization_scope", "repository assessment only"),
                "client_name": payload.get("client_name", ""),
                "project_name": payload.get("project_name", ""),
                "qa_evidence": payload.get("qa_evidence", ""),
                "parity_notes": payload.get("parity_notes", ""),
                "stakeholder_notes": payload.get("stakeholder_notes", ""),
                "roadmap_notes": payload.get("roadmap_notes", ""),
                "known_risks": payload.get("known_risks", ""),
                "service_tier": "comprehensive",
                "run_scanners": True,
                "auto_continue": True,
            },
        }
    return {
        "endpoint": "POST /retainer/ops",
        "payload": {
            "authorized": bool(payload.get("authorized", False)),
            "client_name": payload.get("client_name", ""),
            "project_name": payload.get("project_name", ""),
            "commit_summary": payload.get("commit_summary", ""),
            "pr_summary": payload.get("pr_summary", ""),
            "issue_summary": payload.get("issue_summary", ""),
            "blockers": payload.get("blockers", ""),
            "release_notes": payload.get("release_notes", ""),
            "roadmap_notes": payload.get("roadmap_notes", ""),
        },
    }


def _approval_requirements(workflow: str) -> list[str]:
    requirements = [
        "Explicit authorization is required before execution.",
        "Human review is required before client-facing delivery.",
        "Production-impacting changes require explicit human approval.",
    ]
    if workflow == "express":
        requirements.append("Client acceptance must be recorded before delivery is marked allowed.")
    elif workflow == "comprehensive":
        requirements.append("The authorized reviewer must approve findings, roadmap, staffing, cost, and final delivery scope.")
    else:
        requirements.append("The client must approve scope, budget, timeline, and release-risk changes.")
    return requirements


def build_workflow_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = build_service_intake_readiness(payload)
    workflow = readiness["recommended_workflow"]
    missing_fields = list(readiness.get("missing_fields", []))
    blockers = list(readiness.get("blockers", []))
    allowed_to_run = readiness["status"] == "ready_for_workflow_request" and not blockers

    status = "ready_to_submit" if allowed_to_run else "blocked_preflight" if blockers else "needs_more_preflight_evidence"
    request_template = _request_template(workflow, payload)

    return {
        "artifact_schema": "nico.workflow_preflight.v2",
        "status": status,
        "allowed_to_run": allowed_to_run,
        "recommended_workflow": workflow,
        "requested_workflow": readiness.get("requested_workflow"),
        "internal_execution_profile": readiness.get("internal_execution_profile"),
        "target_endpoint": request_template["endpoint"],
        "readiness_score": readiness["readiness_score"],
        "readiness": readiness,
        "field_status": _field_status(readiness.get("required_fields", []), payload),
        "missing_fields": missing_fields,
        "blockers": blockers,
        "request_template": request_template,
        "approval_requirements": _approval_requirements(workflow),
        "next_action": "Submit the request template." if allowed_to_run else readiness.get("next_action", "Collect missing evidence before running workflow."),
        "human_review_required": True,
        "summary": "Preflight converts the two-service intake contract into an exact endpoint, request payload, blockers, missing evidence, and approval requirements.",
    }


def build_workflow_preflight_batch(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    preflights = [build_workflow_preflight(payload) for payload in payloads]
    return {
        "artifact_schema": "nico.workflow_preflight_batch.v2",
        "status": "ok",
        "count": len(preflights),
        "ready_count": sum(1 for item in preflights if item.get("allowed_to_run")),
        "blocked_count": sum(1 for item in preflights if item.get("status") == "blocked_preflight"),
        "preflights": preflights,
        "human_review_required": True,
    }
