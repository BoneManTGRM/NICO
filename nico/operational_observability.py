from __future__ import annotations

import math
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from nico.admin_security import require_admin_write
from nico.diagnostics import deployment_diagnostics
from nico.operations_readiness import build_operations_readiness
from nico.operations_readiness_api import application_route_inventory
from nico.storage import STORE, utc_now

OPERATIONAL_EVENT_SCHEMA = "nico.operational_event.v1"
OPERATIONAL_EVENTS_RESPONSE_SCHEMA = "nico.operational_events.v1"
OPERATIONAL_OBSERVABILITY_SCHEMA = "nico.operational_observability.v1"
CORRELATION_HEADER = "X-NICO-Correlation-ID"
MAX_EVENT_LIMIT = 500
MAX_SUMMARY_WINDOW = 2000

SEVERITY_DEFINITIONS = {
    "p0": "Confirmed critical integrity, authorization, destructive-action, cross-tenant, or secret-exposure incident requiring immediate shutdown and executive ownership.",
    "p1": "Production outage, unhandled server failure, durable-record corruption, or release-identity failure requiring immediate operator response.",
    "p2": "Degraded service, timeout, provider/scanner unavailability, queue growth, or readiness blocker requiring prompt investigation.",
    "p3": "Isolated client or workflow error with bounded impact and a known recovery path.",
    "info": "Successful or expected operational activity retained for correlation and trend analysis.",
}
VALID_SEVERITIES = frozenset(SEVERITY_DEFINITIONS)
OPERATIONS_OBSERVABILITY_ROUTES = {
    ("GET", "/operations/events"),
    ("GET", "/operations/observability"),
}
REQUIRED_OPERATION_ROUTE_STRINGS = {
    "GET /operations/events",
    "GET /operations/observability",
}

_CORRELATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_OPERATIONAL_ID_RE = re.compile(
    r"\b(?:midrun|fullrun|scan|report|approval|access|receipt|evidence|job|export)_[A-Za-z0-9]{6,64}\b",
    re.IGNORECASE,
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|cookie|token|secret|password|passwd|api[_-]?key|private[_-]?key|credential|session)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\b(?:bearer|basic)\s+\S+", re.IGNORECASE)

_EVENT_WRITE_FAILURES = 0
_EVENT_READ_FAILURES = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    return text[:limit]


def normalize_correlation_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if _CORRELATION_RE.fullmatch(candidate):
        return candidate
    return f"corr_{uuid.uuid4().hex}"


def valid_correlation_id(value: Any) -> bool:
    return bool(_CORRELATION_RE.fullmatch(str(value or "").strip()))


def extract_operational_identifiers(path: Any) -> list[str]:
    value = str(path or "")[:2048]
    seen: set[str] = set()
    identifiers: list[str] = []
    for match in _OPERATIONAL_ID_RE.findall(value):
        normalized = match[:96]
        if normalized in seen:
            continue
        seen.add(normalized)
        identifiers.append(normalized)
        if len(identifiers) >= 8:
            break
    return identifiers


def redact_operational_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if _SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if depth >= 5:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _BEARER_RE.search(value):
            return "[REDACTED]"
        return value[:500]
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for index, raw_key in enumerate(sorted(value, key=lambda item: str(item))):
            if index >= 40:
                output["_truncated"] = True
                break
            normalized_key = _bounded_text(raw_key, 100)
            output[normalized_key] = redact_operational_value(
                value.get(raw_key),
                key=normalized_key,
                depth=depth + 1,
            )
        return output
    if isinstance(value, (list, tuple, set)):
        items = list(value)[:20]
        return [redact_operational_value(item, key=key, depth=depth + 1) for item in items]
    return _bounded_text(value, 240)


def classify_http_severity(status_code: int, *, unhandled_exception: bool = False) -> str:
    if unhandled_exception:
        return "p1"
    if status_code in {408, 429, 502, 503, 504}:
        return "p2"
    if status_code >= 500:
        return "p1"
    if status_code >= 400:
        return "p3"
    return "info"


def classify_http_outcome(status_code: int, *, unhandled_exception: bool = False) -> str:
    if unhandled_exception:
        return "exception"
    if status_code >= 500:
        return "server_error"
    if status_code in {408, 429}:
        return "limited"
    if status_code >= 400:
        return "client_error"
    return "succeeded"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = str(getattr(route, "path", "")).strip()
    return path[:240] if path else "<unmatched>"


