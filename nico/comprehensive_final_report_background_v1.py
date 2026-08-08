from __future__ import annotations

import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator, Mapping

from nico.comprehensive_final_report_execution_boundary_v4 import (
    FINAL_REPORT_STAGE_ID,
    execute_final_report_stage,
)
from nico.comprehensive_run_record import apply_comprehensive_stage_result
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunStore

VERSION = "nico.comprehensive_final_report_background.v2"
DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_ORPHAN_SECONDS = 30.0
_RUNNING_REASON = "final_report_background_publication_in_progress"
_LOCAL_TASKS: dict[str, dict[str, Any]] = {}
_LOCAL_TASKS_LOCK = threading.RLock()
_PUBLICATION_SLOT = threading.BoundedSemaphore(value=1)
_PUBLICATION_SLOT_STATE_LOCK = threading.RLock()
_ACTIVE_PUBLICATION_LEASE_ID = ""


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


@contextmanager
def _publication_slot(lease_id: str) -> Iterator[None]:
    """Admit one CPU-heavy final report provider at a time in the production process.

    Railway intentionally runs one NICO web worker. Exact-head production proofs can
    create several independent Comprehensive runs at once, and concurrent report
    renderers previously starved status and readiness requests. Waiting publication
    workers keep their durable heartbeat and exact-run marker, but only the admitted
    lease invokes the provider. The slot is held for the provider's actual lifetime,
    so a timed-out nested worker can no longer be left behind while another report is
    admitted.
    """

    normalized = _text(lease_id)
    if not normalized:
        raise ValueError("final_report_publication_lease_required")
    _PUBLICATION_SLOT.acquire()
    global _ACTIVE_PUBLICATION_LEASE_ID
    with _PUBLICATION_SLOT_STATE_LOCK:
        _ACTIVE_PUBLICATION_LEASE_ID = normalized
    try:
        yield
    finally:
        with _PUBLICATION_SLOT_STATE_LOCK:
            if _ACTIVE_PUBLICATION_LEASE_ID == normalized:
                _ACTIVE_PUBLICATION_LEASE_ID = ""
        _PUBLICATION_SLOT.release()


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
            "publication_admission_mode": "process_local_single_slot",
            "maximum_concurrent_publications": 1,
            "provider_thread_owned_by_final_report_coordinator": True,
            "nested_timeout_worker_created": False,
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
            "publication_admission_mode": "process_local_single_slot",
            "maximum_concurrent_publications": 1,
            "provider_thread_owned_by_final_report_coordinator": True,
            "nested_timeout_worker_created": False,
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

    Because production uses one web worker, final report provider calls are admitted
    through one process-local slot. Independent exact runs may queue concurrently and
    keep heartbeating, but they cannot render simultaneously and starve status,
    readiness, or persistence traffic.
    """

    def __init__(
        self,
        store: ComprehensiveRunStore,
        capability_executors: Mapping[str, CapabilityExecutor],
    ) -> None:
        self._store = store
        self._stage_executors = bind_capability_executors(capability_executors)
        self._final_report_publication = FinalReportPublicationCoordinator(store)
