from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from nico.provider_credentials import SecretValue
from nico.provider_live_clients import ProviderClientError
from nico.provider_neutral_contract import ProviderKind, normalize_provider
from nico.provider_sync_service import (
    ProviderCollector,
    ProviderSyncConflict,
    ProviderSyncError,
    ProviderSyncMissing,
    ProviderSyncService,
)
from nico.provider_webhook_verification import ReplayGuard, WebhookVerificationError


VERSION = "nico.provider_sync_api.v1"
PROVIDER_SYNC_ROUTES = {
    ("GET", "/providers/{provider}/repositories/{repository_id:path}/sync"),
    ("POST", "/providers/{provider}/repositories/{repository_id:path}/collect"),
    ("POST", "/providers/{provider}/repositories/{repository_id:path}/webhook"),
}


@dataclass
class ProviderSyncRuntime:
    service: ProviderSyncService
    collectors: dict[ProviderKind, ProviderCollector] = field(default_factory=dict)
    webhook_secrets: dict[ProviderKind, SecretValue] = field(default_factory=dict)
    replay_guards: dict[ProviderKind, ReplayGuard] = field(default_factory=dict)

    def collector(self, provider: ProviderKind) -> ProviderCollector:
        collector = self.collectors.get(provider)
        if collector is None:
            raise ProviderSyncError("provider_collector_not_configured")
        if collector.provider is not provider:
            raise ProviderSyncError("provider_collector_kind_mismatch")
        return collector

    def webhook_secret(self, provider: ProviderKind) -> SecretValue:
        secret = self.webhook_secrets.get(provider)
        if secret is None:
            raise ProviderSyncError("provider_webhook_secret_not_configured")
        return secret

    def replay_guard(self, provider: ProviderKind) -> ReplayGuard:
        return self.replay_guards.setdefault(provider, ReplayGuard())


def _runtime(request: Request) -> ProviderSyncRuntime:
    runtime = getattr(request.app.state, "provider_sync_runtime", None)
    if not isinstance(runtime, ProviderSyncRuntime):
        raise HTTPException(status_code=503, detail="provider_sync_runtime_not_configured")
    return runtime


def _kind(provider: str) -> ProviderKind:
    try:
        return normalize_provider(provider)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="provider_not_supported") from exc


async def _json_payload(request: Request) -> Mapping[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="request_body_must_be_object") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=422, detail="request_body_must_be_object")
    return payload


def _safe_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderSyncMissing):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProviderSyncConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (ProviderSyncError, ProviderClientError, WebhookVerificationError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="provider_sync_operation_failed")


def _response(payload: Mapping[str, Any], *, operation: str) -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "operation": operation,
        **dict(payload),
        "read_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def register_provider_sync_routes(
    app: FastAPI,
    *,
    runtime: ProviderSyncRuntime | None = None,
) -> None:
    existing = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    overlap = PROVIDER_SYNC_ROUTES.intersection(existing)
    if overlap:
        if overlap == PROVIDER_SYNC_ROUTES:
            if runtime is not None:
                app.state.provider_sync_runtime = runtime
            return
        raise RuntimeError("provider_sync_partial_route_group_detected")
    if runtime is not None:
        app.state.provider_sync_runtime = runtime

    @app.get("/providers/{provider}/repositories/{repository_id:path}/sync")
    async def provider_sync_status(provider: str, repository_id: str, request: Request) -> dict[str, Any]:
        try:
            stored = _runtime(request).service.store.load(_kind(provider), repository_id)
            return _response(_runtime(request).service.safe(stored), operation="status")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/providers/{provider}/repositories/{repository_id:path}/collect")
    async def collect_provider(provider: str, repository_id: str, request: Request) -> dict[str, Any]:
        try:
            payload = await _json_payload(request)
            kind = _kind(provider)
            result = _runtime(request).service.collect(
                _runtime(request).collector(kind),
                repository_id=repository_id,
                requested_revision=str(payload.get("revision") or ""),
            )
            return _response(result, operation="collection_completed")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc

    @app.post("/providers/{provider}/repositories/{repository_id:path}/webhook")
    async def accept_provider_webhook(provider: str, repository_id: str, request: Request) -> dict[str, Any]:
        try:
            kind = _kind(provider)
            body = await request.body()
            if not body:
                raise ProviderSyncError("provider_webhook_body_required")
            headers = {str(key): str(value) for key, value in request.headers.items()}
            result = _runtime(request).service.accept_webhook(
                provider=kind,
                repository_id=repository_id,
                secret=_runtime(request).webhook_secret(kind),
                headers=headers,
                body=body,
                replay_guard=_runtime(request).replay_guard(kind),
            )
            return _response(result, operation="webhook_verified_and_scheduled")
        except HTTPException:
            raise
        except Exception as exc:
            raise _safe_error(exc) from exc


__all__ = [
    "PROVIDER_SYNC_ROUTES",
    "ProviderSyncRuntime",
    "VERSION",
    "register_provider_sync_routes",
]
