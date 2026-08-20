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

VERSION = "nico.comprehensive_final_report_background.v5"
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_ORPHAN_SECONDS = 30.0
DEFAULT_MAX_PUBLICATION_SECONDS = 900.0
DEFAULT_MAX_QUEUE_SECONDS = 7200.0
_RUNNING_REASON = "final_report_background_publication_in_progress"
_ACTIVE_JOB_STATUSES = {"queued", "rendering", "running"}
_TERMINAL_JOB_STATUSES = {
    "complete",
    "blocked",
    "failed",
    "cancelled",
    "superseded",
    "expired",
}
_LOCAL_TASKS: dict[str, dict[str, Any]] = {}
_LOCAL_TASKS_LOCK = threading.RLock()
_PUBLICATION_SLOT = threading.BoundedSemaphore(value=1)


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


def _max_publication_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_FINAL_REPORT_MAX_PUBLICATION_SECONDS",
        DEFAULT_MAX_PUBLICATION_SECONDS,
        120.0,
        7200.0,
    )


def _max_queue_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_FINAL_REPORT_MAX_QUEUE_SECONDS",
        DEFAULT_MAX_QUEUE_SECONDS,
        120.0,
        14400.0,
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
    """Return whether this process still owns a live publication task."""

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
    if _text(job.get("status")).casefold() not in _ACTIVE_JOB_STATUSES:
        return False
    try:
        heartbeat = float(job.get("heartbeat_epoch") or 0.0)
    except (TypeError, ValueError):
        return False
    return heartbeat > 0.0 and max(0.0, now_epoch - heartbeat) < _orphan_seconds()


def _job_deadline_state(
    job: Mapping[str, Any] | None,
    *,
    now_epoch: float,
) -> dict[str, Any]:
    if not isinstance(job, Mapping):
        return {
            "active": False,
            "overdue": False,
            "phase": "missing",
            "started_epoch": 0.0,
            "elapsed_seconds": 0.0,
            "deadline_seconds": 0.0,
        }

    status = _text(job.get("status")).casefold()
    if status not in _ACTIVE_JOB_STATUSES:
        return {
            "active": False,
            "overdue": False,
            "phase": status or "unknown",
            "started_epoch": 0.0,
            "elapsed_seconds": 0.0,
            "deadline_seconds": 0.0,
        }

    try:
        started_epoch = float(job.get("started_epoch") or 0.0)
    except (TypeError, ValueError):
        started_epoch = 0.0

    phase = "queued" if status == "queued" else "rendering"
    deadline_seconds = _max_queue_seconds() if phase == "queued" else _max_publication_seconds()
    elapsed_seconds = max(0.0, now_epoch - started_epoch) if started_epoch > 0.0 else 0.0
    return {
        "active": True,
        "overdue": started_epoch > 0.0 and elapsed_seconds >= deadline_seconds,
        "phase": phase,
        "lease_status": status,
        "started_epoch": started_epoch,
        "elapsed_seconds": elapsed_seconds,
        "deadline_seconds": deadline_seconds,
    }


def _running_result(
    context: Mapping[str, Any],
    *,
    lease_id: str,
    started_epoch: float,
) -> dict[str, Any]:
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
            "publication_phase_at_claim": "queued",
            "heartbeat_interval_seconds": _heartbeat_seconds(),
            "orphan_after_seconds": _orphan_seconds(),
            "max_queue_seconds": _max_queue_seconds(),
            "max_publication_seconds": _max_publication_seconds(),
            "publication_deadline_scope": "renderer_execution_only",
            "deadline_enforcement_mode": "autonomous_watchdog_and_advance",
            "expired_worker_capacity_reclaim": True,
            "late_result_fencing": "canonical_publication_lease",
            "detached_background_execution": True,
            "canonical_run_write_pending": True,
            "canonical_run_written_by_final_report_coordinator": True,
            "canonical_run_written_only_by_request_thread": False,
            "full_result_job_serialization": False,
            "exact_run_recovery_supported": True,
            "provider_lifetime_owner": "durable_final_report_coordinator",
            "nested_timeout_thread": False,
            "process_local_render_capacity": 1,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


