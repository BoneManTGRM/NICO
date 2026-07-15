from __future__ import annotations

import logging
import re
from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

import nico.express_async_api as express
import nico.express_review_target as express_review
from nico.storage import utc_now

EXPRESS_BACKEND_DIAGNOSTICS_VERSION = "nico.express_backend_diagnostics.v1"
_MARKER = "_nico_express_backend_diagnostics_v1"
_LOGGER = logging.getLogger(__name__)
_SAFE_EXCEPTION_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,119}$")
_SAFE_STAGES = {
    "record_running",
    "import_api",
    "validate_request",
    "collect_assessment",
    "classify_blocked_result",
    "attach_existing_worker_evidence",
    "enrich_scanner_evidence",
    "apply_report_accuracy",
    "attach_review_target",
    "polish_result",
    "finalize_consistency",
    "reattach_review_target",
    "attach_evidence_bundle",
    "attach_client_acceptance",
    "sanitize_response",
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
        progress[0]["step"] = safe_stage
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
    )
    failure.update(diagnostic)
    progress = failure.get("progress") if isinstance(failure.get("progress"), list) else []
    if progress and isinstance(progress[0], dict):
        progress[0]["step"] = diagnostic["failure_stage"]
        evidence = progress[0].get("evidence") if isinstance(progress[0].get("evidence"), dict) else {}
        evidence.update(diagnostic)
        progress[0]["evidence"] = evidence
    return failure


def _validated_payload(api_main: Any, request_payload: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    req = api_main.GithubAssessmentRequest(**request_payload)
    validated = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    payload = deepcopy(request_payload)
    payload.update(validated)
    return req, payload


def _clear_request_local_payload() -> None:
    try:
        express_review._consume_final_express_payload()
    except Exception:
        _LOGGER.warning("Could not clear request-local Express payload capture", exc_info=True)


def execute_with_diagnostics(run_id: str, request_payload: dict[str, Any]) -> None:
    """Execute one accepted Express run with exact-run diagnostics and one final write.

    The public failure record contains only a bounded stage, exception class, and
    non-secret diagnostic ID. The authorized backend log retains the traceback.
    No retry, replacement run, or automatic recovery is introduced here.
    """

    stage = "record_running"
    try:
        running = express._response(
            run_id,
            request_payload,
            "running",
            "Express repository evidence collection and report generation are running on the Railway backend. The browser may poll this exact run without holding one long connection.",
        )
        express._record(run_id, request_payload, running)

        stage = "import_api"
        # Keep the established Express injection seam. Existing tests and bounded
        # runtime wrappers replace express.import_module rather than a second importer.
        api_main = express.import_module("nico.api.main")

        stage = "validate_request"
        _req, payload = _validated_payload(api_main, request_payload)

        stage = "collect_assessment"
        if api_main.extract_scanner_worker_artifact(payload):
            result = api_main.run_github_assessment_with_scanner_artifacts(payload)
        else:
            result = api_main.run_github_assessment(payload)

        if result.get("status") == "blocked":
            stage = "classify_blocked_result"
            blocked = express._blocked_detail(result, run_id)
            blocked.update(
                {
                    "repository": request_payload.get("repository") or "",
                    "customer_id": request_payload.get("customer_id") or "default_customer",
                    "project_id": request_payload.get("project_id") or "default_project",
                    "persistence": express._persistence(),
                    "updated_at": utc_now(),
                }
            )
            express._record(run_id, request_payload, blocked)
            return

        result["run_id"] = run_id

        stage = "attach_existing_worker_evidence"
        result = api_main.attach_existing_worker_evidence(result, payload)

        stage = "enrich_scanner_evidence"
        result = api_main.enrich_payload_with_scanner_evidence(result)

        stage = "apply_report_accuracy"
        result = api_main.apply_report_accuracy(result)

        stage = "attach_review_target"
        result = api_main.attach_express_review_target(result, payload)

        stage = "polish_result"
        result = api_main.polish_express_result(result)

        stage = "finalize_consistency"
        result = api_main.finalize_express_result_consistency(result)

        stage = "reattach_review_target"
        result = api_main.attach_express_review_target(result, payload)

        stage = "attach_evidence_bundle"
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
        response_payload["updated_at"] = utc_now()
        api_main._LAST_HOSTED_ASSESSMENT = response_payload

        # The async lifecycle already owns an exact run record. Persist that final
        # response once rather than routing it through the synchronous compatibility
        # helper and then writing the same run a second time.
        _clear_request_local_payload()
        stage = "persist_final_response"
        express._record(run_id, request_payload, response_payload)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        failure = express._response(
            run_id,
            request_payload,
            "blocked" if exc.status_code < 500 else "failed",
            str(detail.get("message") or "Express assessment execution was blocked.")[:320],
            code=str(detail.get("code") or f"http_{exc.status_code}")[:80],
        )
        _attach_failure_stage(failure, stage)
        express._record(run_id, request_payload, failure)
    except Exception as exc:
        failure = _diagnostic_failure(run_id, request_payload, stage, exc)
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
            "single_final_record_write": True,
        }

    setattr(execute_with_diagnostics, _MARKER, True)
    setattr(execute_with_diagnostics, "_nico_previous", current)
    express._execute = execute_with_diagnostics
    return {
        "status": "installed",
        "version": EXPRESS_BACKEND_DIAGNOSTICS_VERSION,
        "bounded_diagnostics": True,
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
