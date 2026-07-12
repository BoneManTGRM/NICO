from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request

from nico.admin_security import require_admin_write
from nico.operational_observability import build_operational_observability

OPERATIONAL_ALERT_SCHEMA = "nico.operational_alert.v1"
OPERATIONAL_ALERTS_SCHEMA = "nico.operational_alerts.v1"
OPERATIONS_ALERT_ROUTES = {("GET", "/operations/alerts")}
REQUIRED_OPERATION_ALERT_ROUTE = "GET /operations/alerts"

FAILURE_RATE_P2 = 0.05
FAILURE_RATE_P1 = 0.20
TIMEOUT_RATE_P2 = 0.02
TIMEOUT_RATE_P1 = 0.10
MIN_RATE_SAMPLE = 20
QUEUE_AGE_P2_SECONDS = 900.0
QUEUE_AGE_P1_SECONDS = 3600.0
SCANNER_QUEUE_P2 = 5
SCANNER_QUEUE_P1 = 20

SEVERITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "info": 4}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0 or int(number) != number:
        return None
    return int(number)


def _sha(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if _SHA_RE.fullmatch(text) else ""


def _alert(
    *,
    code: str,
    title: str,
    severity: str,
    category: str,
    observed: Any,
    threshold: Any,
    evidence: dict[str, Any],
    operator_action: str,
    evidence_status: str = "available",
) -> dict[str, Any]:
    identity = {
        "code": code,
        "severity": severity,
        "category": category,
        "observed": observed,
        "threshold": threshold,
        "evidence_status": evidence_status,
    }
    return {
        "artifact_schema": OPERATIONAL_ALERT_SCHEMA,
        "alert_id": f"alert_{_canonical_hash(identity)[:20]}",
        "code": code,
        "title": title,
        "severity": severity,
        "category": category,
        "status": "active",
        "evidence_status": evidence_status,
        "observed": observed,
        "threshold": threshold,
        "evidence": evidence,
        "operator_action": operator_action,
        "auto_remediation_eligible": False,
        "destructive_action_allowed": False,
        "client_delivery_allowed": False,
    }


def evaluate_operational_alerts(
    observability: dict[str, Any],
    *,
    frontend_commit: str = "",
) -> dict[str, Any]:
    payload = _dict(observability)
    alerts: list[dict[str, Any]] = []

    request_metrics = _dict(payload.get("request_metrics"))
    workloads = _dict(payload.get("workloads"))
    assessment_runs = _dict(workloads.get("assessment_runs"))
    scanner_runs = _dict(workloads.get("scanner_runs"))
    event_pipeline = _dict(payload.get("event_pipeline"))
    storage = _dict(payload.get("storage"))
    deployment = _dict(payload.get("deployment"))
    readiness = _dict(payload.get("semantic_readiness"))

    severity_counts = _dict(request_metrics.get("severity_counts"))
    p0_count = _integer(severity_counts.get("p0"))
    p1_count = _integer(severity_counts.get("p1"))
    if p0_count is None or p1_count is None:
        alerts.append(
            _alert(
                code="incident_severity_counts_unavailable",
                title="Incident severity counts are unavailable",
                severity="p2",
                category="incident",
                observed={"p0": severity_counts.get("p0"), "p1": severity_counts.get("p1")},
                threshold={"p0": 0, "p1": 0},
                evidence={"request_metrics_present": bool(request_metrics), "severity_counts_present": bool(severity_counts)},
                operator_action="Restore the operational event aggregation path before relying on incident state.",
                evidence_status="unavailable",
            )
        )
    else:
        if p0_count > 0:
            alerts.append(
                _alert(
                    code="p0_events_active",
                    title="P0 operational events require immediate containment",
                    severity="p0",
                    category="incident",
                    observed=p0_count,
                    threshold=0,
                    evidence={"p0_event_count": p0_count},
                    operator_action="Stop affected writes or delivery, preserve evidence, and invoke the P0 incident runbook immediately.",
                )
            )
        if p1_count > 0:
            alerts.append(
                _alert(
                    code="p1_events_active",
                    title="P1 operational events require immediate operator response",
                    severity="p1",
                    category="incident",
                    observed=p1_count,
                    threshold=0,
                    evidence={"p1_event_count": p1_count},
                    operator_action="Assign an operator, inspect correlated events, and block trusted work if integrity is uncertain.",
                )
            )

    request_count = _integer(request_metrics.get("request_count"))
    failure_rate = _number(request_metrics.get("failure_rate"))
    timeout_rate = _number(request_metrics.get("timeout_rate"))
    if request_count is None or failure_rate is None or timeout_rate is None:
        alerts.append(
            _alert(
                code="request_reliability_metrics_unavailable",
                title="Request reliability metrics are unavailable",
                severity="p2",
                category="reliability",
                observed={
                    "request_count": request_metrics.get("request_count"),
                    "failure_rate": request_metrics.get("failure_rate"),
                    "timeout_rate": request_metrics.get("timeout_rate"),
                },
                threshold={"minimum_sample": MIN_RATE_SAMPLE},
                evidence={"request_metrics_present": bool(request_metrics)},
                operator_action="Restore request event collection and metric aggregation before declaring production healthy.",
                evidence_status="unavailable",
            )
        )
    elif request_count >= MIN_RATE_SAMPLE:
        if failure_rate >= FAILURE_RATE_P2:
            severity = "p1" if failure_rate >= FAILURE_RATE_P1 else "p2"
            alerts.append(
                _alert(
                    code="http_failure_rate_elevated",
                    title="HTTP server failure rate exceeds the operating threshold",
                    severity=severity,
                    category="reliability",
                    observed=round(failure_rate, 6),
                    threshold={"p2": FAILURE_RATE_P2, "p1": FAILURE_RATE_P1, "minimum_sample": MIN_RATE_SAMPLE},
                    evidence={
                        "request_count": request_count,
                        "failure_count": request_metrics.get("failure_count"),
                    },
                    operator_action="Filter recent P1/P2 events by correlation ID, identify the failing route, and contain the affected workflow.",
                )
            )
        if timeout_rate >= TIMEOUT_RATE_P2:
            severity = "p1" if timeout_rate >= TIMEOUT_RATE_P1 else "p2"
            alerts.append(
                _alert(
                    code="http_timeout_rate_elevated",
                    title="HTTP timeout rate exceeds the operating threshold",
                    severity=severity,
                    category="reliability",
                    observed=round(timeout_rate, 6),
                    threshold={"p2": TIMEOUT_RATE_P2, "p1": TIMEOUT_RATE_P1, "minimum_sample": MIN_RATE_SAMPLE},
                    evidence={
                        "request_count": request_count,
                        "timeout_count": request_metrics.get("timeout_count"),
                    },
                    operator_action="Inspect queue pressure and slow routes, reduce intake when needed, and verify scanner/provider latency.",
                )
            )

    queue_age = _number(assessment_runs.get("oldest_queue_age_seconds"))
    if queue_age is None:
        alerts.append(
            _alert(
                code="assessment_queue_age_unavailable",
                title="Assessment queue age is unavailable",
                severity="p2",
                category="capacity",
                observed=assessment_runs.get("oldest_queue_age_seconds"),
                threshold={"p2_seconds": QUEUE_AGE_P2_SECONDS, "p1_seconds": QUEUE_AGE_P1_SECONDS},
                evidence={"assessment_run_metrics_present": bool(assessment_runs)},
                operator_action="Restore assessment workload metrics before accepting additional production intake.",
                evidence_status="unavailable",
            )
        )
    elif queue_age >= QUEUE_AGE_P2_SECONDS:
        severity = "p1" if queue_age >= QUEUE_AGE_P1_SECONDS else "p2"
        alerts.append(
            _alert(
                code="assessment_queue_age_elevated",
                title="Assessment queue age exceeds the operating threshold",
                severity=severity,
                category="capacity",
                observed=round(queue_age, 3),
                threshold={"p2_seconds": QUEUE_AGE_P2_SECONDS, "p1_seconds": QUEUE_AGE_P1_SECONDS},
                evidence={
                    "queued": assessment_runs.get("queued"),
                    "active": assessment_runs.get("active"),
                    "total": assessment_runs.get("total"),
                },
                operator_action="Reduce intake, inspect stalled jobs, and recover the oldest queued run without deleting evidence.",
            )
        )

    scanner_queued = _integer(scanner_runs.get("queued"))
    if scanner_queued is None:
        alerts.append(
            _alert(
                code="scanner_queue_metrics_unavailable",
                title="Scanner queue metrics are unavailable",
                severity="p2",
                category="capacity",
                observed=scanner_runs.get("queued"),
                threshold={"p2": SCANNER_QUEUE_P2, "p1": SCANNER_QUEUE_P1},
                evidence={"scanner_run_metrics_present": bool(scanner_runs)},
                operator_action="Restore scanner workload metrics and verify that queued work is being persisted.",
                evidence_status="unavailable",
            )
        )
    elif scanner_queued >= SCANNER_QUEUE_P2:
        severity = "p1" if scanner_queued >= SCANNER_QUEUE_P1 else "p2"
        alerts.append(
            _alert(
                code="scanner_queue_elevated",
                title="Scanner queue depth exceeds the operating threshold",
                severity=severity,
                category="capacity",
                observed=scanner_queued,
                threshold={"p2": SCANNER_QUEUE_P2, "p1": SCANNER_QUEUE_P1},
                evidence={
                    "active": scanner_runs.get("active"),
                    "total": scanner_runs.get("total"),
                    "oldest_queue_age_seconds": scanner_runs.get("oldest_queue_age_seconds"),
                },
                operator_action="Reduce new scanner intake and investigate stalled or unavailable scanner workers.",
            )
        )

    write_failures = _integer(event_pipeline.get("write_failures"))
    read_failures = _integer(event_pipeline.get("read_failures"))
    if write_failures is None or read_failures is None:
        alerts.append(
            _alert(
                code="event_pipeline_metrics_unavailable",
                title="Operational event pipeline metrics are unavailable",
                severity="p2",
                category="telemetry",
                observed={"write_failures": event_pipeline.get("write_failures"), "read_failures": event_pipeline.get("read_failures")},
                threshold={"write_failures": 0, "read_failures": 0},
                evidence={"event_pipeline_present": bool(event_pipeline)},
                operator_action="Restore event pipeline diagnostics before trusting incident and reliability summaries.",
                evidence_status="unavailable",
            )
        )
    else:
        if write_failures > 0:
            alerts.append(
                _alert(
                    code="event_pipeline_write_failures",
                    title="Operational event writes are failing",
                    severity="p1",
                    category="telemetry",
                    observed=write_failures,
                    threshold=0,
                    evidence={"pipeline_status": event_pipeline.get("status"), "durability": event_pipeline.get("durability")},
                    operator_action="Inspect durable storage and block claims that depend on complete incident telemetry until writes recover.",
                )
            )
        if read_failures > 0:
            alerts.append(
                _alert(
                    code="event_pipeline_read_failures",
                    title="Operational event reads are failing",
                    severity="p2",
                    category="telemetry",
                    observed=read_failures,
                    threshold=0,
                    evidence={"pipeline_status": event_pipeline.get("status"), "durability": event_pipeline.get("durability")},
                    operator_action="Inspect the audit-log read path and use provider logs only as temporary supporting evidence.",
                )
            )

    persistence_available = storage.get("persistence_available")
    if persistence_available is not True:
        alerts.append(
            _alert(
                code="durable_storage_unavailable",
                title="Durable hosted storage is unavailable",
                severity="p1",
                category="storage",
                observed={
                    "persistence_available": persistence_available,
                    "adapter": storage.get("adapter") or "unknown",
                    "database_configured": storage.get("database_configured"),
                },
                threshold={"persistence_available": True},
                evidence={"storage_present": bool(storage)},
                operator_action="Restore verified Postgres persistence before accepting trusted assessments, approvals, or delivery work.",
                evidence_status="available" if storage else "unavailable",
            )
        )

    readiness_status = str(readiness.get("status") or "").strip().lower()
    readiness_ready = readiness.get("operational_ready") is True
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    if readiness_status != "ready" or not readiness_ready or blockers:
        alerts.append(
            _alert(
                code="semantic_readiness_blocked",
                title="Semantic production readiness is not ready",
                severity="p1",
                category="readiness",
                observed={"status": readiness_status or "unavailable", "operational_ready": readiness.get("operational_ready")},
                threshold={"status": "ready", "operational_ready": True, "blockers": []},
                evidence={"blockers": blockers[:40], "warnings": (readiness.get("warnings") or [])[:40] if isinstance(readiness.get("warnings"), list) else []},
                operator_action="Resolve every required readiness blocker and rerun the production release gate before trusted production work.",
                evidence_status="available" if readiness else "unavailable",
            )
        )

    backend_commit = _sha(deployment.get("deployed_commit"))
    normalized_frontend = _sha(frontend_commit)
    if not backend_commit:
        alerts.append(
            _alert(
                code="backend_release_identity_unavailable",
                title="Backend release identity is unavailable",
                severity="p1",
                category="deployment",
                observed=deployment.get("deployed_commit") or "unavailable",
                threshold="40-character deployed commit SHA",
                evidence={"deployment_status": deployment.get("status"), "matches_expected_build": deployment.get("matches_expected_build")},
                operator_action="Expose and verify the Railway runtime commit identity before trusting the deployment.",
                evidence_status="unavailable",
            )
        )
    if not normalized_frontend:
        alerts.append(
            _alert(
                code="frontend_release_identity_unavailable",
                title="Frontend release identity is unavailable",
                severity="p1",
                category="deployment",
                observed=frontend_commit or "unavailable",
                threshold="40-character deployed commit SHA",
                evidence={"frontend_commit_supplied": bool(frontend_commit)},
                operator_action="Verify the Vercel `/api/deployment` response and redeploy with commit identity enabled.",
                evidence_status="unavailable",
            )
        )
    if backend_commit and normalized_frontend and backend_commit != normalized_frontend:
        alerts.append(
            _alert(
                code="frontend_backend_release_mismatch",
                title="Frontend and backend are running different releases",
                severity="p1",
                category="deployment",
                observed={"frontend_commit": normalized_frontend, "backend_commit": backend_commit},
                threshold="identical commit SHA",
                evidence={"backend_matches_expected_build": deployment.get("matches_expected_build")},
                operator_action="Stop trusted production work, deploy both components from the same current main SHA, and rerun the release gate.",
            )
        )

    alerts.sort(key=lambda item: (SEVERITY_ORDER.get(str(item.get("severity")), 99), str(item.get("code"))))
    highest = alerts[0]["severity"] if alerts else "info"
    stable_source = {
        "observability": payload,
        "frontend_commit": normalized_frontend or str(frontend_commit or ""),
    }
    result = {
        "artifact_schema": OPERATIONAL_ALERTS_SCHEMA,
        "status": "alerting" if alerts else "clear",
        "highest_severity": highest,
        "alert_count": len(alerts),
        "alerts": alerts,
        "thresholds": {
            "minimum_rate_sample": MIN_RATE_SAMPLE,
            "failure_rate": {"p2": FAILURE_RATE_P2, "p1": FAILURE_RATE_P1},
            "timeout_rate": {"p2": TIMEOUT_RATE_P2, "p1": TIMEOUT_RATE_P1},
            "queue_age_seconds": {"p2": QUEUE_AGE_P2_SECONDS, "p1": QUEUE_AGE_P1_SECONDS},
            "scanner_queue": {"p2": SCANNER_QUEUE_P2, "p1": SCANNER_QUEUE_P1},
        },
        "source_observability_sha256": _canonical_hash(stable_source),
        "alert_set_sha256": _canonical_hash(alerts),
        "human_review_required": True,
        "automatic_remediation_performed": False,
        "client_delivery_allowed": False,
        "guardrail": "Alerts are deterministic operator guidance only. They do not authorize rollback, deployment, deletion, credential rotation, service shutdown, score changes, or client delivery.",
    }
    return result


def _require_operator(token: str) -> None:
    allowed, status = require_admin_write(token)
    if allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "status": "blocked",
            "code": "operator_authentication_required",
            "message": "Operator authentication is required to access operational alerts.",
            "admin_write": status,
        },
    )