def emit_operational_event(
    *,
    correlation_id: str,
    event_name: str,
    severity: str,
    outcome: str,
    metadata: dict[str, Any],
    customer_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    global _EVENT_WRITE_FAILURES
    normalized_severity = severity if severity in VALID_SEVERITIES else "p2"
    event_id = f"event_{uuid.uuid4().hex[:16]}"
    event = {
        "artifact_schema": OPERATIONAL_EVENT_SCHEMA,
        "event_id": event_id,
        "correlation_id": normalize_correlation_id(correlation_id),
        "event_name": _bounded_text(event_name, 120) or "operational.event",
        "severity": normalized_severity,
        "outcome": _bounded_text(outcome, 80) or "unknown",
        "metadata": redact_operational_value(metadata),
        "occurred_at": utc_now(),
    }
    try:
        STORE.audit(
            "operational_event",
            event,
            customer_id=customer_id,
            project_id=project_id,
        )
        return {"stored": True, "event_id": event_id, "event": event}
    except Exception:
        _EVENT_WRITE_FAILURES += 1
        return {"stored": False, "event_id": event_id, "event": event}


def event_pipeline_status() -> dict[str, Any]:
    storage = STORE.status()
    return {
        "status": "ok" if _EVENT_WRITE_FAILURES == 0 and _EVENT_READ_FAILURES == 0 else "degraded",
        "write_failures": _EVENT_WRITE_FAILURES,
        "read_failures": _EVENT_READ_FAILURES,
        "storage_adapter": storage.get("adapter") or "unknown",
        "persistence_available": bool(storage.get("persistence_available")),
        "durability": "durable" if storage.get("persistence_available") else "process_memory_only",
    }


def _event_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    if str(record.get("action") or "") != "operational_event":
        return None
    nested = record.get("payload")
    if isinstance(nested, dict):
        event = dict(nested)
        event.setdefault("occurred_at", record.get("created_at"))
    else:
        event = dict(record)
    if event.get("artifact_schema") != OPERATIONAL_EVENT_SCHEMA:
        return None
    return redact_operational_value(event)


def _read_recent_audit_records(limit: int) -> list[dict[str, Any]]:
    global _EVENT_READ_FAILURES
    bounded = max(1, min(int(limit), MAX_SUMMARY_WINDOW))
    adapter = getattr(STORE, "adapter", None)
    try:
        query = getattr(adapter, "_query", None)
        normalize = getattr(adapter, "_normalize_jsonb", None)
        if callable(query) and callable(normalize):
            rows = query(
                "SELECT * FROM audit_log WHERE action=%s ORDER BY created_at DESC LIMIT %s",
                ("operational_event", bounded),
            )
            return [normalize("audit_log", row) for row in rows]
        records = [
            item
            for item in STORE.list("audit_log")
            if str(item.get("action") or "") == "operational_event"
        ]
        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records[:bounded]
    except Exception:
        _EVENT_READ_FAILURES += 1
        return []


def recent_operational_events(
    *,
    limit: int = 100,
    severity: str | None = None,
    correlation_id: str | None = None,
) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), MAX_EVENT_LIMIT))
    normalized_severity = str(severity or "").lower().strip()
    normalized_correlation = str(correlation_id or "").strip()
    records = _read_recent_audit_records(MAX_SUMMARY_WINDOW if severity or correlation_id else bounded)
    events: list[dict[str, Any]] = []
    for record in records:
        event = _event_from_record(record)
        if not event:
            continue
        if normalized_severity and event.get("severity") != normalized_severity:
            continue
        if normalized_correlation and event.get("correlation_id") != normalized_correlation:
            continue
        events.append(event)
        if len(events) >= bounded:
            break
    return events


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duration_seconds(start: Any, end: Any) -> float | None:
    started = _parse_time(start)
    ended = _parse_time(end)
    if not started or not ended or ended < started:
        return None
    return round((ended - started).total_seconds(), 3)


def _percentile(values: list[float], percentile: float) -> float | None:
    clean = sorted(value for value in values if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0)
    if not clean:
        return None
    if len(clean) == 1:
        return round(float(clean[0]), 3)
    rank = (len(clean) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(float(clean[lower]), 3)
    weighted = clean[lower] * (upper - rank) + clean[upper] * (rank - lower)
    return round(float(weighted), 3)


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "unknown").lower() for item in items)
    return dict(sorted(counter.items()))


