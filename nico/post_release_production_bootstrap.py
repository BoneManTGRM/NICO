from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from fastapi import FastAPI

from nico.monitor_approval_governance import ApprovalRevocationStore, GovernedMonitorExecuteService
from nico.monitor_execute_service import MonitorExecuteStore
from nico.monitor_governed_api import GOVERNANCE_ROUTES, register_governed_monitor_routes
from nico.provider_credentials import SecretValue
from nico.provider_neutral_contract import ProviderKind
from nico.provider_sync_api import PROVIDER_SYNC_ROUTES, ProviderSyncRuntime, register_provider_sync_routes
from nico.provider_sync_service import ProviderCollector, ProviderSyncService, ProviderSyncStore


VERSION = "nico.post_release_production_bootstrap.v1"
DIAGNOSTICS_ROUTE = "/diagnostics/post-release-runtime"


@dataclass(frozen=True)
class PostReleaseRuntimeConfig:
    enable_provider_sync: bool = False
    enable_monitor_execute: bool = False
    database_dialect: str = "sqlite"
    provider_poll_interval_seconds: int = 900
    provider_max_failure_backoff_seconds: int = 3600

    def validate(self) -> None:
        if self.database_dialect not in {"sqlite", "postgres"}:
            raise ValueError("post_release_database_dialect_unsupported")
        if self.provider_poll_interval_seconds < 60:
            raise ValueError("post_release_provider_poll_interval_too_short")
        if self.provider_max_failure_backoff_seconds < self.provider_poll_interval_seconds:
            raise ValueError("post_release_provider_backoff_invalid")


@dataclass(frozen=True)
class PostReleaseDependencies:
    connection_factory: Callable[[], Any] | None = None
    provider_collectors: Mapping[ProviderKind, ProviderCollector] | None = None
    provider_webhook_secrets: Mapping[ProviderKind, SecretValue] | None = None


def _route_count(target: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in target.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(value).upper() for value in (getattr(route, "methods", set()) or set())}
    )


def _provider_status(
    target: FastAPI,
    *,
    config: PostReleaseRuntimeConfig,
    dependencies: PostReleaseDependencies,
) -> dict[str, Any]:
    if not config.enable_provider_sync:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": "provider_sync_not_enabled",
            "route_counts": {},
        }
    if dependencies.connection_factory is None:
        return {
            "enabled": True,
            "status": "blocked",
            "reason": "provider_sync_connection_factory_missing",
            "route_counts": {},
        }
    collectors = dict(dependencies.provider_collectors or {})
    secrets = dict(dependencies.provider_webhook_secrets or {})
    if not collectors:
        return {
            "enabled": True,
            "status": "blocked",
            "reason": "provider_collectors_missing",
            "route_counts": {},
        }
    for provider, collector in collectors.items():
        if not isinstance(provider, ProviderKind) or collector.provider is not provider:
            return {
                "enabled": True,
                "status": "blocked",
                "reason": "provider_collector_kind_mismatch",
                "route_counts": {},
            }
    if set(secrets) - set(collectors):
        return {
            "enabled": True,
            "status": "blocked",
            "reason": "provider_webhook_secret_without_collector",
            "route_counts": {},
        }
    store = ProviderSyncStore(
        dependencies.connection_factory,
        dialect=config.database_dialect,
    )
    store.ensure_schema()
    service = ProviderSyncService(
        store,
        poll_interval_seconds=config.provider_poll_interval_seconds,
        max_failure_backoff_seconds=config.provider_max_failure_backoff_seconds,
    )
    runtime = ProviderSyncRuntime(
        service=service,
        collectors=collectors,
        webhook_secrets=secrets,
    )
    register_provider_sync_routes(target, runtime=runtime)
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(PROVIDER_SYNC_ROUTES)
    }
    ready = all(count == 1 for count in route_counts.values())
    return {
        "enabled": True,
        "status": "ready" if ready else "blocked",
        "reason": "" if ready else "provider_sync_routes_incomplete",
        "configured_collectors": sorted(provider.value for provider in collectors),
        "configured_webhook_secrets": sorted(provider.value for provider in secrets),
        "route_counts": route_counts,
        "read_only": True,
    }


