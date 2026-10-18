from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any
from uuid import uuid4

_ACTIVE: ContextVar[dict[str, Any] | None] = ContextVar("nico_report_delivery_timing", default=None)
_LOGGER = logging.getLogger("uvicorn.error")

# Reserve 14 detail records, 17 ordinary records (including route_started),
# and one final aggregate. Repeated/suppressed phases still aggregate all calls.
_MAX_RECORDS_PER_REQUEST = 32
_DETAIL_PHASE_NAMES = frozenset({
    'prep_reconcile', 'prep_truth_repair', 'prep_installed_completion',
    'prep_stage_projection', 'prep_coverage', 'finalize_core',
    'finalize_prepare', 'finalize_legacy', 'finalize_truth',
    'finalize_presentation', 'finalize_pdf', 'finalize_validation',
    'finalize_binding', 'finalize_manifest_attach',
})
_DETAIL_RECORDS = 14
_ORDINARY_RECORDS = 17
_PHASE_NAMES = _DETAIL_PHASE_NAMES | frozenset({
    'artifact_finalize',
    'artifact_preparation',
    'artifact_render',
    'canonical_integrity',
    'client_pdf_status_sanitizer',
    'combined_compaction',
    'compact_design_validation',
    'controller_status',
    'final_navigation',
    'four_phase_pdf',
    'frozen_pdf',
    'installed_render_target',
    'limitation_compaction',
    'manifest_refresh',
    'markdown_render',
    'package_integrity',
    'pdf_text_lookup',
    'pdf_text_parse',
    'record_decompress_decode',
    'record_integrity_hash',
    'render_target',
    'report_accuracy',
    'report_authority',
    'report_clarity_text',
    'repository_delivery_section',
    'retained_pdf_cache_probe',
    'retained_pdf_exact_input',
    'retained_pdf_input_fingerprint',
    'retired_appendix_validation',
    'semantic_navigation',
    'source_pdf_projection_check',
    'stage_reflow',
    'truth_parity_projection',
    'zip_encoding',
})


def _emit(prefix: str, payload: dict[str, Any]) -> None:
    try:
        _LOGGER.info("%s=%s", prefix, json.dumps(payload, separators=(",", ":"), sort_keys=True))
    except Exception:
        # Diagnostics must not change delivery or hide its original exception.
        pass


def _progress(state: dict[str, Any], event: str, **fields: Any) -> None:
    detail = event == "phase_completed" and fields.get("phase") in _DETAIL_PHASE_NAMES
    budget_key = "detail_records" if detail else "ordinary_records"
    limit = _DETAIL_RECORDS if detail else _ORDINARY_RECORDS
    if state[budget_key] >= limit or state["progress_records"] >= _MAX_RECORDS_PER_REQUEST - 1:
        state["progress_suppressed"] += 1
        return
    state[budget_key] += 1
    state["progress_records"] += 1
    _emit("NICO_REPORT_PROGRESS", {
        "schema": "nico.report-delivery-progress.v1",
        **state["identity"], "event": event,
        "sequence": state["progress_records"],
        "http_transfer_completion_inferred": False,
        **fields,
    })


@contextmanager
def report_delivery_timing(run_id: str, report_language: str):
    """Observe one authenticated route; never retain input bodies or credentials."""
    identity = {
        "run_id": run_id if re.fullmatch(r"comprun_[0-9a-f]{32}", run_id) else "invalid_or_fixture_run_id",
        "report_language": report_language if report_language in {"en", "es-MX"} else "unsupported",
        "request_id": uuid4().hex,
    }
    # Preserve the internal binding consumed by the retained-metadata observer.
    # Only the separately sanitized identity is serialized into timing logs.
    state: dict[str, Any] = {"phases": {}, "run_id": run_id,
                             "report_language": report_language, "identity": identity,
                             "progress_records": 0, "progress_suppressed": 0,
                             "detail_records": 0, "ordinary_records": 0,
                             "reported_phases": set()}
    token = _ACTIVE.set(state)
    started = time.perf_counter()
    outcome, error_type = "completed", ""
    _progress(state, "route_started")
    try:
        yield
    except BaseException as exc:
        outcome, error_type = "failed", type(exc).__name__
        raise
    finally:
        _ACTIVE.reset(token)
        payload = {
            "schema": "nico.report-delivery-timing.v1",
            **identity,
            "progress_records": state["progress_records"],
            "progress_suppressed": state["progress_suppressed"],
            "outcome": outcome,
            "error_type": error_type,
            "response_preparation_ms": round((time.perf_counter() - started) * 1000, 3),
            "phase_times_are_inclusive": True,
            "http_transfer_completion_inferred": False,
            "phases": state["phases"],
        }
        _emit("NICO_REPORT_TIMING", payload)


@contextmanager
def report_delivery_phase_scope(name: str):
    """Measure a fixed, code-owned phase name without retaining arguments or results."""
    state = _ACTIVE.get()
    if state is None:
        yield
        return
    name = name if name in _PHASE_NAMES else "unknown_phase"
    started, cpu = time.perf_counter(), time.thread_time()
    outcome, error_type = "completed", ""
    try:
        yield
    except BaseException as exc:
        outcome, error_type = "failed", type(exc).__name__
        raise
    finally:
        phase = state["phases"].setdefault(name, {"calls": 0, "elapsed_ms": 0.0, "thread_cpu_ms": 0.0})
        phase["calls"] += 1
        phase["elapsed_ms"] = round(phase["elapsed_ms"] + (time.perf_counter() - started) * 1000, 3)
        phase["thread_cpu_ms"] = round(phase["thread_cpu_ms"] + (time.thread_time() - cpu) * 1000, 3)
        if name in state["reported_phases"]:
            state["progress_suppressed"] += 1
        else:
            state["reported_phases"].add(name)
            _progress(state, "phase_completed", phase=name, outcome=outcome,
                      error_type=error_type, phase_times_are_inclusive=True, **phase)


def report_delivery_phase(name: str):
    def decorate(function):
        @wraps(function)
        def observed(*args, **kwargs):
            with report_delivery_phase_scope(name):
                return function(*args, **kwargs)
        return observed
    return decorate
