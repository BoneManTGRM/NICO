from __future__ import annotations

import os
import socket
import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_final_report_execution_boundary_v4 import (
    FINAL_REPORT_STAGE_ID,
    execute_final_report_provider,
)
from nico.comprehensive_final_report_job_store_v1 import (
    DEFAULT_MAX_ACTIVE_WORKERS,
    ComprehensiveFinalReportJobStore,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import apply_comprehensive_stage_result
from nico.comprehensive_run_store import (
    ComprehensiveRunConflict,
    ComprehensiveRunStore,
)

VERSION = "nico.comprehensive_final_report_durable_worker.v1"
DEFAULT_LEASE_SECONDS = 90
DEFAULT_HEARTBEAT_SECONDS = 20
DEFAULT_INLINE_GRACE_SECONDS = 0.25
DEFAULT_QUEUE_POLL_SECONDS = 2.0


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _configured_capacity(value: int | None) -> int:
    if value is not None:
        return max(1, int(value))
    try:
        configured = int(
            os.getenv(
                "NICO_FINAL_REPORT_MAX_ACTIVE_WORKERS",
                str(DEFAULT_MAX_ACTIVE_WORKERS),
            )
        )
    except (TypeError, ValueError):
        configured = DEFAULT_MAX_ACTIVE_WORKERS
    return max(1, configured)


def _identity(record: Mapping[str, Any]) -> dict[str, str]:
    value = record.get("identity")
    identity = value if isinstance(value, Mapping) else {}
    output = {
        field: _text(identity.get(field))
        for field in (
            "run_id",
            "repository",
            "commit_sha",
            "evidence_ledger_id",
            "customer_id",
            "project_id",
            "assessment_depth",
            "report_language",
        )
    }
    if not all(output.values()):
        raise ValueError("comprehensive_final_report_worker_identity_required")
    return output


def _stage_context(record: Mapping[str, Any]) -> dict[str, Any]:
    identity = _identity(record)
    return {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "stage_id": FINAL_REPORT_STAGE_ID,
        **identity,
        "human_evidence": deepcopy(record.get("human_evidence") or {}),
        "prior_stage_results": deepcopy(record.get("stage_results") or {}),
        "recovery_history": deepcopy(record.get("recovery_history") or []),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _running_result(
    identity: Mapping[str, str],
    job: Mapping[str, Any],
) -> dict[str, Any]:
    state = _text(job.get("state")) or "queued"
    capacity_blocked = job.get("capacity_blocked") is True
    return {
        "status": "running",
        "reason": (
            "durable_final_report_worker_queued"
            if state == "queued" or capacity_blocked
            else "durable_final_report_worker_running"
        ),
        "summary": (
            "The final Comprehensive report is queued behind another active render. "
            "Its durable worker will start automatically when capacity is available."
            if state == "queued" or capacity_blocked
            else (
                "The final Comprehensive report is rendering in a durable leased worker. "
                "Status and restart recovery remain available while the exact package is built."
            )
        ),
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
        "artifacts_available": False,
        "response_bounded": True,
        "retryable": True,
        "cancelable": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": {
            "artifact_schema": VERSION,
            "mode": "durable_final_report_worker",
            "state": state,
            "attempt": int(job.get("attempt") or 0),
            "lease_expires_at": job.get("lease_expires_at"),
            "heartbeat_at": job.get("heartbeat_at"),
            "capacity_blocked": capacity_blocked,
            "max_active_workers": int(
                job.get("max_active_workers") or DEFAULT_MAX_ACTIVE_WORKERS
            ),
            "durable_lease": True,
            "request_lifetime_independent": True,
            "canonical_run_write_by_worker": True,
            "orphan_timeout_thread_absent": True,
            "automatic_queue_monitor": True,
        },
    }


def _failure_result(
    identity: Mapping[str, str],
    *,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": error_code,
        "error_code": error_code,
        "error_message": error_message,
        "technical_reason": f"{error_code}:stage={FINAL_REPORT_STAGE_ID}",
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
        "artifacts_available": False,
        "response_bounded": True,
        "retryable": True,
        "cancelable": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_execution": {
            "artifact_schema": VERSION,
            "mode": "durable_final_report_worker",
            "durable_lease": True,
            "request_lifetime_independent": True,
            "orphan_timeout_thread_absent": True,
        },
    }


