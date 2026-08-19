from __future__ import annotations

import os
import queue
import threading
import time
from copy import deepcopy
from typing import Any, Callable, Mapping

from nico.comprehensive_stage_watchdog_v1 import STALL_REASON

VERSION = "nico.comprehensive_stage_execution_timeout.v2"
DEFAULT_STAGE_EXECUTION_TIMEOUT_SECONDS = 240

StageExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def _timeout_seconds() -> int:
    try:
        value = int(
            os.getenv(
                "NICO_COMPREHENSIVE_STAGE_EXECUTION_TIMEOUT_SECONDS",
                str(DEFAULT_STAGE_EXECUTION_TIMEOUT_SECONDS),
            )
        )
    except (TypeError, ValueError):
        value = DEFAULT_STAGE_EXECUTION_TIMEOUT_SECONDS
    return max(1, min(900, value))


def _report_runtime_metadata(stage_id: str) -> dict[str, Any]:
    """Install the stable report runtime for every generic report-stage execution.

    Decision-report generation currently executes through this timeout boundary rather
    than the dedicated final-report coordinator. Rebinding only inside the historical
    detached-stage coordinator therefore leaves a real production path dependent on
    process import order. Keep the runtime repair at the universal execution boundary so
    any caller of a report stage receives the same stable v90/v88 alias chain before the
    provider thread starts.
    """

    from nico.comprehensive_report_worker_runtime_v90 import (
        install_report_worker_runtime_v90,
        report_stage,
    )

    if not report_stage(stage_id):
        return {}

    installation = install_report_worker_runtime_v90()
    authoritative = (
        installation.get("native_report_base_stable") is True
        and installation.get("ci_pdf_base_stable") is True
        and installation.get("detached_report_alias_recursion_blocked") is True
        and installation.get("spanish_guard_bound") is True
    )
    if not authoritative:
        raise RuntimeError(
            f"report stage runtime guard not authoritative:stage={stage_id}"
        )
    return {
        "report_runtime_v90_rebound": True,
        "report_runtime_boundary": "universal_stage_execution_timeout",
        "report_runtime_process_history_independent": True,
    }


def execute_stage_with_timeout(
    executor: StageExecutor,
    context: Mapping[str, Any],
    *,
    stage_id: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Execute one stage without allowing the request worker to wait indefinitely.

    The stage runs in a daemon thread so an unresponsive provider cannot hold the
    HTTP request forever. A timeout does not invent completion or discard prior
    evidence. It returns a fail-closed stage result that uses the existing stalled-
    stage recovery contract and therefore permits at most one explicit retry.

    Report stages additionally rebind the stable v90 runtime before the provider thread
    starts. This covers synchronous decision-report execution as well as callers that
    reach this boundary through detached orchestration, removing process history as a
    source of Spanish/report publication drift.
    """

    report_runtime = _report_runtime_metadata(stage_id)
    limit = max(1, min(900, int(timeout_seconds or _timeout_seconds())))
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    started = time.monotonic()

    def invoke() -> None:
        try:
            result_queue.put_nowait(("result", executor(deepcopy(dict(context)))))
        except BaseException as exc:  # preserve the provider's original exception
            try:
                result_queue.put_nowait(("error", exc))
            except queue.Full:
                pass

    worker = threading.Thread(
        target=invoke,
        name=f"nico-stage-{stage_id}",
        daemon=True,
    )
    worker.start()
    worker.join(limit)
    elapsed = round(time.monotonic() - started, 3)

    if worker.is_alive():
        return {
            "status": "blocked",
            "reason": STALL_REASON,
            "error_code": "stage_execution_timeout",
            "error_message": (
                f"Stage {stage_id} exceeded the {limit}-second execution boundary."
            ),
            "technical_reason": (
                f"stage_execution_timeout:stage={stage_id}:limit_seconds={limit}"
            ),
            "retryable": True,
            "cancelable": True,
            "artifacts_available": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "watchdog": {
                "artifact_schema": VERSION,
                "stage_id": stage_id,
                "execution_timeout_seconds": limit,
                "elapsed_seconds": elapsed,
                "progress_changed": False,
                "no_progress_attempts": 1,
                "stalled_seconds": int(elapsed),
                "revision_only_changes_count_as_progress": False,
                "scanner_evidence_preserved": True,
                "provider_thread_daemonized": True,
                "stalled": True,
                **report_runtime,
            },
        }

    kind, value = result_queue.get_nowait()
    if kind == "error":
        raise value
    if not isinstance(value, dict):
        raise TypeError(f"stage_executor_must_return_dict:{stage_id}")
    output = deepcopy(value)
    output.setdefault("stage_execution", {})
    if isinstance(output["stage_execution"], dict):
        output["stage_execution"].update(
            {
                "artifact_schema": VERSION,
                "elapsed_seconds": elapsed,
                "execution_timeout_seconds": limit,
                "completed_within_boundary": True,
                **report_runtime,
            }
        )
    return output


__all__ = [
    "DEFAULT_STAGE_EXECUTION_TIMEOUT_SECONDS",
    "VERSION",
    "execute_stage_with_timeout",
]
