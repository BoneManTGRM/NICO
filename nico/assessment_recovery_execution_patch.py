from typing import Any

from fastapi import HTTPException

from nico.assessment_checkpointed_orchestration import (
    run_checkpointed_assessment_orchestration,
)
from nico.assessment_execution_checkpoints import (
    build_checkpoint_result,
    make_checkpoint_writer,
)
from nico.full_assessment_orchestrator import (
    run_full_assessment_orchestration as canonical_orchestrator,
)
from nico.storage import STORE

_PATCHED = False


def _attempt(run_id: str) -> int:
    record = STORE.get("assessment_runs", run_id) or {}
    recovery = record.get("recovery") if isinstance(record.get("recovery"), dict) else {}
    if not recovery:
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        recovery = response.get("recovery") if isinstance(response.get("recovery"), dict) else {}
    return max(0, int(recovery.get("attempt") or 0))


def _run_checkpointed(
    api_module: Any,
    payload: dict[str, Any],
    handlers: dict[str, Any],
    writer: Any,
) -> dict[str, Any]:
    orchestrator = api_module.run_full_assessment_orchestration
    return run_checkpointed_assessment_orchestration(
        payload,
        handlers=handlers,
        checkpoint=writer,
        orchestrator=orchestrator,
        wrap_handlers=orchestrator is canonical_orchestrator,
    )