class DurableFinalReportWorker:
    """Lease, queue, heartbeat, render, validate, and persist final reports.

    One database-wide capacity limit protects API availability across app processes and
    concurrent proof runs. A local queue monitor continues trying to acquire capacity,
    while the durable lease remains reclaimable after process replacement. The canonical
    run record remains the only report source of truth.
    """

    def __init__(
        self,
        run_store: ComprehensiveRunStore,
        executor,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
        inline_grace_seconds: float = DEFAULT_INLINE_GRACE_SECONDS,
        queue_poll_seconds: float = DEFAULT_QUEUE_POLL_SECONDS,
        max_active_workers: int | None = None,
    ) -> None:
        self._run_store = run_store
        self._executor = executor
        self._lease_seconds = max(30, int(lease_seconds))
        self._heartbeat_seconds = max(5, int(heartbeat_seconds))
        self._inline_grace_seconds = max(0.0, float(inline_grace_seconds))
        self._queue_poll_seconds = max(0.05, float(queue_poll_seconds))
        self._max_active_workers = _configured_capacity(max_active_workers)
        self._job_store = ComprehensiveFinalReportJobStore(
            run_store.connection_factory,
            dialect=run_store.dialect,
        )
        self._job_store.ensure_schema()
        self._worker_prefix = (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        )
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._events: dict[str, threading.Event] = {}
        self._owners: dict[str, str] = {}

    def advance(self, record: dict[str, Any]) -> dict[str, Any]:
        """Start or observe the final worker and return a bounded canonical record."""

        identity = _identity(record)
        run_id = identity["run_id"]
        current = self._run_store.load(run_id)
        if self._final_stage_is_terminal(current):
            return current

        job = self._ensure_started(current)
        if self.wait(run_id, timeout=self._inline_grace_seconds):
            return self._run_store.load(run_id)

        latest = self._run_store.load(run_id)
        if self._final_stage_is_terminal(latest):
            return latest
        stage_results = latest.get("stage_results")
        stage_map = stage_results if isinstance(stage_results, Mapping) else {}
        existing = stage_map.get(FINAL_REPORT_STAGE_ID)
        if isinstance(existing, Mapping) and _text(existing.get("status")).lower() in {
            "queued",
            "running",
            "pending",
            "planned",
            "in_progress",
        }:
            return latest

        running = _running_result(identity, job)
        updated = apply_comprehensive_stage_result(
            latest,
            stage_id=FINAL_REPORT_STAGE_ID,
            result=running,
        )
        try:
            return self._run_store.save(
                updated,
                expected_revision=int(latest["revision"]),
            )
        except ComprehensiveRunConflict:
            return self._run_store.load(run_id)

    def wait(self, run_id: str, *, timeout: float) -> bool:
        with self._lock:
            event = self._events.get(_text(run_id))
        return bool(event and event.wait(max(0.0, float(timeout))))

    def job(self, run_id: str) -> dict[str, Any] | None:
        return self._job_store.load(run_id)

    def _event(self, run_id: str) -> threading.Event:
        with self._lock:
            event = self._events.get(run_id)
            if event is None or event.is_set():
                event = threading.Event()
                self._events[run_id] = event
            return event

    def _ensure_started(self, record: Mapping[str, Any]) -> dict[str, Any]:
        identity = _identity(record)
        run_id = identity["run_id"]
        with self._lock:
            existing = self._threads.get(run_id)
            if existing is not None and existing.is_alive():
                return self._job_store.load(run_id) or {
                    "state": "running",
                    "attempt": 0,
                    "max_active_workers": self._max_active_workers,
                }

        event = self._event(run_id)
        owner = self._new_owner()
        job = self._claim(identity, owner)
        if job.get("claimed") is True:
            worker = threading.Thread(
                target=self._run,
                args=(run_id, owner, event),
                name=f"nico-final-report-{run_id[-12:]}",
                daemon=True,
            )
        else:
            worker = threading.Thread(
                target=self._monitor_queue,
                args=(run_id, event),
                name=f"nico-final-queue-{run_id[-12:]}",
                daemon=True,
            )
        with self._lock:
            self._threads[run_id] = worker
            if job.get("claimed") is True:
                self._owners[run_id] = owner
        worker.start()
        return job

    def _claim(
        self,
        identity: Mapping[str, str],
        owner: str,
    ) -> dict[str, Any]:
        return self._job_store.claim(
            run_id=identity["run_id"],
            repository=identity["repository"],
            commit_sha=identity["commit_sha"],
            evidence_ledger_id=identity["evidence_ledger_id"],
            lease_owner=owner,
            lease_seconds=self._lease_seconds,
            max_active_workers=self._max_active_workers,
        )

    def _new_owner(self) -> str:
        return f"{self._worker_prefix}:{uuid.uuid4().hex[:12]}"

    def _monitor_queue(self, run_id: str, event: threading.Event) -> None:
        try:
            while not event.is_set():
                record = self._run_store.load(run_id)
                if self._final_stage_is_terminal(record):
                    event.set()
                    return
                identity = _identity(record)
                owner = self._new_owner()
                job = self._claim(identity, owner)
                if job.get("claimed") is True:
                    with self._lock:
                        self._owners[run_id] = owner
                    self._run(run_id, owner, event)
                    return
                if _text(job.get("state")).lower() == "complete":
                    event.set()
                    return
                event.wait(self._queue_poll_seconds)
        except BaseException:
            # A later continue request or replacement process can recreate the monitor.
            return
        finally:
            with self._lock:
                current = self._threads.get(run_id)
                if current is threading.current_thread():
                    self._threads.pop(run_id, None)

    def _run(self, run_id: str, owner: str, event: threading.Event) -> None:
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat,
            args=(run_id, owner, stop),
            name=f"nico-final-heartbeat-{run_id[-10:]}",
            daemon=True,
        )
        heartbeat.start()
        identity: dict[str, str] = {}
        terminal_state = "failed"
        error_code = ""
        error_message = ""
        try:
            record = self._run_store.load(run_id)
            identity = _identity(record)
            context = _stage_context(record)
            result = execute_final_report_provider(
                self._executor,
                context,
                execution_mode="durable_final_report_worker",
            )
            self._persist_result(run_id, result)
            terminal_state = (
                "complete"
                if _text(result.get("status")).lower() == "complete"
                else "failed"
            )
            error_code = _text(result.get("error_code") or result.get("reason"))
            error_message = _text(result.get("error_message"))
        except BaseException as exc:
            error_code = "durable_final_report_worker_exception"
            error_message = f"{type(exc).__name__}: {exc}"
            if identity:
                try:
                    self._persist_result(
                        run_id,
                        _failure_result(
                            identity,
                            error_code=error_code,
                            error_message=error_message,
                        ),
                    )
                except BaseException:
                    pass
        finally:
            stop.set()
            heartbeat.join(timeout=2)
            try:
                self._job_store.finish(
                    run_id,
                    lease_owner=owner,
                    state=terminal_state,
                    error_code=error_code,
                    error_message=error_message,
                )
            finally:
                event.set()
                with self._lock:
                    current = self._threads.get(run_id)
                    if current is threading.current_thread():
                        self._threads.pop(run_id, None)
                    self._owners.pop(run_id, None)

    def _heartbeat(
        self,
        run_id: str,
        owner: str,
        stop: threading.Event,
    ) -> None:
        while not stop.wait(self._heartbeat_seconds):
            if not self._job_store.heartbeat(
                run_id,
                lease_owner=owner,
                lease_seconds=self._lease_seconds,
            ):
                return

    def _persist_result(self, run_id: str, result: dict[str, Any]) -> None:
        expected_completed = len(COMPREHENSIVE_STAGES) - 1
        for _ in range(8):
            current = self._run_store.load(run_id)
            if self._final_stage_is_terminal(current):
                return
            completed = list(current.get("completed_stages") or [])
            if len(completed) != expected_completed:
                raise ValueError(
                    "durable_final_report_unexpected_completed_count:"
                    f"{len(completed)}:expected:{expected_completed}"
                )
            updated = apply_comprehensive_stage_result(
                current,
                stage_id=FINAL_REPORT_STAGE_ID,
                result=result,
            )
            try:
                self._run_store.save(
                    updated,
                    expected_revision=int(current["revision"]),
                )
                return
            except ComprehensiveRunConflict:
                time.sleep(0.02)
        raise ComprehensiveRunConflict(
            f"durable_final_report_persist_conflict:{run_id}"
        )

    @staticmethod
    def _final_stage_is_terminal(record: Mapping[str, Any]) -> bool:
        completed = list(record.get("completed_stages") or [])
        if FINAL_REPORT_STAGE_ID in completed:
            return True
        return bool(record.get("terminal"))


__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_INLINE_GRACE_SECONDS",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_QUEUE_POLL_SECONDS",
    "DurableFinalReportWorker",
    "VERSION",
]
