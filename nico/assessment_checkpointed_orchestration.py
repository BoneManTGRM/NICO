from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from nico.full_assessment_orchestrator import (
    FULL_ASSESSMENT_STEPS,
    StepHandler,
    normalize_repository_target,
    run_full_assessment_orchestration,
)
from nico.storage import utc_now

CheckpointWriter = Callable[[dict[str, Any], str, str], None]
OrchestrationRunner = Callable[..., dict[str, Any]]


def _progress(step: str, output: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "step": step,
        "status": str(output.get("status") or "complete"),
    }
    message = str(output.get("message") or "")
    if message:
        item["message"] = message
    evidence = output.get("evidence")
    if isinstance(evidence, dict) and evidence:
        item["evidence"] = deepcopy(evidence)
    return item


def _checkpoint_response(
    payload: dict[str, Any],
    outputs: dict[str, Any],
    *,
    current_step: str,
    current_phase: str,
) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    repository = normalize_repository_target(payload) or str(
        payload.get("repository") or payload.get("target") or ""
    )
    response: dict[str, Any] = {
        "status": "running",
        "run_id": run_id,
        "repository": repository,
        "customer_id": str(payload.get("customer_id") or "default_customer"),
        "project_id": str(payload.get("project_id") or "default_project"),
        "mode": str(payload.get("mode") or "express"),
        "generated_at": utc_now(),
        "progress": [
            {
                "step": "authorization",
                "status": "complete",
                "message": "Authorization was confirmed before checkpointed execution.",
                "evidence": {
                    "authorized_by": str(payload.get("authorized_by") or "unspecified"),
                    "repository": repository,
                },
            }
        ],
        "scanner": {
            "scan_id": str(payload.get("scan_id") or ""),
            "status": "not_started",
        },
        "scanner_evidence": {
            "status": "not_attached",
            "scan_id": str(payload.get("scan_id") or ""),
        },
        "assessment": {},
        "reports": {},
        "approval": {},
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
        "checkpoint_context": {
            "current_step": current_step,
            "current_phase": current_phase,
        },
    }
    for step in FULL_ASSESSMENT_STEPS[1:]:
        output = outputs.get(step)
        if not isinstance(output, dict):
            continue
        response["progress"].append(_progress(step, output))

    scanner_output = outputs.get("scanner_worker")
    if isinstance(scanner_output, dict) and isinstance(scanner_output.get("scan"), dict):
        response["scanner"] = deepcopy(scanner_output["scan"])
    attachment = outputs.get("evidence_attachment")
    if isinstance(attachment, dict):
        evidence = attachment.get("scanner_evidence")
        if not isinstance(evidence, dict):
            evidence = attachment.get("evidence")
        if isinstance(evidence, dict):
            response["scanner_evidence"] = deepcopy(evidence)
    scoring = outputs.get("scoring")
    if isinstance(scoring, dict):
        assessment = scoring.get("assessment") or scoring.get("result")
        if isinstance(assessment, dict):
            response["assessment"] = deepcopy(assessment)
    reports_output = outputs.get("reports")
    if isinstance(reports_output, dict):
        reports = reports_output.get("reports")
        if isinstance(reports, dict):
            response["reports"] = deepcopy(reports)
    approval_output = outputs.get("approval_request")
    if isinstance(approval_output, dict):
        approval = approval_output.get("approval")
        if isinstance(approval, dict):
            response["approval"] = deepcopy(approval)
    return response


def _wrapped_handlers(
    payload: dict[str, Any],
    handlers: dict[str, StepHandler],
    checkpoint: CheckpointWriter,
) -> dict[str, StepHandler]:
    wrapped: dict[str, StepHandler] = {}
    shared_outputs: dict[str, Any] = {}

    for step, handler in handlers.items():
        def make_wrapper(step_name: str, step_handler: StepHandler) -> StepHandler:
            def execute(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any] | None:
                shared_outputs.clear()
                shared_outputs.update(deepcopy(outputs))
                checkpoint(
                    _checkpoint_response(
                        payload,
                        shared_outputs,
                        current_step=step_name,
                        current_phase="started",
                    ),
                    step_name,
                    "step_started",
                )
                try:
                    output = step_handler(context, outputs) or {}
                except Exception:
                    failed_outputs = deepcopy(shared_outputs)
                    failed_outputs[step_name] = {
                        "status": "failed",
                        "message": "Step failed; inspect authorized diagnostics.",
                        "evidence": {"run_id": payload.get("run_id") or ""},
                    }
                    failed = _checkpoint_response(
                        payload,
                        failed_outputs,
                        current_step=step_name,
                        current_phase="failed",
                    )
                    failed["status"] = "failed"
                    failed["failed_step"] = step_name
                    checkpoint(failed, step_name, "step_failed")
                    raise
                completed_outputs = deepcopy(shared_outputs)
                completed_outputs[step_name] = deepcopy(output)
                checkpoint(
                    _checkpoint_response(
                        payload,
                        completed_outputs,
                        current_step=step_name,
                        current_phase="completed",
                    ),
                    step_name,
                    "step_completed",
                )
                return output

            return execute

        wrapped[step] = make_wrapper(step, handler)
    return wrapped


def run_checkpointed_assessment_orchestration(
    payload: dict[str, Any],
    *,
    handlers: dict[str, StepHandler],
    checkpoint: CheckpointWriter,
    orchestrator: OrchestrationRunner = run_full_assessment_orchestration,
) -> dict[str, Any]:
    checkpoint(
        {
            "status": "running",
            "run_id": str(payload.get("run_id") or ""),
            "repository": str(payload.get("repository") or payload.get("target") or ""),
            "customer_id": str(payload.get("customer_id") or "default_customer"),
            "project_id": str(payload.get("project_id") or "default_project"),
            "mode": str(payload.get("mode") or "express"),
            "progress": [],
            "scanner": {"scan_id": str(payload.get("scan_id") or ""), "status": "not_started"},
            "scanner_evidence": {"status": "not_attached", "scan_id": str(payload.get("scan_id") or "")},
            "assessment": {},
            "reports": {},
            "approval": {},
            "generated_at": utc_now(),
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
        "preflight",
        "preflight",
    )
    result = orchestrator(
        payload,
        handlers=_wrapped_handlers(payload, handlers, checkpoint),
    )
    checkpoint(result, "orchestration", "orchestration_finalized")
    return result


__all__ = [
    "CheckpointWriter",
    "OrchestrationRunner",
    "run_checkpointed_assessment_orchestration",
]
