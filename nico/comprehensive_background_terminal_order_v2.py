from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Mapping

from nico import comprehensive_background_stage_execution_v1 as background

VERSION = "nico.comprehensive_background_terminal_order.v2"

_TERMINAL_STATUSES = frozenset({"complete", "failed", "timed_out"})
_INSTALL_LOCK = threading.RLock()
_TASK_LOCKS: dict[str, threading.RLock] = {}
_TERMINAL_TASKS: dict[str, dict[str, Any]] = {}
_INSTALLED = False


def _status(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    return str(payload.get("status") or "").strip().casefold()


def _task_lock(task_id: str) -> threading.RLock:
    with _INSTALL_LOCK:
        return _TASK_LOCKS.setdefault(task_id, threading.RLock())


def install_background_terminal_ordering() -> bool:
    """Make durable background task status transitions monotonic.

    Background providers and their heartbeat thread can finish at nearly the same
    time. Without serialization, a delayed heartbeat may write ``running`` after the
    provider persisted ``complete``. A later request process then sees a live task
    forever even though the report already exists locally.

    This wrapper serializes writes per task and refuses any transition from a terminal
    state back to a non-terminal state. It changes no provider result, report content,
    score, finding, approval decision, or client-delivery boundary.
    """

    global _INSTALLED
    with _INSTALL_LOCK:
        current = background._put_job
        if getattr(current, "_nico_terminal_ordering_v2", False):
            _INSTALLED = True
            return False

        original = current

        def ordered_put_job(task_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
            candidate = deepcopy(dict(payload))
            candidate_status = _status(candidate)
            lock = _task_lock(task_id)
            with lock:
                retained = _TERMINAL_TASKS.get(task_id)
                if retained and candidate_status not in _TERMINAL_STATUSES:
                    return deepcopy(retained)

                durable = background._durable_job(task_id)
                durable_status = _status(durable)
                if durable_status in _TERMINAL_STATUSES:
                    retained = deepcopy(durable)
                    _TERMINAL_TASKS[task_id] = retained
                    if candidate_status not in _TERMINAL_STATUSES:
                        return deepcopy(retained)

                persisted = original(task_id, candidate)
                if candidate_status in _TERMINAL_STATUSES:
                    retained = deepcopy(
                        persisted if isinstance(persisted, Mapping) else candidate
                    )
                    _TERMINAL_TASKS[task_id] = retained
                return deepcopy(
                    persisted if isinstance(persisted, Mapping) else candidate
                )

        ordered_put_job._nico_terminal_ordering_v2 = True  # type: ignore[attr-defined]
        ordered_put_job._nico_original_put_job = original  # type: ignore[attr-defined]
        background._put_job = ordered_put_job
        _INSTALLED = True
        return True


def background_terminal_ordering_installed() -> bool:
    return bool(
        _INSTALLED
        and getattr(background._put_job, "_nico_terminal_ordering_v2", False)
    )


def reset_background_terminal_ordering_for_tests() -> None:
    with _INSTALL_LOCK:
        _TASK_LOCKS.clear()
        _TERMINAL_TASKS.clear()


__all__ = [
    "VERSION",
    "background_terminal_ordering_installed",
    "install_background_terminal_ordering",
    "reset_background_terminal_ordering_for_tests",
]
