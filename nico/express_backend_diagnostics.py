from __future__ import annotations

import logging
import os
import re
import threading
from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

import nico.express_async_api as express
import nico.express_review_target as express_review
from nico.express_snapshot_pipeline import (
    EXPRESS_SNAPSHOT_PIPELINE_VERSION,
    attach_exact_express_scanner_evidence,
    start_express_snapshot_scan,
    wait_for_express_snapshot_scan,
)
from nico.storage import utc_now

EXPRESS_BACKEND_DIAGNOSTICS_VERSION = "nico.express_backend_diagnostics.v3"
_MARKER = "_nico_express_backend_diagnostics_v1"
_LOGGER = logging.getLogger(__name__)
_SAFE_EXCEPTION_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,119}$")
_SAFE_STAGES = {
    "record_running",
    "import_api",
    "validate_request",
    "start_snapshot_scanner",
    "collect_assessment",
    "classify_blocked_result",
    "wait_snapshot_scanner",
    "attach_exact_scanner_evidence",
    "enrich_scanner_evidence",
    "apply_report_accuracy",
    "attach_review_target",
    "polish_result",
    "finalize_consistency",
    "reattach_review_target",
    "attach_evidence_bundle",
    "attach_client_acceptance",
    "sanitize_response",
    "validate_final_artifacts",
    "persist_final_response",
}


def _safe_stage(value: str) -> str:
    return value if value in _SAFE_STAGES else "unknown_backend_stage"


def _safe_exception_class(exc: BaseException) -> str:
    value = type(exc).__name__[:120]
    return value if _SAFE_EXCEPTION_CLASS.fullmatch(value) else "BackendException"


def _diagnostic(run_id: str, stage: str, exc: BaseException) -> dict[str, str]:
    return {
        "diagnostic_id": f"express_diag_{uuid4().hex[:24]}",
        "failure_stage": _safe_stage(stage),
        "exception_class": _safe_exception_class(exc),
        "diagnostic_recorded_at": utc_now(),
        "diagnostic_run_id": run_id,
    }


def _attach_failure_stage(failure: dict[str, Any], stage: str) -> dict[str, Any]:
    safe_stage = _safe_stage(stage)
    failure["failure_stage"] = safe_stage
    progress = failure.get("progress") if isinstance(failure.get("progress"), list) else []
    if progress and isinstance(progress[0], dict):
        evidence = progress[0].get("evidence") if isinstance(progress[0].get("evidence"), dict) else {}
        evidence["failure_stage"] = safe_stage
        progress[0]["evidence"] = evidence
    return failure


def _diagnostic_failure(
    run_id: str,
    request_payload: dict[str, Any],
    stage: str,
    exc: BaseException,
) -> dict[str, Any]:
    diagnostic = _diagnostic(run_id, stage, exc)
    message = (
        f"Express assessment execution failed during {diagnostic['failure_stage']}. "
        f"Diagnostic ID {diagnostic['diagnostic_id']}; exception class {diagnostic['exception_class']}. "
        "Internal exception text remains redacted. Review authorized backend logs before retrying."
    )
    failure = express._response(
        run_id,
        request_payload,
        "failed",
        message,
        code="express_backend_execution_failed",
        stage="failed",
        progress_percent=100,
        evidence=diagnostic,
    )
    failure.update(diagnostic)
    return _attach_failure_stage(failure, stage)