def _monitor_status(
    target: FastAPI,
    *,
    config: PostReleaseRuntimeConfig,
    dependencies: PostReleaseDependencies,
) -> dict[str, Any]:
    if not config.enable_monitor_execute:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": "monitor_execute_not_enabled",
            "route_counts": {},
        }
    if dependencies.connection_factory is None:
        return {
            "enabled": True,
            "status": "blocked",
            "reason": "monitor_execute_connection_factory_missing",
            "route_counts": {},
        }
    store = MonitorExecuteStore(
        dependencies.connection_factory,
        dialect=config.database_dialect,
    )
    store.ensure_schema()
    revocations = ApprovalRevocationStore(
        dependencies.connection_factory,
        dialect=config.database_dialect,
    )
    revocations.ensure_schema()
    service = GovernedMonitorExecuteService(store, revocations)
    register_governed_monitor_routes(target, service=service)
    expected_routes = set(GOVERNANCE_ROUTES)
    from nico.monitor_execute_api import MONITOR_EXECUTE_ROUTES

    expected_routes.update(MONITOR_EXECUTE_ROUTES)
    route_counts = {
        f"{method} {path}": _route_count(target, method, path)
        for method, path in sorted(expected_routes)
    }
    ready = all(count == 1 for count in route_counts.values())
    return {
        "enabled": True,
        "status": "ready" if ready else "blocked",
        "reason": "" if ready else "monitor_execute_routes_incomplete",
        "route_counts": route_counts,
        "approval_expiry_enforced": True,
        "approval_revocation_enforced": True,
        "production_execution_requires_explicit_approval": True,
    }


def _register_diagnostics(target: FastAPI) -> None:
    if _route_count(target, "GET", DIAGNOSTICS_ROUTE):
        return

    def diagnostics() -> dict[str, Any]:
        status = dict(getattr(target.state, "nico_post_release_runtime", {}) or {})
        status.setdefault("artifact_schema", VERSION)
        status["human_review_required"] = True
        status["client_delivery_allowed"] = False
        status["production_execution_requires_explicit_approval"] = True
        return status

    target.add_api_route(
        DIAGNOSTICS_ROUTE,
        diagnostics,
        methods=["GET"],
        tags=["diagnostics"],
    )
    target.openapi_schema = None


def install_post_release_runtime(
    target: FastAPI,
    *,
    config: PostReleaseRuntimeConfig,
    dependencies: PostReleaseDependencies,
) -> dict[str, Any]:
    """Install provider sync and Monitor + Execute only when explicitly enabled.

    Disabled features add no public operational routes. Enabled features with missing
    dependencies remain blocked and add no partial route group. All execution remains
    exact-SHA/path scoped, explicitly approved, and separately verified.
    """

    config.validate()
    provider = _provider_status(target, config=config, dependencies=dependencies)
    monitor = _monitor_status(target, config=config, dependencies=dependencies)
    _register_diagnostics(target)
    enabled = [item for item in (provider, monitor) if item.get("enabled") is True]
    ready = bool(enabled) and all(item.get("status") == "ready" for item in enabled)
    status = {
        "artifact_schema": VERSION,
        "status": "ready" if ready else "blocked" if enabled else "disabled",
        "provider_sync": provider,
        "monitor_execute": monitor,
        "diagnostics_route": DIAGNOSTICS_ROUTE,
        "diagnostics_route_count": _route_count(target, "GET", DIAGNOSTICS_ROUTE),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "production_execution_requires_explicit_approval": True,
    }
    target.state.nico_post_release_runtime = status
    return status


__all__ = [
    "DIAGNOSTICS_ROUTE",
    "PostReleaseDependencies",
    "PostReleaseRuntimeConfig",
    "VERSION",
    "install_post_release_runtime",
]