def install_assessment_recovery_execution_patch() -> dict[str, Any]:
    global _PATCHED
    if _PATCHED:
        return {"installed": True, "idempotent_reuse": True}

    import nico.full_assessment_api as full_api
    import nico.mid_assessment_api as mid_api

    def full_assessment_response(
        req: full_api.FullAssessmentRequest,
    ) -> dict[str, Any]:
        payload = full_api._model_payload(req)
        payload["run_id"] = str(payload.get("run_id") or full_api.new_id("fullrun"))
        writer = make_checkpoint_writer(
            payload,
            workflow="full_assessment",
            service_tier=str(payload.get("mode") or "full"),
        )
        handlers = full_api.idempotent_full_assessment_handlers(
            timeframe_days=int(payload.get("timeframe_days") or 180)
        )
        result = _run_checkpointed(full_api, payload, handlers, writer)
        result = build_checkpoint_result(
            result,
            step="orchestration",
            phase="orchestration_finalized",
            recovery_attempt=_attempt(payload["run_id"]),
        )
        result = full_api._attach_repository_evidence(result)
        result = full_api._attach_assessment_truth_summary(result)
        result = full_api._with_report_path(result)
        result = full_api._attach_persisted_delivery(result)
        result = full_api._record_result(result, payload, restored=False)
        if result.get("status") == "blocked":
            raise HTTPException(
                status_code=400,
                detail=full_api._blocked_detail(
                    result,
                    "Request blocked by NICO safety, authorization, or review policy.",
                ),
            )
        return result

    def full_assessment_status_response(
        run_id: str,
        req: full_api.FullAssessmentStatusRequest,
    ) -> dict[str, Any]:
        request_payload = full_api._model_payload(req)
        explicit_fields = full_api.explicit_model_fields(req)
        payload, record = full_api.build_status_payload(
            run_id,
            request_payload,
            explicit_fields,
        )
        saved_request = dict((record or {}).get("request") or {})
        auto_continue = (
            bool(request_payload.get("auto_continue"))
            if "auto_continue" in explicit_fields
            else bool(saved_request.get("auto_continue", True))
        )
        plan = full_api.plan_full_assessment_continuation(
            payload,
            record,
            auto_continue=auto_continue,
        )
        continuation_payload = plan["payload"]
        writer = make_checkpoint_writer(
            continuation_payload,
            workflow="full_assessment",
            service_tier=str(continuation_payload.get("mode") or "full"),
        )
        handlers = full_api.idempotent_full_assessment_handlers(
            timeframe_days=int(continuation_payload.get("timeframe_days") or 180)
        )
        result = _run_checkpointed(
            full_api,
            continuation_payload,
            handlers,
            writer,
        )
        result = full_api.apply_full_assessment_continuation(result, plan)
        result["status_refresh"] = True
        result = build_checkpoint_result(
            result,
            step="orchestration",
            phase="orchestration_finalized",
            recovery_attempt=_attempt(run_id),
        )
        result = full_api._attach_repository_evidence(result)
        result = full_api._attach_assessment_truth_summary(result)
        result = full_api._with_report_path(result)
        result = full_api._attach_persisted_delivery(result)
        result = full_api._record_result(
            result,
            continuation_payload,
            restored=bool(record),
        )
        if result.get("status") == "blocked":
            raise HTTPException(
                status_code=400,
                detail=full_api._blocked_detail(
                    result,
                    "Status refresh blocked by NICO safety, authorization, or review policy.",
                ),
            )
        return result

    def mid_assessment_response(
        req: mid_api.MidAssessmentRunRequest,
    ) -> dict[str, Any]:
        payload = mid_api._payload(req)
        payload.update(
            {
                "run_id": mid_api.new_id("midrun"),
                "mode": mid_api.MID_ASSESSMENT_TYPE,
                "build_reports": False,
                "create_final_review_request": False,
            }
        )
        writer = make_checkpoint_writer(
            payload,
            workflow="mid_assessment",
            service_tier="mid",
        )
        handlers = mid_api.mid_assessment_handlers(
            int(payload.get("timeframe_days") or 180)
        )
        result = _run_checkpointed(mid_api, payload, handlers, writer)
        result = build_checkpoint_result(
            result,
            step="orchestration",
            phase="orchestration_finalized",
            recovery_attempt=_attempt(payload["run_id"]),
        )
        result = mid_api._attach_mid_evidence(result)
        result = mid_api._attach_mid_contract(result)
        result = mid_api._record(result, payload, restored=False)
        if result.get("status") == "blocked" or mid_api._has_blocked_progress(result):
            raise HTTPException(
                status_code=400,
                detail=mid_api._blocked_detail(
                    result,
                    "Mid Assessment was blocked by authorization, repository access, or snapshot validation.",
                ),
            )
        result = mid_api._attach_automatic_mid_artifacts(result, payload)
        return result

    def mid_assessment_status_response(
        run_id: str,
        req: mid_api.MidAssessmentStatusRequest,
    ) -> dict[str, Any]:
        if not str(run_id or "").startswith("midrun_"):
            raise HTTPException(
                status_code=404,
                detail={"status": "not_found", "message": "Mid Assessment run not found."},
            )
        request_payload = mid_api._payload(req)
        explicit = mid_api.explicit_model_fields(req)
        payload, record = mid_api.build_mid_status_payload(
            run_id,
            request_payload,
            explicit,
        )
        if not record:
            raise HTTPException(
                status_code=404,
                detail={"status": "not_found", "message": "Mid Assessment run not found."},
            )
        saved_request = dict(record.get("request") or {})
        auto_continue = (
            bool(request_payload.get("auto_continue"))
            if "auto_continue" in explicit
            else bool(saved_request.get("auto_continue", True))
        )
        plan = mid_api.plan_full_assessment_continuation(
            payload,
            record,
            auto_continue=auto_continue,
        )
        continuation = plan["payload"]
        continuation["mode"] = mid_api.MID_ASSESSMENT_TYPE
        continuation["build_reports"] = False
        continuation["create_final_review_request"] = False
        writer = make_checkpoint_writer(
            continuation,
            workflow="mid_assessment",
            service_tier="mid",
        )
        handlers = mid_api.mid_assessment_handlers(
            int(continuation.get("timeframe_days") or 180)
        )
        result = _run_checkpointed(mid_api, continuation, handlers, writer)
        result = mid_api.apply_full_assessment_continuation(result, plan)
        result["status_refresh"] = True
        result = build_checkpoint_result(
            result,
            step="orchestration",
            phase="orchestration_finalized",
            recovery_attempt=_attempt(run_id),
        )
        result = mid_api._attach_mid_evidence(result)
        result = mid_api._attach_mid_contract(result)
        result = mid_api._record(result, continuation, restored=True)
        if result.get("status") == "blocked" or mid_api._has_blocked_progress(result):
            raise HTTPException(
                status_code=400,
                detail=mid_api._blocked_detail(
                    result,
                    "Mid Assessment status refresh was blocked by run or snapshot identity validation.",
                ),
            )
        result = mid_api._attach_automatic_mid_artifacts(result, continuation)
        return result

    full_api.full_assessment_response = full_assessment_response
    full_api.full_assessment_status_response = full_assessment_status_response
    mid_api.mid_assessment_response = mid_assessment_response
    mid_api.mid_assessment_status_response = mid_assessment_status_response
    _PATCHED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "full_run_checkpointed": True,
        "mid_run_checkpointed": True,
        "automatic_resume": False,
    }


__all__ = ["install_assessment_recovery_execution_patch"]
