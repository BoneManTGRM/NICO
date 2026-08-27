from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Mapping
from typing import Any, Callable

from fastapi import FastAPI

from nico import comprehensive_final_report_background_v1 as background
from nico import comprehensive_final_report_execution_boundary_v4 as boundary
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_final_report_process_worker_v1 import (
    IsolatedFinalReportCancelled,
    run_isolated_final_report,
    terminate_process,
)

VERSION = "nico.comprehensive_final_report_process_isolation.v3"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
_INSTALL_STATE = "nico_final_report_process_isolation_v1"
_PATCH_MARKER = "__nico_comprehensive_final_report_process_isolation_v1__"
_DEFAULT_TERMINATION_WAIT_SECONDS = 12.0
_LOCAL_DEADLINE_PERSIST_RETRIES = 12

_ORIGINAL_START_WORKER: Callable[..., Any] | None = None
_ORIGINAL_STOP_LOCAL_TASK: Callable[..., Any] | None = None
_ORIGINAL_SERVICE_LOAD: Callable[..., Any] | None = None
_ORIGINAL_CONTROLLER_RESPONSE: Callable[..., Any] | None = None


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _enabled() -> bool:
    return os.getenv("NICO_FINAL_REPORT_PROCESS_ISOLATION", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _production_final_report_executor(executor: Any) -> bool:
    """Identify the production stage adapter without changing generic test executors."""

    keyword_defaults = getattr(executor, "__kwdefaults__", None)
    if not isinstance(keyword_defaults, dict):
        return False
    if _text(keyword_defaults.get("_capability")) != "final_report_generation":
        return False
    inner = keyword_defaults.get("_executor")
    return (
        callable(inner)
        and getattr(inner, "__module__", "")
        == "nico.comprehensive_production_capabilities"
    )


def _termination_wait_seconds() -> float:
    try:
        value = float(
            os.getenv(
                "NICO_FINAL_REPORT_PROCESS_TERMINATION_WAIT_SECONDS",
                str(_DEFAULT_TERMINATION_WAIT_SECONDS),
            )
        )
    except (TypeError, ValueError):
        value = _DEFAULT_TERMINATION_WAIT_SECONDS
    return max(2.0, min(30.0, value))


def _terminate_state_process(state: Mapping[str, Any]) -> bool:
    process = state.get("worker_process")
    if not isinstance(process, subprocess.Popen):
        return True
    return terminate_process(process, grace_seconds=3.0)


def _wait_for_invoke_shutdown(state: Mapping[str, Any]) -> bool:
    invoke_thread = state.get("invoke_thread")
    if not isinstance(invoke_thread, threading.Thread):
        return _terminate_state_process(state)
    if invoke_thread is threading.current_thread():
        return False
    invoke_thread.join(timeout=_termination_wait_seconds())
    if invoke_thread.is_alive():
        _terminate_state_process(state)
        invoke_thread.join(timeout=5.0)
    return not invoke_thread.is_alive() and _terminate_state_process(state)


def _with_process_execution(
    result: Mapping[str, Any],
    process_execution: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(result)
    prior = output.get("stage_execution")
    execution = dict(prior) if isinstance(prior, Mapping) else {}
    execution.update(dict(process_execution))
    execution.update(
        {
            "process_isolation_schema": VERSION,
            "renderer_lifetime_owner": "killable_isolated_subprocess",
            "logical_capacity_released_only_after_worker_exit": True,
            "recovery_waits_for_worker_termination": True,
            "process_local_monotonic_deadline": True,
            "deadline_independent_of_durable_lease_reads": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["stage_execution"] = execution
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def _process_worker_failure(
    context: Mapping[str, Any],
    exc: BaseException,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    process = state.get("worker_process")
    worker_pid = int(getattr(process, "pid", 0) or state.get("worker_pid") or 0)
    try:
        worker_exit_code = int(state.get("worker_exit_code"))
    except (TypeError, ValueError):
        worker_exit_code = 0
    worker_exit_signal = _text(state.get("worker_exit_signal"))[:80]
    worker_error_type = _text(state.get("worker_error_type")) or type(exc).__name__
    worker_error = _text(state.get("worker_error")) or _text(exc)
    worker_error = worker_error[:1200]
    worker_bootstrap = _text(state.get("worker_bootstrap"))[:240]
    failure_class = (
        "process_signal"
        if worker_exit_code < 0 or bool(worker_exit_signal)
        else "child_exception"
        if worker_error_type not in {"WorkerProcessExit", "WorkerPayloadError"}
        else "worker_process_exit"
    )
    process_execution = {
        "process_isolation_schema": VERSION,
        "worker_model": "isolated_subprocess",
        "killable_worker": True,
        "worker_pid": worker_pid,
        "worker_exit_code": worker_exit_code,
        "worker_exit_signal": worker_exit_signal,
        "worker_error_type": worker_error_type,
        "worker_error": worker_error,
        "worker_failure_class": failure_class,
        "worker_bootstrap": worker_bootstrap,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output = boundary._blocked(
        context,
        reason="detached_stage_execution_failed",
        message=(
            "The isolated final-report worker exited before publishing a validated "
            "artifact package. The exact run can retry final-report generation without "
            "rerunning completed scanners."
        ),
        execution=process_execution,
        recovery_supported=True,
        recovery_scope="final_report_only",
    )
    # The public stage projection intentionally omits nested stage_execution objects.
    # Retain a bounded primitive diagnostic summary at the stage top level so a future
    # renderer failure is actionable instead of collapsing back to an opaque HTTP 200.
    output.update(
        {
            "worker_model": "isolated_subprocess",
            "worker_exit_code": worker_exit_code,
            "worker_exit_signal": worker_exit_signal,
            "worker_error_type": worker_error_type[:240],
            "worker_error": worker_error[:1200],
            "worker_failure_class": failure_class,
            "worker_bootstrap": worker_bootstrap,
            "worker_diagnostics_bounded": True,
            "worker_traceback_exposed": False,
        }
    )
    return output


def _local_deadline_blocked_result(
    context: Mapping[str, Any],
    *,
    lease_id: str,
    state: Mapping[str, Any],
    render_started_epoch: float,
) -> dict[str, Any]:
    try:
        deadline_seconds = float(
            state.get("local_render_deadline_seconds")
            or background._max_publication_seconds()
        )
    except (TypeError, ValueError):
        deadline_seconds = float(background._max_publication_seconds())
    try:
        elapsed_seconds = float(state.get("local_render_elapsed_seconds") or 0.0)
    except (TypeError, ValueError):
        elapsed_seconds = 0.0

    result = background._overdue_result(
        context,
        lease_id=lease_id,
        deadline={
            "phase": "rendering",
            "started_epoch": float(render_started_epoch or time.time()),
            "elapsed_seconds": max(elapsed_seconds, deadline_seconds),
            "deadline_seconds": deadline_seconds,
        },
    )
    execution = result.get("stage_execution")
    execution = dict(execution) if isinstance(execution, Mapping) else {}
    execution.update(
        {
            "deadline_enforced_by": "isolated_process_local_monotonic_clock",
            "process_local_monotonic_deadline": True,
            "deadline_independent_of_durable_lease_reads": True,
            "worker_termination_confirmed": state.get("worker_terminated") is True,
            "physical_worker_exit_confirmed": (
                state.get("physical_worker_exit_confirmed") is True
            ),
            "local_render_elapsed_seconds": max(elapsed_seconds, deadline_seconds),
            "local_render_deadline_seconds": deadline_seconds,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["stage_execution"] = execution
    result.update(
        {
            "local_render_deadline_expired": True,
            "local_render_deadline_seconds": deadline_seconds,
            "local_render_elapsed_seconds": max(elapsed_seconds, deadline_seconds),
            "deadline_source": "process_local_monotonic_clock",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


def _publish_local_deadline_and_recover(
    self: background.FinalReportPublicationCoordinator,
    *,
    lease_id: str,
    executor,
    context: Mapping[str, Any],
    state: Mapping[str, Any],
    render_started_epoch: float,
) -> str:
    """Persist a local render timeout and consume the existing one-retry budget.

    The isolated worker enforces the physical deadline without consulting durable
    storage. Once the child is gone, this helper fences the exact canonical lease,
    persists the same fail-closed deadline result used by the durable watchdog, and
    reuses the existing final-artifact recovery path. Transient persistence failures
    are retried briefly instead of turning a hard renderer timeout into another stuck
    running marker.
    """

    run_id = _text(context.get("run_id"))
    blocked = _local_deadline_blocked_result(
        context,
        lease_id=lease_id,
        state=state,
        render_started_epoch=render_started_epoch,
    )
    for attempt in range(_LOCAL_DEADLINE_PERSIST_RETRIES):
        try:
            published = self._publish_result(
                lease_id=lease_id,
                run_id=run_id,
                result=blocked,
            )
            if published == "failed":
                raise RuntimeError("local_deadline_publication_conflict")
            if published in {"complete", "superseded"}:
                return published

            self._safe_job_update(lease_id, status="expired")
            current = self._store.load(run_id)
            self._recover_after_deadline(
                current,
                executor=executor,
                context=context,
            )
            return "expired"
        except Exception:
            if attempt + 1 >= _LOCAL_DEADLINE_PERSIST_RETRIES:
                break
            time.sleep(min(1.0, 0.1 * (attempt + 1)))
    return "expired"


def _isolated_stop_local_task(
    self: background.FinalReportPublicationCoordinator,
    lease_id: str,
) -> None:
    lease = _text(lease_id)
    if not lease:
        return
    with background._LOCAL_TASKS_LOCK:
        state = background._LOCAL_TASKS.get(lease)
    if not isinstance(state, dict) or state.get("worker_model") != "isolated_subprocess":
        if _ORIGINAL_STOP_LOCAL_TASK is not None:
            return _ORIGINAL_STOP_LOCAL_TASK(self, lease)
        return
    with state.get("state_lock") or threading.RLock():
        state["phase"] = "terminating"
        state["deadline_expired"] = True
    stop = state.get("stop")
    if isinstance(stop, threading.Event):
        stop.set()
    _terminate_state_process(state)
    _wait_for_invoke_shutdown(state)
    background._release_local_task_capacity(state)
    with background._LOCAL_TASKS_LOCK:
        if background._LOCAL_TASKS.get(lease) is state:
            background._LOCAL_TASKS.pop(lease, None)


def _isolated_start_worker(
    self: background.FinalReportPublicationCoordinator,
    *,
    lease_id: str,
    executor,
    context: Mapping[str, Any],
) -> None:
    if not _enabled() or not _production_final_report_executor(executor):
        assert _ORIGINAL_START_WORKER is not None
        return _ORIGINAL_START_WORKER(
            self,
            lease_id=lease_id,
            executor=executor,
            context=context,
        )

    stop = threading.Event()
    state_lock = threading.RLock()
    state: dict[str, Any] = {
        "stop": stop,
        "phase": "queued",
        "state_lock": state_lock,
        "slot_acquired": False,
        "slot_released": False,
        "worker_process": None,
        "worker_pid": 0,
        "worker_model": "isolated_subprocess",
    }

    def release_slot_once() -> None:
        background._release_local_task_capacity(state)

    def heartbeat() -> None:
        interval = background._heartbeat_seconds()
        while not stop.wait(interval):
            with state_lock:
                phase = _text(state.get("phase")) or "queued"
                durable_status = "rendering" if phase in {"rendering", "terminating"} else phase
                self._safe_job_update(lease_id, status=durable_status)

    def watchdog() -> None:
        interval = max(0.05, min(background._heartbeat_seconds(), 5.0))
        run_id = _text(context.get("run_id"))
        while not stop.wait(interval):
            try:
                job = self._store.load_final_report_job(lease_id)
                deadline = background._job_deadline_state(job, now_epoch=time.time())
            except Exception:
                continue
            if not bool(deadline.get("overdue")):
                continue

            try:
                current = self._store.load(run_id)
                expired = self._expire_publication(
                    current,
                    lease_id=lease_id,
                    context=context,
                )
                if background._marker_lease(expired) == lease_id:
                    continue
                with state_lock:
                    state["phase"] = "terminating"
                    state["deadline_expired"] = True
                stop.set()
                terminated = _wait_for_invoke_shutdown(state)
                state["worker_termination_confirmed"] = terminated
                if terminated:
                    self._recover_after_deadline(
                        expired,
                        executor=executor,
                        context=context,
                    )
            except Exception:
                pass
            return

    def invoke() -> None:
        outcome = "failed"
        slot_acquired = False
        render_started_epoch = 0.0
        try:
            slot_acquired = background._acquire_publication_slot(stop)
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
                    state["render_started_epoch"] = render_started_epoch
            if not transitioned:
                outcome = "superseded"
                return

            raw, process_execution = run_isolated_final_report(
                context,
                stop=stop,
                state=state,
                max_render_seconds=background._max_publication_seconds(),
            )
            if stop.is_set():
                outcome = "expired"
                return

            validation = boundary.execute_final_report_stage(
                lambda _context: raw,
                context,
                durable_coordinator_owns_lifetime=True,
            )
            validation = _with_process_execution(validation, process_execution)
            outcome = self._publish_result(
                lease_id=lease_id,
                run_id=_text(context.get("run_id")),
                result=background._with_publication_metadata(
                    validation,
                    lease_id=lease_id,
                    render_started_epoch=render_started_epoch,
                ),
            )
        except IsolatedFinalReportCancelled:
            if state.get("local_render_deadline_expired") is True:
                outcome = _publish_local_deadline_and_recover(
                    self,
                    lease_id=lease_id,
                    executor=executor,
                    context=context,
                    state=state,
                    render_started_epoch=render_started_epoch,
                )
            else:
                outcome = "expired" if bool(state.get("deadline_expired")) else "cancelled"
        except BaseException as exc:
            if stop.is_set():
                outcome = "expired"
            else:
                blocked = _process_worker_failure(context, exc, state)
                outcome = self._publish_result(
                    lease_id=lease_id,
                    run_id=_text(context.get("run_id")),
                    result=background._with_publication_metadata(
                        blocked,
                        lease_id=lease_id,
                        render_started_epoch=render_started_epoch or time.time(),
                    ),
                )
        finally:
            _terminate_state_process(state)
            if slot_acquired:
                release_slot_once()
            stop.set()
            self._safe_job_update(lease_id, status=outcome)
            with background._LOCAL_TASKS_LOCK:
                if background._LOCAL_TASKS.get(lease_id) is state:
                    background._LOCAL_TASKS.pop(lease_id, None)

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
        name=f"nico-final-report-process-{lease_id[-8:]}",
        daemon=True,
    )
    state.update(
        {
            "heartbeat_thread": heartbeat_thread,
            "watchdog_thread": watchdog_thread,
            "invoke_thread": invoke_thread,
        }
    )
    with background._LOCAL_TASKS_LOCK:
        background._LOCAL_TASKS[lease_id] = state

    try:
        heartbeat_thread.start()
        watchdog_thread.start()
        invoke_thread.start()
    except BaseException:
        stop.set()
        _terminate_state_process(state)
        release_slot_once()
        self._safe_job_update(lease_id, status="failed")
        with background._LOCAL_TASKS_LOCK:
            if background._LOCAL_TASKS.get(lease_id) is state:
                background._LOCAL_TASKS.pop(lease_id, None)
        raise


def _active_final_report_execution(
    record: Mapping[str, Any],
    store: Any,
) -> dict[str, Any] | None:
    if _text(record.get("current_stage")) != FINAL_REPORT_STAGE_ID:
        return None
    stage_results = record.get("stage_results")
    stage_results = stage_results if isinstance(stage_results, Mapping) else {}
    stage = stage_results.get(FINAL_REPORT_STAGE_ID)
    if not isinstance(stage, Mapping):
        return None
    execution = stage.get("stage_execution")
    execution = execution if isinstance(execution, Mapping) else {}
    lease_id = _text(execution.get("lease_id") or execution.get("publication_lease_id"))
    if not lease_id:
        return None
    try:
        job = store.load_final_report_job(lease_id)
    except Exception:
        job = None
    if not isinstance(job, Mapping):
        return {
            "artifact_schema": VERSION,
            "stage_id": FINAL_REPORT_STAGE_ID,
            "state": "recovering",
            "lease_id": lease_id,
            "durable_lease_found": False,
            "worker_model": "isolated_subprocess",
            "process_local_monotonic_deadline": True,
            "deadline_independent_of_durable_lease_reads": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    now = time.time()
    heartbeat_epoch = float(job.get("heartbeat_epoch") or 0.0)
    started_epoch = float(job.get("started_epoch") or 0.0)
    deadline = background._job_deadline_state(job, now_epoch=now)
    return {
        "artifact_schema": VERSION,
        "stage_id": FINAL_REPORT_STAGE_ID,
        "state": _text(job.get("status")) or "unknown",
        "lease_id": lease_id,
        "heartbeat_age_seconds": round(max(0.0, now - heartbeat_epoch), 1)
        if heartbeat_epoch > 0
        else None,
        "elapsed_seconds": round(max(0.0, now - started_epoch), 1)
        if started_epoch > 0
        else 0.0,
        "deadline_seconds": float(deadline.get("deadline_seconds") or 0.0),
        "deadline_phase": _text(deadline.get("phase")),
        "overdue": bool(deadline.get("overdue")),
        "durable_lease_found": True,
        "worker_model": "isolated_subprocess",
        "killable_worker": True,
        "process_local_monotonic_deadline": True,
        "deadline_independent_of_durable_lease_reads": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _service_load_with_execution(self: ComprehensiveRunService, run_id: str) -> dict[str, Any]:
    assert _ORIGINAL_SERVICE_LOAD is not None
    record = _ORIGINAL_SERVICE_LOAD(self, run_id)
    execution = _active_final_report_execution(record, self._store)
    if execution:
        projected = dict(record)
        projected["active_stage_execution"] = execution
        return projected
    return record


def _controller_response_with_execution(
    record: dict[str, Any],
    *,
    operation: str,
) -> dict[str, Any]:
    assert _ORIGINAL_CONTROLLER_RESPONSE is not None
    response = _ORIGINAL_CONTROLLER_RESPONSE(record, operation=operation)
    execution = record.get("active_stage_execution")
    if isinstance(execution, Mapping):
        projected = dict(execution)
        response["active_stage_execution"] = projected
        public_record = response.get("record")
        if isinstance(public_record, dict):
            public_record["active_stage_execution"] = projected
    return response


def install_comprehensive_final_report_process_isolation_v1(app: FastAPI) -> dict[str, Any]:
    global _ORIGINAL_START_WORKER
    global _ORIGINAL_STOP_LOCAL_TASK
    global _ORIGINAL_SERVICE_LOAD
    global _ORIGINAL_CONTROLLER_RESPONSE

    existing = getattr(app.state, _INSTALL_STATE, None)
    if isinstance(existing, Mapping) and existing.get("bound") is True:
        return dict(existing)

    if _ORIGINAL_START_WORKER is None:
        _ORIGINAL_START_WORKER = background.FinalReportPublicationCoordinator._start_worker
    if _ORIGINAL_STOP_LOCAL_TASK is None:
        _ORIGINAL_STOP_LOCAL_TASK = background.FinalReportPublicationCoordinator._stop_local_task
    if _ORIGINAL_SERVICE_LOAD is None:
        _ORIGINAL_SERVICE_LOAD = ComprehensiveRunService.load
    if _ORIGINAL_CONTROLLER_RESPONSE is None:
        _ORIGINAL_CONTROLLER_RESPONSE = ComprehensiveApiController._response

    background.FinalReportPublicationCoordinator._start_worker = _isolated_start_worker
    background.FinalReportPublicationCoordinator._stop_local_task = _isolated_stop_local_task
    ComprehensiveRunService.load = _service_load_with_execution
    ComprehensiveApiController._response = staticmethod(_controller_response_with_execution)

    setattr(background.FinalReportPublicationCoordinator._start_worker, _PATCH_MARKER, True)
    setattr(background.FinalReportPublicationCoordinator._stop_local_task, _PATCH_MARKER, True)
    setattr(ComprehensiveRunService.load, _PATCH_MARKER, True)
    setattr(ComprehensiveApiController._response, _PATCH_MARKER, True)

    bound = bool(
        getattr(background.FinalReportPublicationCoordinator._start_worker, _PATCH_MARKER, False)
        and getattr(
            background.FinalReportPublicationCoordinator._stop_local_task,
            _PATCH_MARKER,
            False,
        )
        and getattr(ComprehensiveRunService.load, _PATCH_MARKER, False)
        and getattr(ComprehensiveApiController._response, _PATCH_MARKER, False)
    )
    state = {
        "artifact_schema": VERSION,
        "status": "installed" if bound else "blocked",
        "bound": bound,
        "isolated_subprocess_worker": True,
        "hard_termination_supported": True,
        "production_executor_only": True,
        "recovery_waits_for_worker_termination": True,
        "logical_capacity_released_only_after_worker_exit": True,
        "active_stage_execution_projection": True,
        "bounded_worker_failure_diagnostics_projected": True,
        "worker_traceback_exposed": False,
        "process_local_monotonic_deadline": True,
        "deadline_independent_of_durable_lease_reads": True,
        "local_deadline_persists_blocked_result": True,
        "local_deadline_reuses_single_recovery_budget": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    setattr(app.state, _INSTALL_STATE, state)
    return dict(state)


__all__ = [
    "FINAL_REPORT_STAGE_ID",
    "VERSION",
    "_local_deadline_blocked_result",
    "install_comprehensive_final_report_process_isolation_v1",
]
