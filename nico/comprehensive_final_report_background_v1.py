from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_final_report_execution_boundary_v4 import (
    FINAL_REPORT_STAGE_ID,
    execute_final_report_stage,
)
from nico.comprehensive_run_record import apply_comprehensive_stage_result
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunStore

VERSION = "nico.comprehensive_final_report_background.v1"
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_ORPHAN_SECONDS = 30.0
_RUNNING_REASON = "final_report_background_publication_in_progress"
_LOCAL_TASKS: dict[str, dict[str, Any]] = {}
_LOCAL_TASKS_LOCK = threading.RLock()


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _heartbeat_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_FINAL_REPORT_HEARTBEAT_SECONDS",
        DEFAULT_HEARTBEAT_SECONDS,
        1.0,
        30.0,
    )


def _orphan_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_FINAL_REPORT_ORPHAN_SECONDS",
        DEFAULT_ORPHAN_SECONDS,
        10.0,
        300.0,
    )


def _marker(record: Mapping[str, Any]) -> Mapping[str, Any]:
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return {}
    value = stage_results.get(FINAL_REPORT_STAGE_ID)
    if not isinstance(value, Mapping):
        return {}
    if _text(value.get("status")).casefold() != "running":
        return {}
    if _text(value.get("reason")) != _RUNNING_REASON:
        return {}
    return value


def _marker_lease(record: Mapping[str, Any]) -> str:
    value = _marker(record)
    execution = value.get("stage_execution")
    if not isinstance(execution, Mapping):
        return ""
    return _text(execution.get("lease_id"))


def _local_task_active(lease_id: str) -> bool:
    """Return whether this process still owns a live publication task.

    Durable heartbeat timestamps can become temporarily stale while report rendering
    is CPU-heavy. A stale heartbeat must not cause this same process to launch a
    second final-report worker while the original worker is still alive. After a
    process restart the in-memory task map is empty, so genuinely orphaned durable
    leases remain reclaimable.
    """

    normalized = _text(lease_id)
    if not normalized:
        return False
    with _LOCAL_TASKS_LOCK:
        state = _LOCAL_TASKS.get(normalized)
        if not isinstance(state, Mapping):
            return False
        stop = state.get("stop")
        if not isinstance(stop, threading.Event) or stop.is_set():
            return False
        invoke_thread = state.get("invoke_thread")
        if not isinstance(invoke_thread, threading.Thread):
            return True
        return invoke_thread.is_alive() or invoke_thread.ident is None


def _job_fresh(job: Mapping[str, Any] | None, *, now_epoch: float) -> bool:
    if not isinstance(job, Mapping):
        return False
    if _text(job.get("status")).casefold() != "running":
        return False
    try:
        heartbeat = float(job.get("heartbeat_epoch") or 0.0)
    except (TypeError, ValueError):
        return False
    return heartbeat > 0.0 and max(0.0, now_epoch - heartbeat) < _orphan_seconds()


