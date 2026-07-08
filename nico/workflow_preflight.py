from __future__ import annotations

from typing import Any

from nico.service_catalog import build_service_intake_readiness


def _has_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) or isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _field_status(required_fields: list[str], payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "present": _has_value(payload, field),
            "required": True,
        }
        for field in required_fields
    ]


def _request_template(workflow: str, payload: dict[str, Any]) -> dict[str, Any]:
    if workflow == "express":
        return {
            "endpoint": "POST /assessment/github",
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
    if workflow == "mid":
        return {
            "endpoint": "POST /assessment/mid",
            "payload": {
                "authorized": bool(payload.get("authorized", False)),
                "client_name": payload.get("client_name", ""),
                "project_name": payload.get("project_name", ""),
                "qa_evidence": payload.get("qa_evidence", ""),
                "parity_notes": payload.get("parity_notes", ""),
                "stakeholder_notes": payload.get("stakeholder_notes", ""),
                "roadmap_notes": payload.get("roadmap_notes", ""),
                "known_risks": payload.get("known_risks", ""),
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
        "Human review is required before client-facing delivery.",
        "Production-impacting changes require explicit human approval.",
    ]
    if workflow == "express":
        requirements.insert(0, "Explicit repository authorization is required before execution.")
        requirements.append("Client acceptance must be recorded before delivery is marked allowed.")
    elif workflow == "mid":
        requirements.append("Client or authorized representative must approve roadmap commitments.")
    else:
        requirements.append("Client or authorized representative must approve scope, budget, timeline, and release-risk changes.")
    return requirements


def build_workflow_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = build_service_intake_readiness(payload)
    workflow = readiness["recommended_workflow"]
    missing_fields = list(readiness.get("missing_fields", []))
    blockers = list(readiness.get("blockers", []))
    allowed_to_run = readiness["status"] == "ready_for_workflow_request" and not blockers

    if allowed_to_run:
        status = "ready_to_submit"
    elif blockers:
        status = "blocked_preflight"
    else:
        status = "needs_more_preflight_evidence"

    request_template = _request_template(workflow, payload)

    return {
        "artifact_schema": "nico.workflow_preflight.v1",
        "status": status,
        "allowed_to_run": allowed_to_run,
        "recommended_workflow": workflow,
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
        "summary": "Workflow preflight converts intake readiness into a before-run package with endpoint, request template, blockers, missing evidence, and approval requirements.",
    }


def build_workflow_preflight_batch(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    preflights = [build_workflow_preflight(payload) for payload in payloads]
    return {
        "artifact_schema": "nico.workflow_preflight_batch.v1",
        "status": "ok",
        "count": len(preflights),
        "ready_count": sum(1 for item in preflights if item.get("allowed_to_run")),
        "blocked_count": sum(1 for item in preflights if item.get("status") == "blocked_preflight"),
        "preflights": preflights,
        "human_review_required": True,
    }