def _validated_payload(api_main: Any, request_payload: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    req = api_main.GithubAssessmentRequest(**request_payload)
    validated = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    payload = deepcopy(request_payload)
    payload.update(validated)
    payload["authorized"] = bool(request_payload.get("authorized") or request_payload.get("authorization_confirmed"))
    payload["authorization_confirmed"] = bool(request_payload.get("authorization_confirmed") or request_payload.get("authorized"))
    payload["authorized_by"] = str(request_payload.get("authorized_by") or "requester_confirmation")
    payload["authorization_scope"] = str(request_payload.get("authorization_scope") or "repository assessment only")
    return req, payload


def _clear_request_local_payload() -> None:
    try:
        express_review._consume_final_express_payload()
    except Exception:
        _LOGGER.warning("Could not clear request-local Express payload capture", exc_info=True)


def _worker_identity(worker_started_at: str, backend_stage: str) -> dict[str, Any]:
    return {
        "worker_started": True,
        "worker_started_at": worker_started_at,
        "worker_process_id": os.getpid(),
        "worker_thread": threading.current_thread().name[:120],
        "backend_stage": _safe_stage(backend_stage),
    }


def _publish_live_stage(
    run_id: str,
    request_payload: dict[str, Any],
    *,
    ui_stage: str,
    backend_stage: str,
    message: str,
    worker_started_at: str,
    scanner: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = _worker_identity(worker_started_at, backend_stage)
    response = express._response(
        run_id,
        request_payload,
        "running",
        message,
        stage=ui_stage,
        evidence=evidence,
    )
    response.update(evidence)
    response["status_truth"] = "durable_worker_stage"
    if scanner:
        response["scanner"] = deepcopy(scanner)
        response["scan_id"] = str(scanner.get("scan_id") or "")
    elif ui_stage == "repository_evidence":
        response["scanner"] = {
            "status": "pending",
            "current_stage": "awaiting_repository_snapshot",
            "progress_percent": 0,
            "message": "Exact-commit scanner execution starts after snapshot capture.",
        }
    if snapshot:
        response["repository_snapshot"] = deepcopy(snapshot)
        response["snapshot_id"] = str(snapshot.get("snapshot_id") or "")
        response["snapshot_commit_sha"] = str(snapshot.get("commit_sha") or "")
    express._record(run_id, request_payload, response)
    return response


def _scanner_projection(result: dict[str, Any], *, fallback_status: str, fallback_stage: str) -> dict[str, Any]:
    candidates = (
        result.get("scanner"),
        result.get("scanner_run"),
        result.get("scanner_evidence"),
        result.get("scanner_worker"),
    )
    scanner = next((deepcopy(value) for value in candidates if isinstance(value, dict) and value), {})
    scanner.setdefault("status", fallback_status)
    scanner.setdefault("current_stage", fallback_stage)
    scanner.setdefault("progress_percent", 100 if fallback_status == "complete" else 0)
    return scanner


def _scan_message(scan: dict[str, Any]) -> str:
    status = str(scan.get("status") or "unknown")
    tool = str(scan.get("active_tool") or "").replace("-", " ")
    progress = max(0, min(100, int(scan.get("progress_percent") or 0)))
    if tool and status in {"queued", "running"}:
        return f"Exact-snapshot scanner is running {tool} ({progress}% scanner progress)."
    return f"Exact-snapshot scanner status is {status} ({progress}% scanner progress)."


def _validate_final_artifacts(result: dict[str, Any]) -> None:
    scanner = _scanner_projection(result, fallback_status="not_started", fallback_stage="not_started")
    attachment = result.get("worker_evidence_attachment") if isinstance(result.get("worker_evidence_attachment"), dict) else {}
    if scanner.get("status") != "complete" or scanner.get("snapshot_match") is not True:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "failed",
                "code": "express_scanner_completion_gate_failed",
                "message": "Express report generation was blocked because exact-snapshot scanner completion was not verified.",
                "scanner": scanner,
                "scan_id": scanner.get("scan_id") or "",
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        )
    if attachment.get("status") != "complete" or attachment.get("mode") != "exact_same_run_snapshot_bound":
        raise HTTPException(
            status_code=503,
            detail={
                "status": "failed",
                "code": "express_scanner_attachment_gate_failed",
                "message": "Express report generation was blocked because the completed scanner was not attached to the same exact run and snapshot.",
                "scanner": scanner,
                "scan_id": scanner.get("scan_id") or "",
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        )

    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    markdown = str(reports.get("markdown") or "")
    html = str(reports.get("html") or "")
    pdf = str(reports.get("pdf_base64") or reports.get("pdf") or "")
    if len(markdown.strip()) < 500 or len(html.strip()) < 500 or len(pdf.strip()) < 100:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "failed",
                "code": "express_report_artifacts_missing",
                "message": "Express execution finished its analysis but did not produce complete Markdown, HTML, and PDF report artifacts. NICO refused to publish a completed result.",
                "scanner": scanner,
                "scan_id": scanner.get("scan_id") or "",
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        )
    manifest = result.get("report_quality_manifest") if isinstance(result.get("report_quality_manifest"), dict) else {}
    if manifest.get("status") == "blocked":
        raise HTTPException(
            status_code=503,
            detail={
                "status": "blocked",
                "code": "express_report_quality_gate_blocked",
                "message": "The Express report quality gate blocked the generated report. The draft was not published as complete.",
                "scanner": scanner,
                "scan_id": scanner.get("scan_id") or "",
                "report_quality_manifest": manifest,
                "duplicate_start_allowed": False,
                "human_review_required": True,
                "client_ready": False,
            },
        )


def execute_with_diagnostics(run_id: str, request_payload: dict[str, Any]) -> None:
    """Execute one Express run with exact-snapshot scanners and bounded diagnostics."""

    stage = "record_running"
    worker_started_at = utc_now()
    try:
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="repository_evidence",
            backend_stage=stage,
            message="Express worker started. Capturing the exact repository commit before analysis and scanner execution.",
            worker_started_at=worker_started_at,
        )

        stage = "import_api"
        api_main = express.import_module("nico.api.main")

        stage = "validate_request"
        _req, payload = _validated_payload(api_main, request_payload)

        stage = "start_snapshot_scanner"
        snapshot, initial_scan = start_express_snapshot_scan(run_id, payload)
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="repository_evidence",
            backend_stage=stage,
            message="Exact repository snapshot captured. Hosted evidence collection and the scanner suite are running against the same commit.",
            worker_started_at=worker_started_at,
            scanner=initial_scan,
            snapshot=snapshot,
        )

        stage = "collect_assessment"
        if api_main.extract_scanner_worker_artifact(payload):
            result = api_main.run_github_assessment_with_scanner_artifacts(payload)
        else:
            result = api_main.run_github_assessment(payload)

        if result.get("status") == "blocked":
            stage = "classify_blocked_result"
            blocked = express._blocked_detail(result, run_id, request_payload)
            blocked.update(
                {
                    "repository": request_payload.get("repository") or "",
                    "customer_id": request_payload.get("customer_id") or "default_customer",
                    "project_id": request_payload.get("project_id") or "default_project",
                    "persistence": express._persistence(),
                    "updated_at": utc_now(),
                    "scanner": initial_scan,
                    "scan_id": initial_scan.get("scan_id") or "",
                    "repository_snapshot": snapshot,
                    **_worker_identity(worker_started_at, stage),
                }
            )
            express._record(run_id, request_payload, blocked)
            return

        result["run_id"] = run_id

        stage = "wait_snapshot_scanner"

        def publish_scan(scan: dict[str, Any]) -> None:
            _publish_live_stage(
                run_id,
                request_payload,
                ui_stage="scanner_reconciliation",
                backend_stage=stage,
                message=_scan_message(scan),
                worker_started_at=worker_started_at,
                scanner=scan,
                snapshot=snapshot,
            )

        scan = wait_for_express_snapshot_scan(
            run_id,
            snapshot,
            initial_scan,
            on_update=publish_scan,
        )

        stage = "attach_exact_scanner_evidence"
        result = attach_exact_express_scanner_evidence(result, snapshot, scan)
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="scanner_reconciliation",
            backend_stage=stage,
            message="Exact-snapshot scanner suite completed and its same-run evidence was attached.",
            worker_started_at=worker_started_at,
            scanner=scan,
            snapshot=snapshot,
        )

        stage = "enrich_scanner_evidence"
        result = api_main.enrich_payload_with_scanner_evidence(result)

        stage = "apply_report_accuracy"
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="accuracy_review",
            backend_stage=stage,
            message="Scanner evidence is attached. Applying source classification, contradiction removal, unavailable-evidence disclosure, and false-positive controls.",
            worker_started_at=worker_started_at,
            scanner=scan,
            snapshot=snapshot,
        )
        result = api_main.apply_report_accuracy(result)

        stage = "attach_review_target"
        result = api_main.attach_express_review_target(result, payload)

        stage = "polish_result"
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="score_reconciliation",
            backend_stage=stage,
            message="Evidence classification is complete. Reconciling section scores and maturity against the final retained evidence without score inflation.",
            worker_started_at=worker_started_at,
            scanner=scan,
            snapshot=snapshot,
        )
        result = api_main.polish_express_result(result)

        stage = "finalize_consistency"
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="report_generation",
            backend_stage=stage,
            message="Final scores are available. Generating Markdown, HTML, professional PDF, repair intelligence, and the decision summary.",
            worker_started_at=worker_started_at,
            scanner=scan,
            snapshot=snapshot,
        )
        result = api_main.finalize_express_result_consistency(result)

        stage = "reattach_review_target"
        result = api_main.attach_express_review_target(result, payload)

        stage = "attach_evidence_bundle"
        _publish_live_stage(
            run_id,
            request_payload,
            ui_stage="truth_and_review_gates",
            backend_stage=stage,
            message="Report formats are generated. Applying evidence-ledger, consistency, acceptance, report-quality, and required human-review gates.",
            worker_started_at=worker_started_at,
            scanner=scan,
            snapshot=snapshot,
        )
        result = api_main.attach_evidence_artifact_bundle(result)

        stage = "attach_client_acceptance"
        result = api_main.attach_client_acceptance_gate(result)

        stage = "sanitize_response"
        response_payload = api_main.safe_assessment_response_payload(result)
        response_payload["run_id"] = run_id
        response_payload["assessment_type"] = "express"
        response_payload["service_tier"] = "express"
        response_payload["human_review_required"] = True
        response_payload["client_ready"] = False
        response_payload["persistence"] = express._persistence()
        response_payload["current_stage"] = "complete"
        response_payload["progress_percent"] = 100
        response_payload.update(_worker_identity(worker_started_at, stage))
        response_payload["scanner"] = deepcopy(scan)
        response_payload["scan_id"] = str(scan.get("scan_id") or "")
        response_payload["repository_snapshot"] = deepcopy(snapshot)
        response_payload["snapshot_id"] = str(snapshot.get("snapshot_id") or "")
        response_payload["snapshot_commit_sha"] = str(snapshot.get("commit_sha") or "")
        response_payload["worker_evidence_attachment"] = deepcopy(result.get("worker_evidence_attachment") or {})
        response_payload["updated_at"] = utc_now()

        stage = "validate_final_artifacts"
        _validate_final_artifacts(response_payload)
        response_payload["progress"] = express._stage_progress(
            "complete",
            "complete",
            "Express assessment completed. Exact-snapshot scanner evidence and draft report artifacts are ready for required human review.",
            evidence={
                **_worker_identity(worker_started_at, stage),
                "scan_id": scan.get("scan_id") or "",
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
                "snapshot_match": True,
                "report_formats_ready": True,
                "score_reconciled": True,
            },
        )
        response_payload["backend_stage"] = stage
        api_main._LAST_HOSTED_ASSESSMENT = response_payload

        _clear_request_local_payload()
        stage = "persist_final_response"
        response_payload["backend_stage"] = stage
        express._record(run_id, request_payload, response_payload)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        detail_status = str(detail.get("status") or "").lower()
        terminal_status = "interrupted" if detail_status == "interrupted" else "blocked" if detail_status == "blocked" or exc.status_code < 500 else "failed"
        failure = express._response(
            run_id,
            request_payload,
            terminal_status,
            str(detail.get("message") or "Express assessment execution was blocked.")[:320],
            code=str(detail.get("code") or f"http_{exc.status_code}")[:80],
            stage=terminal_status,
            progress_percent=100,
            evidence={
                **_worker_identity(worker_started_at, stage),
                "http_status": exc.status_code,
                "scan_id": detail.get("scan_id") or "",
                "recovery_required": bool(detail.get("recovery_required")),
            },
        )
        failure.update(_worker_identity(worker_started_at, stage))
        for key in (
            "scan_id",
            "scanner",
            "repository_snapshot",
            "recovery_required",
            "recovery_path",
            "report_quality_manifest",
        ):
            if key in detail:
                failure[key] = deepcopy(detail[key])
        failure["client_ready"] = False
        _attach_failure_stage(failure, stage)
        express._record(run_id, request_payload, failure)
    except Exception as exc:
        failure = _diagnostic_failure(run_id, request_payload, stage, exc)
        failure.update(_worker_identity(worker_started_at, stage))
        _LOGGER.exception(
            "Express backend execution failed diagnostic_id=%s run_id=%s stage=%s exception_class=%s",
            failure["diagnostic_id"],
            run_id,
            failure["failure_stage"],
            failure["exception_class"],
        )
        try:
            express._record(run_id, request_payload, failure)
        except Exception:
            _LOGGER.exception(
                "Express terminal diagnostic record could not be persisted diagnostic_id=%s run_id=%s",
                failure["diagnostic_id"],
                run_id,
            )
    finally:
        _clear_request_local_payload()
        express._release_active(run_id, request_payload)


def install_express_backend_diagnostics() -> dict[str, Any]:
    current: Callable[[str, dict[str, Any]], None] = express._execute
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
            "bounded_diagnostics": True,
            "truthful_live_stages": True,
            "exact_snapshot_scanner_required": True,
            "report_artifact_gate": True,
            "single_final_record_write": True,
        }

    setattr(execute_with_diagnostics, _MARKER, True)
    setattr(execute_with_diagnostics, "_nico_previous", current)
    express._execute = execute_with_diagnostics
    return {
        "status": "installed",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "snapshot_pipeline_version": EXPRESS_SNAPSHOT_PIPELINE_VERSION,
        "bounded_diagnostics": True,
        "truthful_live_stages": True,
        "worker_start_identity": True,
        "exact_snapshot_scanner_required": True,
        "same_run_scanner_identity_required": True,
        "report_artifact_gate": True,
        "report_without_scanner_allowed": False,
        "public_exception_text_exposed": False,
        "authorized_traceback_logging": True,
        "single_final_record_write": True,
        "automatic_retry": False,
        "replacement_run": False,
    }


__all__ = [
    "EXPRESS_BACKEND_DIAGNOSTICS_VERSION",
    "execute_with_diagnostics",
    "install_express_backend_diagnostics",
]