def _running_result(context: Mapping[str, Any], *, lease_id: str, started_epoch: float) -> dict[str, Any]:
    return {
        "status": "running",
        "reason": _RUNNING_REASON,
        "summary": (
            "Final report generation is continuing behind the durable exact-run "
            "boundary without holding the browser continuation request open."
        ),
        "retryable": False,
        "cancelable": True,
        "artifacts_available": False,
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": {
            "artifact_schema": VERSION,
            "mode": "durable_final_report_publication",
            "lease_id": lease_id,
            "started_epoch": started_epoch,
            "heartbeat_interval_seconds": _heartbeat_seconds(),
            "orphan_after_seconds": _orphan_seconds(),
            "detached_background_execution": True,
            "canonical_run_write_pending": True,
            "canonical_run_written_by_final_report_coordinator": True,
            "canonical_run_written_only_by_request_thread": False,
            "full_result_job_serialization": False,
            "exact_run_recovery_supported": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


def _with_publication_metadata(result: Mapping[str, Any], *, lease_id: str) -> dict[str, Any]:
    output = dict(result)
    prior = output.get("stage_execution")
    execution = dict(prior) if isinstance(prior, Mapping) else {}
    execution.update(
        {
            "publication_coordinator_schema": VERSION,
            "publication_lease_id": lease_id,
            "detached_background_execution": True,
            "canonical_run_write_required": True,
            "canonical_run_written_by_final_report_coordinator": True,
            "canonical_run_written_only_by_request_thread": False,
            "full_result_job_serialization": False,
        }
    )
    output["stage_execution"] = execution
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


class FinalReportPublicationCoordinator:
    """Run final report generation outside the HTTP continuation lifetime.

    The canonical run receives one small running marker. A separate durable lease row
    receives only heartbeat metadata. The generated PDF/HTML/Markdown/JSON package is
    never serialized through the lease table: the worker validates it with the
    existing atomic final-report boundary and commits it directly to the exact run via
    the optimistic-concurrency store. A stale lease can be replaced after process
    loss, while the lease id in the canonical marker prevents a late superseded worker
    from overwriting the replacement.
    """

    def __init__(self, store: ComprehensiveRunStore) -> None:
        self._store = store

    def advance(
        self,
        record: dict[str, Any],
        executor,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = _text(context.get("run_id"))
        if not run_id:
            raise ValueError("final_report_run_id_required")

        lease_id = _marker_lease(record)
        if lease_id:
            if _local_task_active(lease_id):
                return record
            job = self._store.load_final_report_job(lease_id)
            if _job_fresh(job, now_epoch=time.time()):
                return record
            latest = self._store.load(run_id)
            if int(latest.get("revision") or 0) != int(record.get("revision") or 0):
                return latest
            record = latest

        return self._claim_and_launch(record, executor, context)

    def _claim_and_launch(
        self,
        record: dict[str, Any],
        executor,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = _text(context.get("run_id"))
        lease_id = f"frpub_{uuid.uuid4().hex}"
        started_epoch = time.time()
        started_at = _now_iso()

        self._store.create_final_report_job(
            lease_id=lease_id,
            run_id=run_id,
            started_epoch=started_epoch,
            heartbeat_epoch=started_epoch,
            updated_at=started_at,
        )
        marker = _running_result(
            context,
            lease_id=lease_id,
            started_epoch=started_epoch,
        )
        expected_revision = int(record["revision"])
        updated = apply_comprehensive_stage_result(
            record,
            stage_id=FINAL_REPORT_STAGE_ID,
            result=marker,
        )
        try:
            claimed = self._store.save(updated, expected_revision=expected_revision)
        except ComprehensiveRunConflict:
            self._safe_job_update(lease_id, status="superseded")
            return self._store.load(run_id)

        self._start_worker(
            lease_id=lease_id,
            executor=executor,
            context=dict(context),
        )
        return claimed

    def _start_worker(
        self,
        *,
        lease_id: str,
        executor,
        context: Mapping[str, Any],
    ) -> None:
        stop = threading.Event()

        def heartbeat() -> None:
            interval = _heartbeat_seconds()
            while not stop.wait(interval):
                self._safe_job_update(lease_id, status="running")

        def invoke() -> None:
            outcome = "failed"
            try:
                result = execute_final_report_stage(executor, context)
                outcome = self._publish_result(
                    lease_id=lease_id,
                    run_id=_text(context.get("run_id")),
                    result=_with_publication_metadata(result, lease_id=lease_id),
                )
            except BaseException:
                # Keep the canonical run on its running marker. A failed or crashed
                # worker is retried by the next continuation using a replacement
                # durable lease; it is never converted into a passing result.
                outcome = "failed"
            finally:
                stop.set()
                self._safe_job_update(lease_id, status=outcome)
                with _LOCAL_TASKS_LOCK:
                    _LOCAL_TASKS.pop(lease_id, None)

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"nico-final-report-heartbeat-{lease_id[-8:]}",
            daemon=True,
        )
        invoke_thread = threading.Thread(
            target=invoke,
            name=f"nico-final-report-publication-{lease_id[-8:]}",
            daemon=True,
        )
        state = {
            "stop": stop,
            "heartbeat_thread": heartbeat_thread,
            "invoke_thread": invoke_thread,
        }
        with _LOCAL_TASKS_LOCK:
            _LOCAL_TASKS[lease_id] = state

        try:
            heartbeat_thread.start()
            invoke_thread.start()
        except BaseException:
            stop.set()
            self._safe_job_update(lease_id, status="failed")
            with _LOCAL_TASKS_LOCK:
                if _LOCAL_TASKS.get(lease_id) is state:
                    _LOCAL_TASKS.pop(lease_id, None)
            raise

    def _publish_result(
        self,
        *,
        lease_id: str,
        run_id: str,
        result: Mapping[str, Any],
    ) -> str:
        for _ in range(4):
            current = self._store.load(run_id)
            if FINAL_REPORT_STAGE_ID in set(current.get("completed_stages") or []):
                return "complete"
            if _marker_lease(current) != lease_id:
                return "superseded"
            expected_revision = int(current["revision"])
            updated = apply_comprehensive_stage_result(
                current,
                stage_id=FINAL_REPORT_STAGE_ID,
                result=dict(result),
            )
            try:
                self._store.save(updated, expected_revision=expected_revision)
            except ComprehensiveRunConflict:
                continue
            return (
                "complete"
                if _text(result.get("status")).casefold() in {"complete", "completed", "success", "succeeded", "passed"}
                else "blocked"
            )
        return "failed"

    def _safe_job_update(self, lease_id: str, *, status: str) -> None:
        try:
            self._store.update_final_report_job(
                lease_id,
                status=status,
                heartbeat_epoch=time.time(),
                updated_at=_now_iso(),
            )
        except Exception:
            # Lease telemetry is recovery metadata. Canonical run truth remains in the
            # optimistic-concurrency run store and must never be weakened if a
            # heartbeat write is temporarily unavailable.
            pass


def reset_final_report_publication_tasks_for_tests() -> None:
    with _LOCAL_TASKS_LOCK:
        for state in _LOCAL_TASKS.values():
            stop = state.get("stop") if isinstance(state, Mapping) else None
            if isinstance(stop, threading.Event):
                stop.set()
        _LOCAL_TASKS.clear()


__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_ORPHAN_SECONDS",
    "FinalReportPublicationCoordinator",
    "VERSION",
    "reset_final_report_publication_tasks_for_tests",
]
