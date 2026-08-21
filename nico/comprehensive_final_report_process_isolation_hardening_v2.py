from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Mapping
from typing import Any, Callable

from fastapi import FastAPI

from nico import comprehensive_final_report_background_v1 as background

VERSION = "nico.comprehensive_final_report_process_isolation_hardening.v2"
_INSTALL_STATE = "nico_final_report_process_isolation_hardening_v2"
_PATCH_MARKER = "__nico_final_report_process_capacity_gate_v2__"
_ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY: Callable[[dict[str, Any]], None] | None = None


def _isolated_worker_still_alive(state: Mapping[str, Any]) -> bool:
    process = state.get("worker_process")
    return isinstance(process, subprocess.Popen) and process.poll() is None


def _release_original_capacity(state: dict[str, Any]) -> None:
    if _ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY is None:
        raise RuntimeError("final_report_capacity_release_original_missing")
    _ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY(state)


def _schedule_capacity_release_after_worker_exit(state: dict[str, Any]) -> None:
    process = state.get("worker_process")
    if not isinstance(process, subprocess.Popen) or process.poll() is not None:
        return
    state_lock = state.get("state_lock")
    lock = state_lock if isinstance(state_lock, threading.RLock().__class__) else None
    if lock is not None:
        with lock:
            if state.get("capacity_exit_reaper_started") is True:
                return
            state["capacity_exit_reaper_started"] = True
    elif state.get("capacity_exit_reaper_started") is True:
        return
    else:
        state["capacity_exit_reaper_started"] = True

    def reap() -> None:
        while process.poll() is None:
            time.sleep(0.2)
        state["physical_worker_exit_confirmed"] = True
        state["capacity_release_blocked_until_worker_exit"] = False
        state["capacity_exit_reaper_completed"] = True
        _release_original_capacity(state)

    thread = threading.Thread(
        target=reap,
        name=f"nico-final-report-capacity-reaper-{int(process.pid or 0)}",
        daemon=True,
    )
    state["capacity_exit_reaper_thread"] = thread
    thread.start()


def _release_local_task_capacity_after_physical_exit(state: dict[str, Any]) -> None:
    """Never reuse renderer capacity while an isolated renderer process is alive.

    The v1 coordinator correctly fences expired leases before recovery, but its generic
    capacity helper historically released the single renderer semaphore regardless of
    whether process termination was actually confirmed. Keep generic/fake executor
    behavior unchanged and strengthen only isolated production workers. If a stubborn
    process survives the bounded termination attempt, a daemon reaper retains the slot
    until that exact process actually exits and then releases the slot exactly once.
    """

    if state.get("worker_model") == "isolated_subprocess":
        if _isolated_worker_still_alive(state):
            state["capacity_release_blocked_until_worker_exit"] = True
            state["physical_worker_exit_confirmed"] = False
            _schedule_capacity_release_after_worker_exit(state)
            return
        state["physical_worker_exit_confirmed"] = True
        state["capacity_release_blocked_until_worker_exit"] = False

    _release_original_capacity(state)


def install_comprehensive_final_report_process_isolation_hardening_v2(
    app: FastAPI,
) -> dict[str, Any]:
    global _ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY

    existing = getattr(app.state, _INSTALL_STATE, None)
    if isinstance(existing, Mapping) and existing.get("bound") is True:
        return dict(existing)

    current = background._release_local_task_capacity
    if getattr(current, _PATCH_MARKER, False):
        bound = True
    else:
        if _ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY is None:
            _ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY = current
        background._release_local_task_capacity = (
            _release_local_task_capacity_after_physical_exit
        )
        setattr(background._release_local_task_capacity, _PATCH_MARKER, True)
        bound = bool(
            getattr(background._release_local_task_capacity, _PATCH_MARKER, False)
        )

    state = {
        "artifact_schema": VERSION,
        "status": "installed" if bound else "blocked",
        "bound": bound,
        "physical_worker_exit_required_before_capacity_release": True,
        "failed_termination_keeps_renderer_capacity_reserved": True,
        "eventual_exit_releases_reserved_capacity": True,
        "generic_executor_capacity_behavior_unchanged": True,
        "process_group_descendant_cleanup_required": True,
        "private_transport_permissions_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    setattr(app.state, _INSTALL_STATE, state)
    return dict(state)


__all__ = [
    "VERSION",
    "install_comprehensive_final_report_process_isolation_hardening_v2",
]
