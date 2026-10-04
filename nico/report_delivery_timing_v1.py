from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

_ACTIVE: ContextVar[dict[str, Any] | None] = ContextVar("nico_report_delivery_timing", default=None)
_LOGGER = logging.getLogger("uvicorn.error")


@contextmanager
def report_delivery_timing(run_id: str, report_language: str):
    """Observe one authenticated route; never retain input bodies or credentials."""
    state: dict[str, Any] = {"phases": {}}
    token = _ACTIVE.set(state)
    started = time.perf_counter()
    outcome, error_type = "completed", ""
    try:
        yield
    except BaseException as exc:
        outcome, error_type = "failed", type(exc).__name__
        raise
    finally:
        _ACTIVE.reset(token)
        payload = {
            "schema": "nico.report-delivery-timing.v1",
            "run_id": run_id if re.fullmatch(r"comprun_[0-9a-f]{32}", run_id) else "invalid_or_fixture_run_id",
            "report_language": report_language if report_language in {"en", "es-MX"} else "unsupported",
            "outcome": outcome,
            "error_type": error_type,
            "response_preparation_ms": round((time.perf_counter() - started) * 1000, 3),
            "phase_times_are_inclusive": True,
            "http_transfer_completion_inferred": False,
            "phases": state["phases"],
        }
        try:
            _LOGGER.info("NICO_REPORT_TIMING=%s", json.dumps(payload, separators=(",", ":"), sort_keys=True))
        except Exception:
            # Observability must never change report delivery or hide its error.
            pass


def report_delivery_phase(name: str):
    def decorate(function):
        @wraps(function)
        def observed(*args, **kwargs):
            state = _ACTIVE.get()
            if state is None:
                return function(*args, **kwargs)
            started, cpu = time.perf_counter(), time.thread_time()
            try:
                return function(*args, **kwargs)
            finally:
                phase = state["phases"].setdefault(name, {"calls": 0, "elapsed_ms": 0.0, "thread_cpu_ms": 0.0})
                phase["calls"] += 1
                phase["elapsed_ms"] = round(phase["elapsed_ms"] + (time.perf_counter() - started) * 1000, 3)
                phase["thread_cpu_ms"] = round(phase["thread_cpu_ms"] + (time.thread_time() - cpu) * 1000, 3)
        return observed
    return decorate

def report_delivery_call(name: str, function, *args, **kwargs):
    """Time the currently bound callable without retaining arguments or results."""
    if _ACTIVE.get() is None:
        return function(*args, **kwargs)
    return report_delivery_phase(name)(function)(*args, **kwargs)
