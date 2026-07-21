from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol

from fastapi import FastAPI, HTTPException, Request

from nico.notification_delivery import (
    NotificationDispatcher,
    NotificationMessage,
    NotificationStore,
    build_notification,
)
from nico.post_release_observability import (
    MetricPoint,
    OperationalThresholds,
    alert_conditions,
    build_health_snapshot,
)
from nico.provider_credentials import SecretValue


VERSION = "nico.operational_api.v1"
OPERATIONAL_ROUTES = {
    ("GET", "/internal/operational-health"),
    ("POST", "/internal/notifications/enqueue"),
    ("POST", "/internal/notifications/dispatch"),
}


class OperationalAuthorizer(Protocol):
    def __call__(self, request: Request) -> bool:
        ...


@dataclass(frozen=True)
class HeaderOperationalAuthorizer:
    secret: SecretValue
    header_name: str = "X-NICO-Operational-Token"

    def __call__(self, request: Request) -> bool:
        presented = str(request.headers.get(self.header_name) or "")
        return bool(presented) and secrets.compare_digest(presented, self.secret.reveal())


@dataclass
class OperationalRuntime:
    authorizer: OperationalAuthorizer
    exact_sha_provider: Callable[[], str]
    metric_provider: Callable[[], Iterable[MetricPoint]]
    log_sample_provider: Callable[[], Iterable[str]]
    forbidden_log_value_provider: Callable[[], Iterable[str]]
    notification_store: NotificationStore
    notification_dispatcher: NotificationDispatcher
    thresholds: OperationalThresholds = OperationalThresholds()


def _runtime(request: Request) -> OperationalRuntime:
    runtime = getattr(request.app.state, "operational_runtime", None)
    if not isinstance(runtime, OperationalRuntime):
        raise HTTPException(status_code=503, detail="operational_runtime_not_configured")
    if not runtime.authorizer(request):
        raise HTTPException(status_code=403, detail="operational_authorization_required")
    return runtime


async def _payload(request: Request) -> Mapping[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="request_body_must_be_object") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=422, detail="request_body_must_be_object")
    return payload


def _message(value: NotificationMessage) -> dict[str, Any]:
    payload = asdict(value)
    payload["human_review_required"] = True
    payload["client_delivery_allowed"] = False
    return payload


def _route_count(app: FastAPI, method: str, path: str) -> int:
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def register_operational_routes(
    app: FastAPI,
    *,
    runtime: OperationalRuntime | None = None,
) -> None:
    existing = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    overlap = OPERATIONAL_ROUTES.intersection(existing)
    if overlap:
        if overlap == OPERATIONAL_ROUTES:
            if runtime is not None:
                app.state.operational_runtime = runtime
            return
        raise RuntimeError("operational_partial_route_group_detected")
    if runtime is not None:
        runtime.notification_store.ensure_schema()
        app.state.operational_runtime = runtime

    @app.get("/internal/operational-health")
    async def operational_health(request: Request) -> dict[str, Any]:
        runtime_value = _runtime(request)
        snapshot = build_health_snapshot(
            exact_sha=str(runtime_value.exact_sha_provider() or ""),
            points=tuple(runtime_value.metric_provider()),
            log_samples=tuple(runtime_value.log_sample_provider()),
            forbidden_log_values=tuple(runtime_value.forbidden_log_value_provider()),
            thresholds=runtime_value.thresholds,
        )
        return {
            "artifact_schema": VERSION,
            "operation": "operational_health",
            "snapshot": asdict(snapshot),
            "alerts": list(alert_conditions(snapshot)),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @app.post("/internal/notifications/enqueue")
    async def enqueue_notification(request: Request) -> dict[str, Any]:
        runtime_value = _runtime(request)
        payload = await _payload(request)
        allowed = {
            "dedup_key",
            "destination",
            "severity",
            "subject",
            "body",
            "exact_sha",
            "evidence_fingerprint",
            "created_at",
        }
        if set(payload) - allowed:
            raise HTTPException(status_code=422, detail="notification_enqueue_fields_invalid")
        try:
            message = build_notification(
                dedup_key=str(payload.get("dedup_key") or ""),
                destination=str(payload.get("destination") or ""),
                severity=str(payload.get("severity") or ""),
                subject=str(payload.get("subject") or ""),
                body=str(payload.get("body") or ""),
                exact_sha=str(payload.get("exact_sha") or ""),
                evidence_fingerprint=str(payload.get("evidence_fingerprint") or ""),
                created_at=str(payload.get("created_at") or ""),
            )
            stored = runtime_value.notification_store.enqueue(message)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "notification_enqueue_failed") from exc
        return {
            "artifact_schema": VERSION,
            "operation": "notification_enqueued",
            "notification": _message(stored),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @app.post("/internal/notifications/dispatch")
    async def dispatch_notifications(request: Request) -> dict[str, Any]:
        runtime_value = _runtime(request)
        payload = await _payload(request)
        allowed = {"limit"}
        if set(payload) - allowed:
            raise HTTPException(status_code=422, detail="notification_dispatch_fields_invalid")
        limit = int(payload.get("limit") or 100)
        delivered = runtime_value.notification_dispatcher.run_due(limit=limit)
        return {
            "artifact_schema": VERSION,
            "operation": "notifications_dispatched",
            "notifications": [_message(item) for item in delivered],
            "notification_count": len(delivered),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }


__all__ = [
    "HeaderOperationalAuthorizer",
    "OPERATIONAL_ROUTES",
    "OperationalAuthorizer",
    "OperationalRuntime",
    "VERSION",
    "register_operational_routes",
]
