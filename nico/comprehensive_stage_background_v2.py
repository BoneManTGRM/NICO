from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_report_worker_runtime_v90 import (
    install_report_worker_runtime_v90,
    report_stage,
)
from nico.comprehensive_run_record import apply_comprehensive_stage_result
from nico.comprehensive_run_store import ComprehensiveRunConflict, ComprehensiveRunStore
from nico.comprehensive_stage_execution_timeout_v1 import execute_stage_with_timeout
from nico.comprehensive_stage_watchdog_v1 import apply_stage_watchdog

VERSION = "nico.comprehensive_stage_background.v3"
DEFAULT_ORPHAN_SECONDS = 270.0
_RUNNING_REASON = "comprehensive_stage_background_execution_in_progress"
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


def _orphan_seconds() -> float:
    return _bounded_float(
        "NICO_COMPREHENSIVE_STAGE_ORPHAN_SECONDS",
        DEFAULT_ORPHAN_SECONDS,
        30.0,
        900.0,
    )


def _stage_marker(record: Mapping[str, Any], stage_id: str) -> Mapping[str, Any]:
    stage_results = record.get("stage_results")
    if not isinstance(stage_results, Mapping):
        return {}
    value = stage_results.get(stage_id)
    if not isinstance(value, Mapping):
        return {}
    if _text(value.get("status")).casefold() != "running":
        return {}
    if _text(value.get("reason")) != _RUNNING_REASON:
        return {}
    return value


def _marker_lease(record: Mapping[str, Any], stage_id: str) -> str:
    marker = _stage_marker(record, stage_id)
    execution = marker.get("stage_execution")
    if not isinstance(execution, Mapping):
        return ""
    return _text(execution.get("lease_id"))


