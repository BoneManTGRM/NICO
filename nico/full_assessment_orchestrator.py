from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from nico.storage import new_id, utc_now

FULL_ASSESSMENT_STEPS = [
    "authorization",
    "repo_evidence",
    "scanner_worker",
    "evidence_attachment",
    "scoring",
    "reports",
    "approval_request",
]

StepHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None]


class FullAssessmentBlocked(ValueError):
    """Raised when the full-run request fails a safe preflight gate."""


def normalize_repository_target(payload: dict[str, Any]) -> str:
    """Normalize a GitHub owner/repo or GitHub URL into owner/repo form.

    This intentionally accepts only GitHub repository targets. The full-run
    orchestrator is an authorized defensive repository assessment workflow, not
    a generic URL scanner.
    """

    raw = str(payload.get("repository") or payload.get("target") or "").strip()
    raw = raw.removesuffix(".git").strip(" /")
    match = re.match(r"^https://github\.com/([^/]+)/([^/#?]+)", raw, re.IGNORECASE)
    if match:
        raw = f"{match.group(1)}/{match.group(2)}"
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", raw):
        return ""
    return raw


def _authorized(payload: dict[str, Any]) -> bool:
    return bool(payload.get("authorization_confirmed") or payload.get("authorized"))


def _base_context(payload: dict[str, Any]) -> dict[str, Any]:
    repository = normalize_repository_target(payload)
    return {
        "run_id": str(payload.get("run_id") or new_id("fullrun")),
        "repository": repository,
        "customer_id": str(payload.get("customer_id") or "default_customer"),
        "project_id": str(payload.get("project_id") or "default_project"),
        "client_name": str(payload.get("client_name") or ""),
        "project_name": str(payload.get("project_name") or ""),
        "authorized_by": str(payload.get("authorized_by") or "unspecified"),
        "mode": str(payload.get("mode") or "express"),
        "created_at": utc_now(),
    }


def _progress(step: str, status: str, message: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"step": step, "status": status}
    if message:
        item["message"] = message
    if evidence:
        item["evidence"] = evidence
    return item


def _empty_response(context: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": context.get("run_id") or "",
        "repository": context.get("repository") or "",
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "mode": context.get("mode") or "express",
        "progress": [],
        "assessment": {},
        "reports": {"markdown": "", "html": "", "pdf_base64": "", "pdf_filename": "nico-assessment.pdf", "pdf_error": ""},
        "approval": {"approval_id": "", "status": "not_requested"},
        "human_review_required": True,
        "client_ready": False,
        "generated_at": context.get("created_at") or utc_now(),
    }


def run_full_assessment_orchestration(
    payload: dict[str, Any],
    handlers: dict[str, StepHandler] | None = None,
) -> dict[str, Any]:
    """Run the one-click full-assessment pipeline skeleton.

    PR-1 intentionally provides the orchestration contract and safe gates only.
    Missing handlers are marked ``planned`` rather than completed so NICO never
    claims evidence was collected, scanned, scored, exported, or approved when a
    real worker has not run yet.
    """

    context = _base_context(payload)
    response = _empty_response(context, "planned")
    handlers = handlers or {}

    if not context["repository"]:
        response["status"] = "blocked"
        response["progress"].append(_progress("authorization", "blocked", "A valid GitHub repository target in owner/repo form is required."))
        response["error"] = "valid repository target is required"
        return response

    if not _authorized(payload):
        response["status"] = "blocked"
        response["progress"].append(_progress("authorization", "blocked", "Authorization confirmation is required before assessment."))
        response["error"] = "authorization confirmation is required"
        return response

    response["progress"].append(
        _progress(
            "authorization",
            "complete",
            "Authorization was confirmed by the requester; final delivery still requires human review.",
            {"authorized_by": context["authorized_by"], "repository": context["repository"]},
        )
    )

    step_outputs: dict[str, Any] = {}
    for step in FULL_ASSESSMENT_STEPS[1:]:
        handler = handlers.get(step)
        if handler is None:
            response["progress"].append(_progress(step, "planned", "Step is defined in the orchestrator contract but is not wired in this PR."))
            continue
        try:
            output = handler(context, step_outputs) or {}
        except Exception:  # pragma: no cover - defensive orchestration boundary
            response["status"] = "failed"
            response["progress"].append(_progress(step, "failed", "Step failed; review server logs or authorized diagnostic evidence."))
            response["failed_step"] = step
            return response
        step_outputs[step] = output
        response["progress"].append(_progress(step, output.get("status", "complete"), output.get("message", ""), output.get("evidence") if isinstance(output.get("evidence"), dict) else None))

    if "scoring" in step_outputs:
        response["assessment"] = step_outputs["scoring"].get("assessment") or step_outputs["scoring"].get("result") or {}
    if "reports" in step_outputs:
        response["reports"].update(step_outputs["reports"].get("reports") or {})
    if "approval_request" in step_outputs:
        response["approval"].update(step_outputs["approval_request"].get("approval") or {})

    response["status"] = "complete" if all(item.get("status") == "complete" for item in response["progress"]) else response["status"]
    return response
