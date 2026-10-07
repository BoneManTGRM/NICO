"""Bounded test-only observation; no admission, deadline, or cleanup repair.

The imported autouse fixture observes the six synthetic watchdog tests. Wrapped
functions receive their original arguments exactly once; returns and exceptions
are preserved. This adds overhead and is not a performance measurement. Snapshots
are deliberately non-transactional and never include contexts, source text,
exception messages, database paths, report bytes, or raw lease/run identifiers.
"""
from __future__ import annotations

import functools
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import sys
import threading
import time

import pytest


_RUNS = frozenset({
    "comprun_watchdog_auto_recovery", "comprun_watchdog_exhausted",
    "comprun_status_restart_recovery", "comprun_terminal_fence",
    "comprun_watchdog_transient_read",
})
_STATUSES = frozenset({
    "queued", "rendering", "running", "terminating", "complete", "blocked",
    "failed", "cancelled", "superseded", "expired", "missing", "unknown",
})
_LIMIT = 128
_THREAD_PREFIX = "nico-final-report-"


def _token(value, limit=180):
    return value[:limit] if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9_.<>\[\]-]{1,180}", value
    ) else "unavailable"


def _status(value):
    return value if isinstance(value, str) and value in _STATUSES else "unknown"


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def _error(exc):
    return _token(type(exc).__module__ + "." + type(exc).__qualname__)


def _proof(function):
    proof = {
        "module": _token(getattr(function, "__module__", "")),
        "qualified_name": _token(getattr(function, "__qualname__", "")),
    }
    code = getattr(function, "__code__", None)
    if code is not None:
        proof["code_qualified_name"] = _token(code.co_qualname)
        proof["bytecode_sha256"] = hashlib.sha256(code.co_code).hexdigest()
        proof["source_file_basename"] = _token(Path(code.co_filename).name)
        proof["first_line"] = code.co_firstlineno
    try:
        proof["source_sha256"] = hashlib.sha256(
            inspect.getsource(function).encode("utf-8")
        ).hexdigest()
    except BaseException as exc:
        proof["source_unavailable_error_class"] = _error(exc)
    return proof