def _queue_summary(items: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    queued_states = {"queued", "pending", "created", "accepted"}
    active_states = queued_states | {"running", "in_progress", "started", "processing"}
    queued = [item for item in items if str(item.get("status") or "").lower() in queued_states]
    active = [item for item in items if str(item.get("status") or "").lower() in active_states]
    ages = []
    for item in queued:
        created = _parse_time(item.get("created_at"))
        if created and created <= now:
            ages.append((now - created).total_seconds())
    return {
        "total": len(items),
        "active": len(active),
        "queued": len(queued),
        "oldest_queue_age_seconds": round(max(ages), 3) if ages else 0.0,
        "status_counts": _status_counts(items),
    }


def build_operational_observability(app: FastAPI, *, event_window: int = 500) -> dict[str, Any]:
    bounded_window = max(1, min(int(event_window), MAX_SUMMARY_WINDOW))
    events = recent_operational_events(limit=bounded_window)
    request_events = [event for event in events if event.get("event_name", "").startswith("http.request.")]
    durations = [
        float((event.get("metadata") or {}).get("duration_ms"))
        for event in request_events
        if isinstance((event.get("metadata") or {}).get("duration_ms"), (int, float))
    ]
    failures = [
        event
        for event in request_events
        if event.get("outcome") in {"exception", "server_error"}
    ]
    timeouts = [
        event
        for event in request_events
        if int((event.get("metadata") or {}).get("status_code") or 0) in {408, 504}
    ]
    severity_counts = Counter(str(event.get("severity") or "unknown") for event in events)

    assessment_runs = STORE.list("assessment_runs")
    scanner_runs = STORE.list("scanner_runs")
    reports = STORE.list("reports")
    now = _now()

    scanner_durations = [
        duration
        for item in scanner_runs
        for duration in [_duration_seconds(item.get("created_at"), item.get("updated_at"))]
        if duration is not None and str(item.get("status") or "").lower() not in {"queued", "pending", "running", "in_progress"}
    ]
    run_started = {
        str(item.get("run_id") or item.get("id") or ""): item.get("created_at")
        for item in assessment_runs
        if item.get("run_id") or item.get("id")
    }
    report_durations = [
        duration
        for item in reports
        for duration in [_duration_seconds(run_started.get(str(item.get("run_id") or "")), item.get("created_at"))]
        if duration is not None
    ]

    storage = STORE.status()
    deployment = deployment_diagnostics()
    readiness = build_operations_readiness(application_route_inventory(app))
    pipeline = event_pipeline_status()
    failure_rate = round(len(failures) / len(request_events), 6) if request_events else 0.0
    timeout_rate = round(len(timeouts) / len(request_events), 6) if request_events else 0.0
    status = "ok"
    if pipeline.get("status") != "ok" or readiness.get("status") != "ready" or not storage.get("persistence_available"):
        status = "degraded"

    return {
        "artifact_schema": OPERATIONAL_OBSERVABILITY_SCHEMA,
        "status": status,
        "generated_at": utc_now(),
        "event_window": bounded_window,
        "events_observed": len(events),
        "request_metrics": {
            "request_count": len(request_events),
            "failure_count": len(failures),
            "failure_rate": failure_rate,
            "timeout_count": len(timeouts),
            "timeout_rate": timeout_rate,
            "latency_ms": {
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
                "max": round(max(durations), 3) if durations else None,
            },
            "severity_counts": dict(sorted(severity_counts.items())),
        },
        "workloads": {
            "assessment_runs": _queue_summary(assessment_runs, now),
            "scanner_runs": _queue_summary(scanner_runs, now),
            "scanner_duration_seconds": {
                "sample_count": len(scanner_durations),
                "p50": _percentile(scanner_durations, 0.50),
                "p95": _percentile(scanner_durations, 0.95),
                "max": round(max(scanner_durations), 3) if scanner_durations else None,
            },
            "report_generation_seconds": {
                "sample_count": len(report_durations),
                "p50": _percentile(report_durations, 0.50),
                "p95": _percentile(report_durations, 0.95),
                "max": round(max(report_durations), 3) if report_durations else None,
            },
        },
        "event_pipeline": pipeline,
        "storage": {
            "adapter": storage.get("adapter") or "unknown",
            "persistence_available": bool(storage.get("persistence_available")),
            "database_configured": bool(storage.get("database_url_configured")),
        },
        "deployment": {
            "status": deployment.get("status") or "unknown",
            "deployed_commit": deployment.get("deployed_commit") or "unavailable",
            "matches_expected_build": bool(deployment.get("matches_expected_build")),
            "build_marker": deployment.get("build_marker") or "unavailable",
        },
        "semantic_readiness": {
            "status": readiness.get("status") or "blocked",
            "operational_ready": readiness.get("operational_ready") is True,
            "blockers": list(readiness.get("blockers") or []),
            "warnings": list(readiness.get("warnings") or []),
        },
        "severity_definitions": SEVERITY_DEFINITIONS,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "Operational telemetry contains bounded metadata only. It does not include request bodies, credentials, query values, raw exception messages, or client-delivery authority.",
    }


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required to access operational telemetry.",
            "admin_write": status,
        },
    )


