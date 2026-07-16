from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException, Request

MID_TERMINAL_TRUTH_VERSION = "nico.mid_terminal_truth.v1"
MID_STATUS_PATH = "/assessment/mid-run/{run_id}/status"
_ARTIFACT_MARKER = "_nico_mid_terminal_truth_artifacts_v1"
_LIVE_MARKER = "_nico_mid_terminal_truth_live_v1"
_INSTALLER_MARKER = "_nico_mid_terminal_truth_installer_v1"
_TERMINAL_SCANNER = {"complete", "failed", "error", "blocked", "cancelled", "unavailable", "timed_out"}
_COMPLETE = {"complete", "completed", "attached", "verified"}
_BLOCKED = {"blocked", "failed", "error", "interrupted", "rejected"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    request = _dict(record.get("request"))
    stored_customer = str(record.get("customer_id") or request.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request.get("project_id") or "default_project")
    return stored_customer == customer_id and stored_project == project_id


def _progress_index(progress: list[dict[str, Any]], step: str) -> int | None:
    for index, item in enumerate(progress):
        if str(item.get("step") or "") == step:
            return index
    return None


def _step_status(progress: list[dict[str, Any]], step: str) -> str:
    index = _progress_index(progress, step)
    return str(progress[index].get("status") or "") if index is not None else ""


def _replace_step(
    progress: list[dict[str, Any]],
    step: str,
    status: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    item = {
        "step": step,
        "status": status,
        "message": message,
        "evidence": deepcopy(evidence or {}),
    }
    index = _progress_index(progress, step)
    if index is None:
        progress.append(item)
    else:
        progress[index] = item


def _scanner_terminal_status(result: dict[str, Any], progress: list[dict[str, Any]]) -> str:
    scanner = _dict(result.get("scanner"))
    evidence = _dict(result.get("scanner_evidence"))
    candidates = [
        evidence.get("scanner_status"),
        evidence.get("status"),
        scanner.get("status"),
    ]
    for step in ("scanner_reconciliation", "scanner_worker"):
        index = _progress_index(progress, step)
        if index is not None:
            candidates.append(_dict(progress[index].get("evidence")).get("scanner_status"))
    for value in candidates:
        normalized = str(value or "").lower()
        if normalized in _TERMINAL_SCANNER:
            return normalized
    return ""


def _quality_report_for_run(result: dict[str, Any]) -> dict[str, Any]:
    from nico.storage import STORE

    run_id = str(result.get("run_id") or "")
    customer_id = str(result.get("customer_id") or "default_customer")
    project_id = str(result.get("project_id") or "default_project")
    if not run_id:
        return {}
    try:
        reports = STORE.list("reports", customer_id=customer_id, project_id=project_id)
    except Exception:
        return {}
    matches = [
        item for item in reports
        if isinstance(item, dict)
        and str(item.get("run_id") or "") == run_id
        and isinstance(item.get("report_quality_manifest"), dict)
    ]
    if not matches:
        return {}
    matches.sort(key=lambda item: str(item.get("updated_at") or item.get("generated_at") or ""), reverse=True)
    return deepcopy(matches[0])


def _attach_quality_failure_truth(result: dict[str, Any], progress: list[dict[str, Any]]) -> None:
    if str(result.get("report_generation_status") or "").lower() != "blocked":
        return
    report = _quality_report_for_run(result)
    manifest = _dict(report.get("report_quality_manifest"))
    issues = [deepcopy(item) for item in _list(manifest.get("issues")) if isinstance(item, dict)]
    critical = [item for item in issues if str(item.get("severity") or "").lower() == "critical"]
    codes = [str(item.get("code") or "unknown")[:80] for item in critical]
    messages = [_bounded(item.get("message"), 220) for item in critical]
    result["report_quality_manifest"] = manifest
    result["report_quality_issues"] = issues[:40]
    result["report_quality_blockers"] = codes
    report_id = str(report.get("report_id") or "")
    result["mid_report"] = {
        "status": "blocked",
        "report_id": report_id,
        "report_path": report.get("report_path") or "mid_run",
        "report_version": report.get("report_version") or "",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    detail = "; ".join(codes) if codes else "unknown_quality_check"
    result["report_generation_error"] = (
        f"Mid draft blocked by {len(critical)} critical report-quality check(s): {detail}."
    )
    result["report_generation_note"] = result["report_generation_error"]
    _replace_step(
        progress,
        "reports",
        "blocked",
        result["report_generation_error"],
        {
            "report_id": report_id,
            "quality_status": manifest.get("status") or "blocked",
            "quality_score": manifest.get("quality_score"),
            "critical_issue_count": len(critical),
            "critical_issue_codes": codes,
            "critical_issue_messages": messages,
            "rendered_format_status": _dict(manifest.get("rendered_formats")).get("status") or "unknown",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def normalize_mid_terminal_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    progress = [deepcopy(item) for item in _list(output.get("progress")) if isinstance(item, dict)]
    downstream_complete = any(
        _step_status(progress, step).lower() in _COMPLETE
        for step in ("evidence_attachment", "scoring", "score_reconciliation")
    )
    terminal_scanner = _scanner_terminal_status(output, progress)

    if downstream_complete:
        _replace_step(
            progress,
            "scanner_reconciliation",
            "complete",
            "Terminal scanner evidence was reconciled before evidence attachment and technical scoring continued.",
            {
                "scanner_status": terminal_scanner or "terminal_status_retained",
                "scan_id": str(_dict(output.get("scanner")).get("scan_id") or _dict(output.get("scanner_evidence")).get("scan_id") or ""),
                "same_run_identity_preserved": True,
            },
        )
        scanner = deepcopy(_dict(output.get("scanner")))
        scanner_evidence = deepcopy(_dict(output.get("scanner_evidence")))
        if terminal_scanner:
            scanner["status"] = terminal_scanner
            scanner_evidence["scanner_status"] = terminal_scanner
        if scanner:
            output["scanner"] = scanner
        if scanner_evidence:
            output["scanner_evidence"] = scanner_evidence

    _attach_quality_failure_truth(output, progress)
    report_status = str(output.get("report_generation_status") or "").lower()
    approval_status = str(output.get("approval_request_status") or "").lower()

    if report_status == "blocked":
        output["status"] = "blocked"
        output["current_stage"] = "reports"
        output["progress_percent"] = 100
        output["continuation_required"] = False
        output["recovery_required"] = False
        _replace_step(
            progress,
            "approval_request",
            "not_started",
            "Human review request was not created because the Mid draft did not pass the report-quality gate.",
            {"report_quality_gate": "blocked"},
        )
    elif approval_status in _BLOCKED:
        output["status"] = "blocked"
        output["current_stage"] = "approval_request"
        output["progress_percent"] = 100
        output["continuation_required"] = False
    elif report_status == "complete" and bool(_dict(output.get("approval_request")).get("approval_id")):
        output["status"] = "complete"
        output["current_stage"] = "complete"
        output["progress_percent"] = 100
        output["continuation_required"] = False

    assessment = deepcopy(_dict(output.get("assessment")))
    maturity = _dict(assessment.get("maturity_signal"))
    if maturity:
        output["maturity_signal"] = deepcopy(maturity)
        if isinstance(maturity.get("score"), (int, float)):
            output["technical_score"] = maturity.get("score")
    coverage = assessment.get("evidence_coverage") or output.get("evidence_coverage")
    if isinstance(coverage, dict):
        output["evidence_coverage"] = deepcopy(coverage)
    output["progress"] = progress
    output["mid_terminal_truth_version"] = MID_TERMINAL_TRUTH_VERSION
    output["human_review_required"] = True
    output["client_ready"] = False
    return output


def _persist_normalized(result: dict[str, Any]) -> None:
    from nico import mid_assessment_runs
    from nico.storage import STORE, utc_now

    run_id = str(result.get("run_id") or "")
    if not run_id:
        return
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        return
    updated = deepcopy(record)
    updated["status"] = str(result.get("status") or updated.get("status") or "unknown")
    updated["response"] = mid_assessment_runs._retained_response(result)
    updated["report_id"] = str(_dict(result.get("mid_report")).get("report_id") or updated.get("report_id") or "")
    updated["approval_id"] = str(_dict(result.get("approval_request")).get("approval_id") or updated.get("approval_id") or "")
    updated["updated_at"] = utc_now()
    STORE.put("assessment_runs", run_id, updated)


def _terminal_retained_response(record: dict[str, Any]) -> dict[str, Any] | None:
    response = _dict(record.get("response"))
    report_status = str(response.get("report_generation_status") or "").lower()
    approval_status = str(response.get("approval_request_status") or "").lower()
    if report_status != "blocked" and approval_status not in _BLOCKED:
        return None
    result = normalize_mid_terminal_truth(response)
    result["run_id"] = str(record.get("run_id") or result.get("run_id") or "")
    result["customer_id"] = str(record.get("customer_id") or result.get("customer_id") or "default_customer")
    result["project_id"] = str(record.get("project_id") or result.get("project_id") or "default_project")
    result["repository"] = str(record.get("repository") or result.get("repository") or "")
    result["status_refresh"] = True
    result["continuation_required"] = False
    result["status_read_path"] = {
        "version": MID_TERMINAL_TRUTH_VERSION,
        "mode": "retained_terminal_report_gate",
        "read_only": True,
        "orchestrator_reentered": False,
        "repository_recaptured": False,
        "assessment_run_rewritten": False,
    }
    return result


async def mid_status_endpoint(run_id: str, request: Request) -> dict[str, Any]:
    from nico import mid_assessment_api
    from nico.storage import STORE

    payload: dict[str, Any] = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}
    customer_id = _bounded(payload.get("customer_id") or request.query_params.get("customer_id") or "default_customer", 120)
    project_id = _bounded(payload.get("project_id") or request.query_params.get("project_id") or "default_project", 120)
    record = STORE.get("assessment_runs", run_id)
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found."})
    if not _scope_matches(record, customer_id or "default_customer", project_id or "default_project"):
        raise HTTPException(status_code=404, detail={"status": "not_found", "message": "Mid Assessment run not found in this scope."})
    terminal = _terminal_retained_response(record)
    if terminal is not None:
        return terminal
    try:
        model = mid_assessment_api.MidAssessmentStatusRequest(**payload)
        return normalize_mid_terminal_truth(mid_assessment_api.mid_assessment_status_response(run_id, model))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "temporarily_unavailable",
                "code": "mid_status_read_failed",
                "message": "NICO could not continue the exact Mid lifecycle state. The run remains preserved; inspect Recovery before starting another run.",
                "run_id": run_id,
                "assessment_type": "mid",
                "failure_type": type(exc).__name__[:80],
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        ) from exc


def install_mid_terminal_truth_patch() -> dict[str, Any]:
    from nico import lifecycle_status_hardening as lifecycle
    from nico import mid_assessment_api, mid_live_status_api

    artifact_current: Callable[..., dict[str, Any]] = mid_assessment_api._attach_automatic_mid_artifacts
    artifact_installed = False
    if not getattr(artifact_current, _ARTIFACT_MARKER, False):
        @wraps(artifact_current)
        def artifacts_with_terminal_truth(*args: Any, **kwargs: Any) -> dict[str, Any]:
            normalized = normalize_mid_terminal_truth(artifact_current(*args, **kwargs))
            _persist_normalized(normalized)
            return normalized

        setattr(artifacts_with_terminal_truth, _ARTIFACT_MARKER, True)
        setattr(artifacts_with_terminal_truth, "_nico_previous", artifact_current)
        mid_assessment_api._attach_automatic_mid_artifacts = artifacts_with_terminal_truth
        artifact_installed = True

    live_current: Callable[..., dict[str, Any]] = mid_live_status_api.mid_live_status_response
    live_installed = False
    if not getattr(live_current, _LIVE_MARKER, False):
        @wraps(live_current)
        def live_with_terminal_truth(run_id: str, customer_id: str = "", project_id: str = "") -> dict[str, Any]:
            from nico.storage import STORE

            record = STORE.get("assessment_runs", run_id)
            if isinstance(record, dict) and str(record.get("workflow") or "") == "mid_assessment":
                if (not customer_id or not project_id) or _scope_matches(
                    record,
                    customer_id or str(record.get("customer_id") or "default_customer"),
                    project_id or str(record.get("project_id") or "default_project"),
                ):
                    terminal = _terminal_retained_response(record)
                    if terminal is not None:
                        return terminal
            return normalize_mid_terminal_truth(live_current(run_id, customer_id=customer_id, project_id=project_id))

        setattr(live_with_terminal_truth, _LIVE_MARKER, True)
        setattr(live_with_terminal_truth, "_nico_previous", live_current)
        mid_live_status_api.mid_live_status_response = live_with_terminal_truth
        lifecycle.mid_live_status_response = live_with_terminal_truth
        live_installed = True

    installer_current = lifecycle.install_lifecycle_status_hardening
    installer_installed = False
    if not getattr(installer_current, _INSTALLER_MARKER, False):
        @wraps(installer_current)
        def installer_with_mid_post_status(app: Any) -> dict[str, Any]:
            result = dict(installer_current(app))
            lifecycle._replace_route(app, "POST", MID_STATUS_PATH, mid_status_endpoint, ["assessment", "mid", "status"])
            result.update(
                {
                    "version": MID_TERMINAL_TRUTH_VERSION,
                    "mid_canonical_status_bounded": True,
                    "mid_not_found_generic_500_possible": False,
                    "mid_terminal_report_gate_read_only": True,
                }
            )
            return result

        setattr(installer_with_mid_post_status, _INSTALLER_MARKER, True)
        setattr(installer_with_mid_post_status, "_nico_previous", installer_current)
        lifecycle.install_lifecycle_status_hardening = installer_with_mid_post_status
        installer_installed = True

    return {
        "status": "installed" if artifact_installed or live_installed or installer_installed else "already_installed",
        "version": MID_TERMINAL_TRUTH_VERSION,
        "automatic_artifact_truth_installed": artifact_installed,
        "live_terminal_truth_installed": live_installed,
        "canonical_post_status_installed": installer_installed,
        "stale_scanner_running_after_downstream_completion": False,
        "report_quality_issue_codes_exposed": True,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_STATUS_PATH",
    "MID_TERMINAL_TRUTH_VERSION",
    "install_mid_terminal_truth_patch",
    "mid_status_endpoint",
    "normalize_mid_terminal_truth",
]