def operational_alerts_response(
    request: Request,
    frontend_commit: str = Query(default="", max_length=40),
    event_window: int = Query(default=500, ge=1, le=2000),
    x_nico_admin_token: str = Header(default=""),
) -> dict[str, Any]:
    _require_operator(x_nico_admin_token)
    if frontend_commit and not _sha(frontend_commit):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "blocked",
                "code": "invalid_frontend_commit",
                "message": "frontend_commit must be a full 40-character hexadecimal commit SHA.",
            },
        )
    observability = build_operational_observability(request.app, event_window=event_window)
    return evaluate_operational_alerts(observability, frontend_commit=frontend_commit)


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in target.routes:
        path = str(getattr(route, "path", ""))
        for method in getattr(route, "methods", set()) or set():
            pairs.add((str(method).upper(), path))
    return pairs


def install_operational_alert_routes(target: FastAPI) -> dict[str, Any]:
    existing = _route_pairs(target)
    present = existing & OPERATIONS_ALERT_ROUTES
    if present and present != OPERATIONS_ALERT_ROUTES:
        raise RuntimeError(f"Partial operational alert route registration detected; missing={sorted(OPERATIONS_ALERT_ROUTES - present)}")
    if not present:
        target.get("/operations/alerts", tags=["operations"])(operational_alerts_response)
        target.openapi_schema = None

    from nico.operations_readiness import REQUIRED_OPERATION_ROUTES

    REQUIRED_OPERATION_ROUTES.add(REQUIRED_OPERATION_ALERT_ROUTE)
    missing = OPERATIONS_ALERT_ROUTES - _route_pairs(target)
    if missing:
        raise RuntimeError(f"Operational alert route registration incomplete; missing={sorted(missing)}")
    return {
        "installed": True,
        "route_reused": bool(present),
        "routes": sorted(f"{method} {path}" for method, path in OPERATIONS_ALERT_ROUTES),
        "alert_schema": OPERATIONAL_ALERT_SCHEMA,
        "alerts_schema": OPERATIONAL_ALERTS_SCHEMA,
    }


__all__ = [
    "OPERATIONAL_ALERT_SCHEMA",
    "OPERATIONAL_ALERTS_SCHEMA",
    "OPERATIONS_ALERT_ROUTES",
    "REQUIRED_OPERATION_ALERT_ROUTE",
    "FAILURE_RATE_P2",
    "FAILURE_RATE_P1",
    "TIMEOUT_RATE_P2",
    "TIMEOUT_RATE_P1",
    "MIN_RATE_SAMPLE",
    "QUEUE_AGE_P2_SECONDS",
    "QUEUE_AGE_P1_SECONDS",
    "SCANNER_QUEUE_P2",
    "SCANNER_QUEUE_P1",
    "evaluate_operational_alerts",
    "operational_alerts_response",
    "install_operational_alert_routes",
]