def operational_events_response(
    limit: int = Query(default=100, ge=1, le=MAX_EVENT_LIMIT),
    severity: str | None = Query(default=None, max_length=16),
    correlation_id: str | None = Query(default=None, max_length=128),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    normalized_severity = str(severity or "").lower().strip()
    if normalized_severity and normalized_severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail={"status": "blocked", "code": "invalid_severity"})
    normalized_correlation = str(correlation_id or "").strip()
    if normalized_correlation and not valid_correlation_id(normalized_correlation):
        raise HTTPException(status_code=400, detail={"status": "blocked", "code": "invalid_correlation_id"})
    events = recent_operational_events(
        limit=limit,
        severity=normalized_severity or None,
        correlation_id=normalized_correlation or None,
    )
    return {
        "artifact_schema": OPERATIONAL_EVENTS_RESPONSE_SCHEMA,
        "status": "ok",
        "count": len(events),
        "limit": limit,
        "filters": {
            "severity": normalized_severity or None,
            "correlation_id": normalized_correlation or None,
        },
        "events": events,
        "event_pipeline": event_pipeline_status(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def operational_observability_response(
    request: Request,
    event_window: int = Query(default=500, ge=1, le=MAX_SUMMARY_WINDOW),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    return build_operational_observability(request.app, event_window=event_window)


async def operational_observability_middleware(
    request: Request,
    call_next: Callable[[Request], Any],
) -> Response:
    correlation_id = normalize_correlation_id(request.headers.get(CORRELATION_HEADER))
    request.state.nico_correlation_id = correlation_id
    started = time.perf_counter()
    identifiers = extract_operational_identifiers(request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        emit_operational_event(
            correlation_id=correlation_id,
            event_name="http.request.failed",
            severity="p1",
            outcome="exception",
            metadata={
                "method": request.method.upper(),
                "route": _route_template(request),
                "status_code": 500,
                "duration_ms": duration_ms,
                "identifiers": identifiers,
                "error_class": type(exc).__name__[:120],
                "unhandled_exception": True,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "internal_server_error",
                "message": "The request failed inside the production service.",
                "correlation_id": correlation_id,
            },
            headers={
                CORRELATION_HEADER: correlation_id,
                "Cache-Control": "no-store, private, max-age=0",
                "X-Content-Type-Options": "nosniff",
            },
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    status_code = int(getattr(response, "status_code", 500) or 500)
    response.headers[CORRELATION_HEADER] = correlation_id
    emit_operational_event(
        correlation_id=correlation_id,
        event_name="http.request.completed",
        severity=classify_http_severity(status_code),
        outcome=classify_http_outcome(status_code),
        metadata={
            "method": request.method.upper(),
            "route": _route_template(request),
            "status_code": status_code,
            "duration_ms": duration_ms,
            "identifiers": identifiers,
            "timeout": status_code in {408, 504},
        },
    )
    return response


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def install_operational_observability(target: FastAPI) -> dict[str, Any]:
    existing = _route_pairs(target)
    present = existing & OPERATIONS_OBSERVABILITY_ROUTES
    if present and present != OPERATIONS_OBSERVABILITY_ROUTES:
        raise RuntimeError(
            f"Partial operational observability route registration detected; missing={sorted(OPERATIONS_OBSERVABILITY_ROUTES - present)}"
        )
    if not present:
        target.get("/operations/events", tags=["operations"])(operational_events_response)
        target.get("/operations/observability", tags=["operations"])(operational_observability_response)
        target.openapi_schema = None

    middleware_reused = bool(getattr(target.state, "nico_operational_observability_middleware", False))
    if not middleware_reused:
        target.middleware("http")(operational_observability_middleware)
        target.state.nico_operational_observability_middleware = True

    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.update(REQUIRED_OPERATION_ROUTE_STRINGS)
    missing = OPERATIONS_OBSERVABILITY_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Operational observability route registration incomplete; missing={sorted(missing)}")
    return {
        "installed": True,
        "middleware_reused": middleware_reused,
        "routes": sorted(f"{method} {path}" for method, path in OPERATIONS_OBSERVABILITY_ROUTES),
        "event_schema": OPERATIONAL_EVENT_SCHEMA,
        "observability_schema": OPERATIONAL_OBSERVABILITY_SCHEMA,
    }


__all__ = [
    "OPERATIONAL_EVENT_SCHEMA",
    "OPERATIONAL_EVENTS_RESPONSE_SCHEMA",
    "OPERATIONAL_OBSERVABILITY_SCHEMA",
    "CORRELATION_HEADER",
    "MAX_EVENT_LIMIT",
    "MAX_SUMMARY_WINDOW",
    "SEVERITY_DEFINITIONS",
    "VALID_SEVERITIES",
    "OPERATIONS_OBSERVABILITY_ROUTES",
    "REQUIRED_OPERATION_ROUTE_STRINGS",
    "normalize_correlation_id",
    "valid_correlation_id",
    "extract_operational_identifiers",
    "redact_operational_value",
    "classify_http_severity",
    "classify_http_outcome",
    "emit_operational_event",
    "event_pipeline_status",
    "recent_operational_events",
    "build_operational_observability",
    "operational_events_response",
    "operational_observability_response",
    "operational_observability_middleware",
    "install_operational_observability",
]