def _marker_started_epoch(record: Mapping[str, Any], stage_id: str) -> float:
    marker = _stage_marker(record, stage_id)
    execution = marker.get("stage_execution")
    if not isinstance(execution, Mapping):
        return 0.0
    try:
        return float(execution.get("started_epoch") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _running_result(
    context: Mapping[str, Any],
    *,
    stage_id: str,
    lease_id: str,
    started_epoch: float,
) -> dict[str, Any]:
    return {
        "status": "running",
        "reason": _RUNNING_REASON,
        "summary": (
            "This assessment stage is executing behind the exact-run boundary without "
            "holding the browser continuation request open."
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
            "mode": "canonical_detached_stage_execution",
            "stage_id": stage_id,
            "lease_id": lease_id,
            "started_epoch": started_epoch,
            "started_at": _now_iso(),
            "orphan_after_seconds": _orphan_seconds(),
            "detached_background_execution": True,
            "canonical_run_write_pending": True,
            "duplicate_execution_prevented": True,
            "exact_run_recovery_supported": True,
            "transport_request_may_return_before_stage_completion": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


def _failure_result(
    context: Mapping[str, Any],
    *,
    stage_id: str,
    message: str,
    exception_type: str = "Exception",
    report_runtime_rebound: bool = False,
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": "detached_stage_execution_failed",
        "error_code": "detached_stage_execution_failed",
        "error_message": message[:700] or "Detached stage execution failed.",
        "technical_reason": (
            f"detached_stage_execution_failed:{exception_type}:stage={stage_id}"
        ),
        "retryable": True,
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
            "mode": "canonical_detached_stage_execution",
            "stage_id": stage_id,
            "failed": True,
            "exception_type": exception_type,
            "report_runtime_v90_rebound": report_runtime_rebound,
            "exact_run_recovery_supported": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    }


class ComprehensiveStagePublicationCoordinator:
    """Execute one canonical stage outside the HTTP continuation lifetime.

    The canonical run itself is the durable lease. A continuation first commits a
    small running marker with a unique lease id and then returns. The provider runs in
    a daemon worker and may publish only while that same lease still owns the stage.
    A replacement process therefore cannot be overwritten by a late worker.

    A marker remains authoritative for one bounded orphan window. If a process dies,
    a later continuation can replace the stale marker through the normal optimistic
    revision check and safely relaunch the exact stage. No continuation POST is
    automatically replayed by the transport layer.

    Report-production stages additionally rebind their mutable compatibility aliases to
    stable v90 base delegates inside the detached worker immediately before execution.
    This removes first-install ordering as a source of report/PDF self-recursion while
    preserving the exact run, evidence, review, and client-delivery boundaries.
    """

    def __init__(self, store: ComprehensiveRunStore) -> None:
        self._store = store

    def advance(
        self,
        record: dict[str, Any],
        *,
        stage_id: str,
        executor,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = _text(context.get("run_id"))
        if not run_id:
            raise ValueError("detached_stage_run_id_required")

        lease_id = _marker_lease(record, stage_id)
        if lease_id:
            started_epoch = _marker_started_epoch(record, stage_id)
            age = max(0.0, time.time() - started_epoch) if started_epoch else 0.0
            if started_epoch and age < _orphan_seconds():
                return record

            latest = self._store.load(run_id)
            if int(latest.get("revision") or 0) != int(record.get("revision") or 0):
                return latest
            record = latest

        return self._claim_and_launch(
            record,
            stage_id=stage_id,
            executor=executor,
            context=context,
        )

    def _claim_and_launch(
        self,
        record: dict[str, Any],
        *,
        stage_id: str,
        executor,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = _text(context.get("run_id"))
        lease_id = f"stagepub_{uuid.uuid4().hex}"
        started_epoch = time.time()
        marker = _running_result(
            context,
            stage_id=stage_id,
            lease_id=lease_id,
            started_epoch=started_epoch,
        )
        expected_revision = int(record["revision"])
        updated = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result=marker,
        )
        try:
            claimed = self._store.save(updated, expected_revision=expected_revision)
        except ComprehensiveRunConflict:
            return self._store.load(run_id)

        self._start_worker(
            lease_id=lease_id,
            stage_id=stage_id,
            executor=executor,
            context=dict(context),
        )
        return claimed

    def _start_worker(
        self,
        *,
        lease_id: str,
        stage_id: str,
        executor,
        context: Mapping[str, Any],
    ) -> None:
        state = {"stage_id": stage_id, "started_epoch": time.time()}
        with _LOCAL_TASKS_LOCK:
            _LOCAL_TASKS[lease_id] = state

        def invoke() -> None:
            report_runtime_rebound = False
            try:
                if report_stage(stage_id):
                    installation = install_report_worker_runtime_v90()
                    report_runtime_rebound = (
                        installation.get("native_report_base_stable") is True
                        and installation.get("ci_pdf_base_stable") is True
                        and installation.get("detached_report_alias_recursion_blocked") is True
                    )
                    if not report_runtime_rebound:
                        raise RuntimeError("detached report worker v90 runtime guard not authoritative")

                raw = execute_stage_with_timeout(
                    executor,
                    context,
                    stage_id=stage_id,
                )
                source_record = self._store.load(_text(context.get("run_id")))
                result = apply_stage_watchdog(
                    source_record,
                    stage_id=stage_id,
                    result=raw,
                )
            except BaseException as exc:
                result = _failure_result(
                    context,
                    stage_id=stage_id,
                    message=f"{type(exc).__name__}: {_text(exc)}",
                    exception_type=type(exc).__name__,
                    report_runtime_rebound=report_runtime_rebound,
                )
            try:
                self._publish_result(
                    lease_id=lease_id,
                    stage_id=stage_id,
                    run_id=_text(context.get("run_id")),
                    result=result,
                )
            finally:
                with _LOCAL_TASKS_LOCK:
                    _LOCAL_TASKS.pop(lease_id, None)

        threading.Thread(
            target=invoke,
            name=f"nico-comprehensive-stage-{stage_id[:24]}-{lease_id[-8:]}",
            daemon=True,
        ).start()

    def _publish_result(
        self,
        *,
        lease_id: str,
        stage_id: str,
        run_id: str,
        result: Mapping[str, Any],
    ) -> str:
        for _ in range(4):
            current = self._store.load(run_id)
            if stage_id in set(current.get("completed_stages") or []):
                return "complete"
            if _marker_lease(current, stage_id) != lease_id:
                return "superseded"

            expected_revision = int(current["revision"])
            updated = apply_comprehensive_stage_result(
                current,
                stage_id=stage_id,
                result=dict(result),
            )
            try:
                self._store.save(updated, expected_revision=expected_revision)
            except ComprehensiveRunConflict:
                continue
            return _text(result.get("status")).casefold() or "unknown"
        return "conflict"


def reset_comprehensive_stage_publication_tasks_for_tests() -> None:
    with _LOCAL_TASKS_LOCK:
        _LOCAL_TASKS.clear()


__all__ = [
    "ComprehensiveStagePublicationCoordinator",
    "DEFAULT_ORPHAN_SECONDS",
    "VERSION",
    "reset_comprehensive_stage_publication_tasks_for_tests",
]
