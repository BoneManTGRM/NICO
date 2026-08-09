from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Mapping

import nico.comprehensive_final_report_background_v1 as background
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.comprehensive_final_report_activity.v1"
_RUNNING_REASON = "final_report_background_publication_in_progress"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _local_phase(lease_id: str) -> tuple[str, bool]:
    """Read bounded same-process ownership without exposing task internals."""

    lock = getattr(background, "_LOCAL_TASKS_LOCK", None)
    tasks = getattr(background, "_LOCAL_TASKS", None)
    if lock is None or not isinstance(tasks, dict):
        return "", False
    with lock:
        state = tasks.get(lease_id)
        if not isinstance(state, Mapping):
            return "", False
        stop = state.get("stop")
        if not isinstance(stop, threading.Event) or stop.is_set():
            return "", False
        worker = state.get("invoke_thread")
        active = not isinstance(worker, threading.Thread) or worker.is_alive() or worker.ident is None
        return (_text(state.get("phase")) or "durable_publication", active)


def describe_final_report_activity(
    service: ComprehensiveRunService,
    record: Mapping[str, Any],
    *,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Project durable final-report liveness without changing canonical revision.

    The canonical run intentionally remains stable while a report is queued or
    rendering. This projection reads the separate lease heartbeat and bounded local
    ownership so browsers and production proofs can distinguish a live publication
    from a genuinely abandoned one. It never writes the run, report, score, candidate
    state, approval state, or delivery state.
    """

    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return {}
    marker = stage_results.get(FINAL_REPORT_STAGE_ID)
    if not isinstance(marker, Mapping):
        return {}
    if _text(marker.get("status")).casefold() != "running":
        return {}
    if _text(marker.get("reason")) != _RUNNING_REASON:
        return {}
    execution = marker.get("stage_execution")
    if not isinstance(execution, Mapping):
        return {}
    lease_id = _text(execution.get("lease_id"))
    if not lease_id:
        return {}

    store = getattr(service, "_store", None)
    load_job = getattr(store, "load_final_report_job", None)
    job = load_job(lease_id) if callable(load_job) else None
    job = job if isinstance(job, Mapping) else {}
    job_status = _text(job.get("status")).casefold() or "missing"
    heartbeat_epoch = _number(job.get("heartbeat_epoch"))
    current_epoch = time.time() if now_epoch is None else float(now_epoch)
    heartbeat_age = (
        max(0.0, current_epoch - heartbeat_epoch)
        if heartbeat_epoch is not None and heartbeat_epoch > 0.0
        else None
    )
    orphan_after = _number(execution.get("orphan_after_seconds")) or 30.0
    heartbeat_fresh = bool(
        job_status == "running"
        and heartbeat_age is not None
        and heartbeat_age < orphan_after
    )
    local_phase, local_worker_active = _local_phase(lease_id)
    phase = local_phase or ("durable_running" if heartbeat_fresh else job_status)
    heartbeat_token = ""
    if heartbeat_epoch is not None:
        heartbeat_token = hashlib.sha256(
            f"{lease_id}|{job_status}|{heartbeat_epoch:.6f}|{phase}".encode("utf-8")
        ).hexdigest()[:24]

    return {
        "artifact_schema": VERSION,
        "stage_id": FINAL_REPORT_STAGE_ID,
        "status": "active" if local_worker_active or heartbeat_fresh else job_status,
        "phase": phase,
        "lease_fingerprint": hashlib.sha256(lease_id.encode("utf-8")).hexdigest()[:16],
        "durable_job_status": job_status,
        "heartbeat_epoch": heartbeat_epoch,
        "heartbeat_updated_at": _text(job.get("updated_at")),
        "heartbeat_age_seconds": round(heartbeat_age, 3) if heartbeat_age is not None else None,
        "heartbeat_fresh": heartbeat_fresh,
        "activity_token": heartbeat_token,
        "local_worker_active": local_worker_active,
        "orphan_after_seconds": orphan_after,
        "provider_lifetime_owner": _text(execution.get("provider_lifetime_owner")),
        "nested_timeout_thread": bool(execution.get("nested_timeout_thread")),
        "canonical_run_revision": record.get("revision"),
        "canonical_run_revision_mutated": False,
        "report_artifacts_available": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


class ObservableComprehensiveApiController(ComprehensiveApiController):
    """Attach bounded durable activity to active Comprehensive responses."""

    def _response_with_activity(
        self,
        record: dict[str, Any],
        *,
        operation: str,
    ) -> dict[str, Any]:
        response = self._response(record, operation=operation)
        activity = describe_final_report_activity(self._service, record)
        if activity:
            response["active_stage_execution"] = activity
            projection = response.get("response_projection")
            if isinstance(projection, dict):
                projection["active_stage_execution_attached"] = True
                projection["canonical_run_revision_mutated_for_activity"] = False
        return response

    def status(self, run_id: str) -> dict[str, Any]:
        normalized = self._required(run_id, "run_id")
        record = self._service.load(normalized)
        return self._response_with_activity(record, operation="status")

    def continue_run(
        self,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = self._object(payload or {})
        bounded = body.get("max_stages")
        max_stages = None if bounded is None else int(bounded)
        if max_stages is not None and max_stages < 0:
            raise ValueError("max_stages_must_be_non_negative")
        record = self._service.resume(
            self._required(run_id, "run_id"),
            max_stages=max_stages,
        )
        return self._response_with_activity(record, operation="continued")


__all__ = [
    "ObservableComprehensiveApiController",
    "VERSION",
    "describe_final_report_activity",
]