def _overdue_result(
    context: Mapping[str, Any],
    *,
    lease_id: str,
    deadline: Mapping[str, Any],
) -> dict[str, Any]:
    phase = _text(deadline.get("phase")) or "rendering"
    if phase == "queued":
        message = (
            "Final report publication could not acquire bounded renderer capacity before "
            "the durable queue deadline. The exact run can retry final-report publication "
            "without rerunning completed scanners."
        )
    else:
        message = (
            "Final report rendering exceeded the durable renderer-execution deadline. "
            "The exact run can retry final-report publication without rerunning completed scanners."
        )
    return {
        "status": "blocked",
        "reason": "final_report_publication_deadline_exceeded",
        "error_code": "final_report_publication_deadline_exceeded",
        "error_message": message,
        "technical_reason": (
            "final_report_publication_deadline_exceeded:"
            f"stage={FINAL_REPORT_STAGE_ID}:phase={phase}"
        ),
        "retryable": True,
        "cancelable": True,
        "artifacts_available": False,
        "recovery_supported": True,
        "recovery_scope": "final_report_only",
        "run_id": _text(context.get("run_id")),
        "repository": _text(context.get("repository")),
        "commit_sha": _text(context.get("commit_sha")),
        "evidence_ledger_id": _text(context.get("evidence_ledger_id")),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": {
            "artifact_schema": VERSION,
            "mode": "durable_final_report_publication",
            "publication_lease_id": lease_id,
            "deadline_phase": phase,
            "started_epoch": float(deadline.get("started_epoch") or 0.0),
            "elapsed_seconds": float(deadline.get("elapsed_seconds") or 0.0),
            "deadline_seconds": float(deadline.get("deadline_seconds") or 0.0),
            "max_queue_seconds": _max_queue_seconds(),
            "max_publication_seconds": _max_publication_seconds(),
            "publication_deadline_scope": "renderer_execution_only",
            "deadline_enforced_by": "durable_final_report_coordinator_watchdog_or_advance",
            "deadline_enforcement_mode": "autonomous_watchdog_and_advance",
            "expired_worker_capacity_reclaim": True,
            "late_result_fencing": "canonical_publication_lease",
            "provider_lifetime_owner": "durable_final_report_coordinator",
            "nested_timeout_thread": False,
            "detached_background_execution": True,
            "canonical_run_write_required": True,
            "recovery_supported": True,
            "recovery_scope": "final_report_only",
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


def _with_publication_metadata(
    result: Mapping[str, Any],
    *,
    lease_id: str,
    render_started_epoch: float,
) -> dict[str, Any]:
    output = dict(result)
    prior = output.get("stage_execution")
    execution = dict(prior) if isinstance(prior, Mapping) else {}
    execution.update(
        {
            "publication_coordinator_schema": VERSION,
            "publication_lease_id": lease_id,
            "publication_phase": "published",
            "render_started_epoch": render_started_epoch,
            "detached_background_execution": True,
            "canonical_run_write_required": True,
            "canonical_run_written_by_final_report_coordinator": True,
            "canonical_run_written_only_by_request_thread": False,
            "full_result_job_serialization": False,
            "provider_lifetime_owner": "durable_final_report_coordinator",
            "nested_timeout_thread": False,
            "process_local_render_capacity": 1,
            "max_queue_seconds": _max_queue_seconds(),
            "max_publication_seconds": _max_publication_seconds(),
            "publication_deadline_scope": "renderer_execution_only",
            "deadline_enforcement_mode": "autonomous_watchdog_and_advance",
            "expired_worker_capacity_reclaim": True,
            "late_result_fencing": "canonical_publication_lease",
        }
    )
    output["stage_execution"] = execution
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def _acquire_publication_slot(stop: threading.Event) -> bool:
    while not stop.is_set():
        if _PUBLICATION_SLOT.acquire(timeout=0.25):
            return True
    return False


def _release_local_task_capacity(state: dict[str, Any]) -> None:
    state_lock = state.get("state_lock")
    if state_lock is None:
        return
    should_release = False
    with state_lock:
        if bool(state.get("slot_acquired")) and not bool(state.get("slot_released")):
            state["slot_released"] = True
            should_release = True
    if should_release:
        _PUBLICATION_SLOT.release()


class FinalReportPublicationCoordinator:
    """Run final report generation outside the HTTP continuation lifetime.

    The canonical run receives one small running marker. A separate durable lease row
    receives only heartbeat metadata. The generated PDF/HTML/Markdown/JSON package is
    never serialized through the lease table. The durable worker owns provider
    lifetime directly and process-local rendering is serialized so concurrent runs do
    not starve status and readiness transport in the single production process.

    Queue wait and renderer execution are bounded independently. Waiting for the single
    renderer does not consume the renderer-execution deadline. Once capacity is acquired,
    the durable lease atomically transitions from ``queued`` to ``rendering`` and resets
    the deadline clock. The deadline is enforced both when continuation advances and by
    the worker's own watchdog, so status-only polling cannot leave the canonical run at
    the final-report stage forever. A renderer that exceeds its hard lease is fenced from
    late publication and its logical capacity is reclaimed for the bounded exact-run
    recovery attempt. Scoring, artifact validation, human review, and client-delivery
    gates remain unchanged.
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
            latest = self._store.load(run_id)
            if int(latest.get("revision") or 0) != int(record.get("revision") or 0):
                return latest
            if _marker_lease(latest) != lease_id:
                return latest
            record = latest

            job = self._store.load_final_report_job(lease_id)
            now_epoch = time.time()
            deadline = _job_deadline_state(job, now_epoch=now_epoch)
            if bool(deadline.get("overdue")):
                return self._expire_publication(
                    record,
                    lease_id=lease_id,
                    context=context,
                )
            if _local_task_active(lease_id):
                return record
            if _job_fresh(job, now_epoch=now_epoch):
                return record
            latest = self._store.load(run_id)
            if int(latest.get("revision") or 0) != int(record.get("revision") or 0):
                return latest
            record = latest

        return self._claim_and_launch(record, executor, context)

    def _expire_publication(
        self,
        record: dict[str, Any],
        *,
        lease_id: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = _text(context.get("run_id"))
        latest = self._store.load(run_id)
        if int(latest.get("revision") or 0) != int(record.get("revision") or 0):
            return latest
        if _marker_lease(latest) != lease_id:
            return latest

        job = self._store.load_final_report_job(lease_id)
        deadline = _job_deadline_state(job, now_epoch=time.time())
        if not bool(deadline.get("overdue")):
            return latest

        result = _overdue_result(
            context,
            lease_id=lease_id,
            deadline=deadline,
        )
        expected_revision = int(latest["revision"])
        updated = apply_comprehensive_stage_result(
            latest,
            stage_id=FINAL_REPORT_STAGE_ID,
            result=result,
        )
        try:
            persisted = self._store.save(updated, expected_revision=expected_revision)
        except ComprehensiveRunConflict:
            return self._store.load(run_id)
        self._stop_local_task(lease_id)
        self._safe_job_update(lease_id, status="expired")
        return persisted

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
            status="queued",
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
        state_lock = threading.RLock()
        state: dict[str, Any] = {
            "stop": stop,
            "phase": "queued",
            "state_lock": state_lock,
            "slot_acquired": False,
            "slot_released": False,
        }

        def release_slot_once() -> None:
            _release_local_task_capacity(state)

        def heartbeat() -> None:
            interval = _heartbeat_seconds()
            while not stop.wait(interval):
                with state_lock:
                    phase = _text(state.get("phase")) or "queued"
                    self._safe_job_update(lease_id, status=phase)

        def watchdog() -> None:
            interval = max(0.05, min(_heartbeat_seconds(), 5.0))
            run_id = _text(context.get("run_id"))
            while not stop.wait(interval):
                try:
                    job = self._store.load_final_report_job(lease_id)
                    deadline = _job_deadline_state(job, now_epoch=time.time())
                except Exception:
                    continue
                if not bool(deadline.get("overdue")):
                    continue

                try:
                    current = self._store.load(run_id)
                    with state_lock:
                        expired = self._expire_publication(
                            current,
                            lease_id=lease_id,
                            context=context,
                        )
                        if _marker_lease(expired) == lease_id:
                            continue
                        release_slot_once()
                except Exception:
                    continue
                stop.set()
                return

        def invoke() -> None:
            outcome = "failed"
            slot_acquired = False
            render_started_epoch = 0.0
            try:
                slot_acquired = _acquire_publication_slot(stop)
                if not slot_acquired:
                    outcome = "cancelled"
                    return
                with state_lock:
                    state["slot_acquired"] = True

                render_started_epoch = time.time()
                with state_lock:
                    transitioned = self._transition_job_to_rendering(
                        lease_id,
                        render_started_epoch=render_started_epoch,
                    )
                    if transitioned:
                        state["phase"] = "rendering"
                if not transitioned:
                    outcome = "superseded"
                    return

                result = execute_final_report_stage(
                    executor,
                    context,
                    durable_coordinator_owns_lifetime=True,
                )
                outcome = self._publish_result(
                    lease_id=lease_id,
                    run_id=_text(context.get("run_id")),
                    result=_with_publication_metadata(
                        result,
                        lease_id=lease_id,
                        render_started_epoch=render_started_epoch,
                    ),
                )
            except BaseException:
                outcome = "failed"
            finally:
                if slot_acquired:
                    release_slot_once()
                stop.set()
                self._safe_job_update(lease_id, status=outcome)
                with _LOCAL_TASKS_LOCK:
                    if _LOCAL_TASKS.get(lease_id) is state:
                        _LOCAL_TASKS.pop(lease_id, None)

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"nico-final-report-heartbeat-{lease_id[-8:]}",
            daemon=True,
        )
        watchdog_thread = threading.Thread(
            target=watchdog,
            name=f"nico-final-report-watchdog-{lease_id[-8:]}",
            daemon=True,
        )
        invoke_thread = threading.Thread(
            target=invoke,
            name=f"nico-final-report-publication-{lease_id[-8:]}",
            daemon=True,
        )
        state.update(
            {
                "heartbeat_thread": heartbeat_thread,
                "watchdog_thread": watchdog_thread,
                "invoke_thread": invoke_thread,
            }
        )
        with _LOCAL_TASKS_LOCK:
            _LOCAL_TASKS[lease_id] = state

        try:
            heartbeat_thread.start()
            watchdog_thread.start()
            invoke_thread.start()
        except BaseException:
            stop.set()
            release_slot_once()
            self._safe_job_update(lease_id, status="failed")
            with _LOCAL_TASKS_LOCK:
                if _LOCAL_TASKS.get(lease_id) is state:
                    _LOCAL_TASKS.pop(lease_id, None)
            raise

    def _transition_job_to_rendering(
        self,
        lease_id: str,
        *,
        render_started_epoch: float,
    ) -> bool:
        try:
            return self._store.transition_final_report_job_to_rendering(
                lease_id,
                started_epoch=render_started_epoch,
                heartbeat_epoch=render_started_epoch,
                updated_at=_now_iso(),
            )
        except Exception:
            return False

    def _stop_local_task(self, lease_id: str) -> None:
        with _LOCAL_TASKS_LOCK:
            state = _LOCAL_TASKS.get(lease_id)
        if not isinstance(state, dict):
            return
        stop = state.get("stop")
        if isinstance(stop, threading.Event):
            stop.set()
        _release_local_task_capacity(state)

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
                if _text(result.get("status")).casefold()
                in {"complete", "completed", "success", "succeeded", "passed"}
                else "blocked"
            )
        return "failed"

    def _safe_job_update(
        self,
        lease_id: str,
        *,
        status: str,
        started_epoch: float | None = None,
    ) -> None:
        try:
            target = _text(status).casefold()
            current = self._store.load_final_report_job(lease_id)
            current_status = _text(
                current.get("status") if isinstance(current, Mapping) else ""
            ).casefold()
            if current_status in _TERMINAL_JOB_STATUSES and current_status != target:
                return
            self._store.update_final_report_job(
                lease_id,
                status=target,
                started_epoch=started_epoch,
                heartbeat_epoch=time.time(),
                updated_at=_now_iso(),
            )
        except Exception:
            pass


def reset_final_report_publication_tasks_for_tests() -> None:
    with _LOCAL_TASKS_LOCK:
        states = list(_LOCAL_TASKS.values())
        _LOCAL_TASKS.clear()
    for state in states:
        stop = state.get("stop") if isinstance(state, Mapping) else None
        if isinstance(stop, threading.Event):
            stop.set()
        if isinstance(state, dict):
            _release_local_task_capacity(state)


__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_MAX_PUBLICATION_SECONDS",
    "DEFAULT_MAX_QUEUE_SECONDS",
    "DEFAULT_ORPHAN_SECONDS",
    "FinalReportPublicationCoordinator",
    "VERSION",
    "reset_final_report_publication_tasks_for_tests",
]
