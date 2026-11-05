"""One bounded caller-snapshot log per admission; never a durable-job verdict."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import logging
import re
from threading import RLock, Lock, Thread
from queue import Queue, Full
from uuid import uuid4

_ACTIVE = ContextVar("nico_pdf_admission_trace", default=None)
_PHASES = frozenset({"policy", "snapshot_read", "snapshot_fetch", "decode",
    "history_validation", "record_restore_validation", "report_projection",
    "lifecycle_binding", "enqueue"})
_LOG = logging.getLogger("uvicorn.error")


class _LogSink:
    """One daemon and at most 16 bounded strings; slow handlers cannot block callers."""
    def __init__(self):
        self.queue = Queue(maxsize=16)
        self.start_lock = Lock()
        self.started = False

    def _run(self):
        while True:
            encoded = self.queue.get()
            try:
                _LOG.info("nico_pdf_admission_timing=%s", encoded)
            except Exception:
                pass
            finally:
                self.queue.task_done()

    def offer(self, encoded):
        try:
            self.queue.put_nowait(encoded)
        except Full:
            return  # Loss of telemetry is safer than delaying admission or cleanup.
        if not self.started and self.start_lock.acquire(blocking=False):
            try:
                if not self.started:
                    Thread(target=self._run, daemon=True, name="nico-admission-log").start()
                    self.started = True
            except Exception:
                pass
            finally:
                self.start_lock.release()


_SINK = _LogSink()
_offer = _SINK.offer


@contextmanager
def bind_trace(trace):
    token = _ACTIVE.set(trace)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def current_trace():
    return _ACTIVE.get()


@contextmanager
def phase(name):
    trace = _ACTIVE.get()
    if trace is None or name not in _PHASES:
        yield
        return
    started = trace.guard.clock()
    with trace.lock:
        item = trace.phases.setdefault(name, dict(calls=0, active=0, elapsed_ms=0., raised=0))
        item["calls"] = min(9999, item["calls"] + 1)
        if not item["active"]:
            item["active_started"] = started
        item["remaining_ms_at_last_start"] = round(min(20000., max(0., trace.guard.remaining() * 1000)), 3)
        item["active"] += 1
    raised = False
    try:
        yield
    except BaseException:
        raised = True
        raise
    finally:
        with trace.lock:
            item["active"] -= 1
            item["elapsed_ms"] = min(3600000., item["elapsed_ms"] + max(0., (trace.guard.clock() - started) * 1000))
            item["raised"] = min(9999, item["raised"] + int(raised))


def timed(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with phase(name):
                return function(*args, **kwargs)
        return wrapped
    return decorate


class AdmissionTrace:
    def __init__(self, guard, trace_id=None):
        self.guard = guard
        self.lock = RLock()
        self.phases = {}
        self.started = guard.clock()
        self.trace_id = trace_id if type(trace_id) is str and re.fullmatch(r"[0-9a-f]{32}", trace_id) else uuid4().hex

    def emit(self, outcome):
        # No exception object, identity, arguments, paths or customer data accepted.
        # Copy at caller completion: late threads may still finish under quarantine.
        try:
            with self.guard.lock:
                commit = ("acknowledged" if self.guard.commit_acknowledged else
                          "started_unacknowledged" if self.guard.commit_started else "not_started")
                pending = not self.guard.idle()
                remaining = min(20000., max(0., self.guard.remaining() * 1000))
            with self.lock:
                phases = {name: {"calls": item["calls"], "active": min(9999, item["active"]),
                    "raised": item["raised"], "elapsed_ms": round(item["elapsed_ms"], 3),
                    "remaining_ms_at_last_start": item["remaining_ms_at_last_start"],
                    "active_span_ms": round(min(3600000., max(0., (self.guard.clock() - item["active_started"]) * 1000)), 3) if item["active"] else 0.}
                    for name, item in sorted(self.phases.items())}
            payload = dict(schema="nico.pdf-admission-timing.v1", trace_id=self.trace_id,
                snapshot="caller_return", outcome="returned" if outcome == "returned" else "raised",
                elapsed_ms=round(min(3600000., max(0., (self.guard.clock() - self.started) * 1000)), 3),
                deadline_remaining_ms=round(remaining, 3), commit_state=commit,
                physical_calls_pending=pending, durable_job_outcome="not_established_by_timing",
                phases=phases)
            encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            if len(encoded.encode("utf-8")) <= 4096:
                _offer(encoded)
        except Exception:
            pass  # Observability cannot replace the operation result or exception.

    @contextmanager
    def scope(self):
        outcome = "raised"
        with bind_trace(self):
            try:
                yield
                outcome = "returned"
            finally:
                self.emit(outcome)