class _Observation:
    def __init__(self, background, request):
        self.background = background
        self.test_name = _token(request.node.name)
        self.started = time.perf_counter()
        self.events = []
        self.event_lock = threading.Lock()
        self.dropped = 0
        self.diagnostic_errors = 0
        self.error_classes = []
        self.leases = {}
        self.runs = {}
        self.stores = {}
        self.stop_labels = {}
        self.thread_labels = {}
        self.status_seen = {}
        self.bindings = {}
        self.targets = []
        self.installed = []
        self.closed = False

    def _failed_diagnostic(self, exc):
        self.diagnostic_errors += 1
        name = _error(exc)
        if name not in self.error_classes and len(self.error_classes) < 8:
            self.error_classes.append(name)

    def safe(self, function, *args, default=None):
        try:
            return function(*args)
        except BaseException as exc:
            try:
                self._failed_diagnostic(exc)
            except BaseException:
                pass
            return default

    def thread(self):
        current = threading.current_thread()
        key = id(current)
        if key not in self.thread_labels:
            self.thread_labels[key] = "thread-" + str(len(self.thread_labels) + 1)
        return self.thread_labels[key]

    def lease(self, value):
        if value not in self.leases:
            self.leases[value] = "lease-" + str(len(self.leases) + 1)
        return self.leases[value]

    def owned_context(self, context, coordinator=None):
        if not isinstance(context, dict) or context.get("run_id") not in _RUNS:
            return False
        run_id = context["run_id"]
        if run_id not in self.runs:
            self.runs[run_id] = "synthetic-run-" + str(len(self.runs) + 1)
        if coordinator is not None:
            store = getattr(coordinator, "_store", None)
            self.stores[id(store)] = store
        return True

    def current_lease(self):
        name = threading.current_thread().name
        for lease, label in list(self.leases.items()):
            if name.endswith(lease[-8:]):
                return label
        return "unassociated"

    def record(self, phase, fields=None):
        if not self.event_lock.acquire(blocking=False):
            self.dropped += 1
            return
        try:
            if self.closed:
                return
            if len(self.events) >= _LIMIT:
                self.dropped += 1
                return
            self.events.append({
                "phase": phase, "since_fixture_ms": round(
                    (time.perf_counter() - self.started) * 1000, 3
                ), "thread": self.thread(), **(fields or {}),
            })
        finally:
            self.event_lock.release()

    def state(self, state):
        if not isinstance(state, dict):
            return {"state_available": False}
        stop = state.get("stop")
        model = state.get("worker_model")
        return {
            "state_available": True, "phase": _status(state.get("phase")),
            "stop_set": stop.is_set() if isinstance(stop, threading.Event) else None,
            "slot_acquired": state.get("slot_acquired") is True,
            "slot_released": state.get("slot_released") is True,
            "worker_model": "isolated_subprocess" if model == "isolated_subprocess"
            else "generic" if model is None else "other",
        }

    def summary(self):
        tasks = list(self.background._LOCAL_TASKS.values())
        return {"live_task_count": len(tasks), "semaphore_value_observed":
                _number(getattr(self.background._PUBLICATION_SLOT, "_value", None))}

    def before(self, kind, args, kwargs):
        fields = {}
        scope = False
        if kind in {"claim", "start", "expire", "recover"}:
            context = kwargs.get("context")
            if kind == "claim" and len(args) > 3:
                context = args[3]
            scope = self.owned_context(context, args[0])
            lease = kwargs.get("lease_id")
            if scope and isinstance(lease, str):
                fields["lease"] = self.lease(lease)
        elif kind == "create":
            run_id, lease = kwargs.get("run_id"), kwargs.get("lease_id")
            scope = run_id in _RUNS and isinstance(lease, str)
            if scope:
                self.owned_context({"run_id": run_id})
                self.stores[id(args[0])] = args[0]
                fields.update(lease=self.lease(lease), status=_status(kwargs.get("status")))
        elif kind in {"transition", "durable_transition", "update", "stop"}:
            lease = args[1] if len(args) > 1 else kwargs.get("lease_id")
            scope = lease in self.leases
            if scope:
                fields["lease"] = self.leases[lease]
            if kind == "update":
                fields["status"] = _status(kwargs.get("status"))
        elif kind == "acquire":
            stop = args[0]
            lease = self.current_lease()
            scope = lease != "unassociated"
            if scope:
                self.stop_labels[id(stop)] = lease
                fields.update(lease=lease, stop_set=stop.is_set())
        elif kind == "release":
            state = args[0]
            stop = state.get("stop") if isinstance(state, dict) else None
            lease = self.stop_labels.get(id(stop), self.current_lease())
            scope = lease != "unassociated"
            fields = {"lease": lease, **self.state(state)}
        elif kind in {"guards", "managed"}:
            scope = self.current_lease() != "unassociated"
            fields["lease"] = self.current_lease()
        elif kind == "reset":
            scope, fields = True, self.summary()
        if scope:
            # Heartbeats are deduplicated on their actual returned status below.
            if kind != "update":
                self.record(kind + ".entry", fields)
        return scope, fields

    def after(self, kind, args, kwargs, scope, fields, value=None, exc=None):
        if not scope:
            return
        fields = dict(fields)
        if exc is not None:
            fields["error_class"] = _error(exc)
            self.record(kind + ".error", fields)
            return
        if kind in {"transition", "durable_transition", "update", "acquire"}:
            fields["returned_bool"] = value if type(value) is bool else None
        if kind == "acquire":
            fields["stop_set"] = args[0].is_set()
        if kind == "release":
            fields.update(self.state(args[0]))
        if kind == "reset":
            fields.update(self.summary())
        if kind == "managed" and isinstance(value, tuple) and len(value) == 3:
            fields["result_kind"] = value[0] if value[0] in {"result", "error", "timeout"} else "unknown"
            if value[0] == "error" and isinstance(value[1], BaseException):
                fields["executor_error_class"] = _error(value[1])
        if kind == "guards" and isinstance(value, dict):
            fields["structured_return"] = True
        if kind == "update":
            key = (fields.get("lease"), fields.get("status"), fields.get("returned_bool"))
            if key in self.status_seen:
                return
            self.status_seen[key] = True
        self.record(kind + ".return", fields)

    def install(self, monkeypatch, owner, name, kind):
        original = getattr(owner, name)
        label = kind + ":" + name
        self.bindings[label] = self.safe(_proof, original, default={"proof_unavailable": True})
        self.targets.append((label, owner, name))

        @functools.wraps(original)
        def observed(*args, **kwargs):
            scope, fields = self.safe(self.before, kind, args, kwargs, default=(False, {}))
            try:
                value = original(*args, **kwargs)
            except BaseException as exc:
                self.safe(self.after, kind, args, kwargs, scope, fields, None, exc)
                raise
            self.safe(self.after, kind, args, kwargs, scope, fields, value, None)
            return value

        monkeypatch.setattr(owner, name, observed)
        self.installed.append(label)

    def final_state(self):
        tasks = []
        for index, state in enumerate(list(self.background._LOCAL_TASKS.values())[:16]):
            tasks.append({"task": "task-" + str(index + 1), **self.state(state),
                          "threads": {
                              key: value.is_alive() for key, value in list(state.items())
                              if key in {"invoke_thread", "watchdog_thread", "heartbeat_thread"}
                              and isinstance(value, threading.Thread)
                          }})
        rows = []
        for store in list(self.stores.values())[:6]:
            for lease, label in list(self.leases.items())[:12]:
                try:
                    job = store.load_final_report_job(lease)
                    if isinstance(job, dict):
                        rows.append({"lease": label, "status": _status(job.get("status")),
                                     "started_epoch": _number(job.get("started_epoch")),
                                     "heartbeat_epoch": _number(job.get("heartbeat_epoch"))})
                except BaseException as exc:
                    rows.append({"lease": label, "read_error_class": _error(exc)})
        frames = sys._current_frames()
        workers = []
        for thread in threading.enumerate():
            if not thread.name.startswith(_THREAD_PREFIX):
                continue
            if len(workers) >= 24:
                break
            stack = []
            frame = frames.get(thread.ident)
            while frame is not None and len(stack) < 10:
                stack.append({"source_file_basename": _token(Path(frame.f_code.co_filename).name),
                              "function": _token(frame.f_code.co_name), "line": frame.f_lineno})
                frame = frame.f_back
            workers.append({"thread": self.thread_labels.setdefault(
                id(thread), "thread-" + str(len(self.thread_labels) + 1)
            ), "alive": thread.is_alive(), "stack_innermost_first": stack})
        return {**self.summary(), "tasks": tasks, "synthetic_job_rows": rows,
                "final_report_workers": workers, "tasks_limit": 16,
                "workers_limit": 24, "stack_frames_limit_per_worker": 10,
                "snapshot_atomic": False}

    def emit(self):
        final = self.safe(self.final_state, default={"snapshot_unavailable": True})
        bindings_after = {}
        for label, owner, name in self.targets:
            bindings_after[label] = self.safe(_proof, getattr(owner, name),
                                              default={"proof_unavailable": True})
        self.closed = True
        payload = {
            "schema": "nico.synthetic-watchdog-startup-observation.v1",
            "test_name": self.test_name, "python_version": sys.version.split()[0],
            "event_limit": _LIMIT, "events": list(self.events),
            "events_dropped": self.dropped, "diagnostic_errors": self.diagnostic_errors,
            "diagnostic_error_classes": list(self.error_classes),
            "actual_bindings_before_observation": self.bindings,
            "installed_observation_bindings": list(self.installed),
            "actual_bindings_at_fixture_teardown": bindings_after,
            "final_state": final, "instrumentation_changes_timing": True,
            "performance_or_production_acceptance": False,
            "returns_exceptions_arguments_and_test_limits_preserved": True,
            "cleanup_action_performed_by_observer": False,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > 131072:
            encoded = json.dumps({"schema": payload["schema"], "test_name": self.test_name,
                                  "diagnostic_output_size_limit_exceeded": True})
        print("\nNICO_WATCHDOG_STARTUP_OBSERVATION=" + encoded)


@pytest.fixture(autouse=True)
def observe_watchdog_startup(monkeypatch, request):
    """Observe only this imported test module; never repair or join its workers."""
    observer = None
    try:
        background = sys.modules["nico.comprehensive_final_report_background_v1"]
        boundary = sys.modules["nico.comprehensive_final_report_execution_boundary_v4"]
        store_module = sys.modules["nico.comprehensive_run_store"]
        observer = _Observation(background, request)
        coordinator = background.FinalReportPublicationCoordinator
        targets = (
            (background, "_acquire_publication_slot", "acquire"),
            (background, "_release_local_task_capacity", "release"),
            (background, "reset_final_report_publication_tasks_for_tests", "reset"),
            (coordinator, "_claim_and_launch", "claim"),
            (coordinator, "_start_worker", "start"),
            (coordinator, "_transition_job_to_rendering", "transition"),
            (coordinator, "_expire_publication", "expire"),
            (coordinator, "_recover_after_deadline", "recover"),
            (coordinator, "_stop_local_task", "stop"),
            (boundary, "_install_final_report_runtime_guards", "guards"),
            (boundary, "_execute_managed", "managed"),
            (store_module.ComprehensiveRunStore, "create_final_report_job", "create"),
            (store_module.ComprehensiveRunStore, "transition_final_report_job_to_rendering", "durable_transition"),
            (store_module.ComprehensiveRunStore, "update_final_report_job", "update"),
        )
        for owner, name, kind in targets:
            observer.safe(observer.install, monkeypatch, owner, name, kind)
    except BaseException:
        # Observation availability never changes the tested outcome.
        pass
    try:
        yield
    finally:
        if observer is not None:
            observer.safe(observer.emit)
