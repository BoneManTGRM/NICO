from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol

from fastapi import FastAPI, HTTPException, Request

from nico.provider_credential_rotation import (
    CredentialRotationError,
    CredentialRotationLedger,
    CredentialRotationPolicy,
    rotation_due,
)
from nico.provider_credentials import SecretValue
from nico.provider_neutral_contract import ProviderKind, normalize_provider
from nico.provider_work_items import WorkItemCollection


VERSION = "nico.provider_admin_api.v1"
PROVIDER_ADMIN_ROUTES = {
    ("POST", "/admin/providers/{provider}/work-items/{repository_id:path}/collect"),
    ("GET", "/admin/providers/{provider}/credentials/{key_id}/versions"),
    ("POST", "/admin/providers/{provider}/credentials/{key_id}/activate"),
    ("POST", "/admin/providers/{provider}/credentials/{key_id}/retire"),
}


class AdminAuthorizer(Protocol):
    def __call__(self, request: Request) -> bool:
        ...


class WorkItemCollector(Protocol):
    def __call__(self, repository_id: str, options: Mapping[str, Any]) -> WorkItemCollection:
        ...


@dataclass(frozen=True)
class HeaderAdminAuthorizer:
    secret: SecretValue
    header_name: str = "X-NICO-Admin-Token"

    def __call__(self, request: Request) -> bool:
        presented = str(request.headers.get(self.header_name) or "")
        return bool(presented) and secrets.compare_digest(presented, self.secret.reveal())


@dataclass
class ProviderAdminRuntime:
    authorizer: AdminAuthorizer
    credential_ledger: CredentialRotationLedger
    rotation_policy: CredentialRotationPolicy = field(default_factory=CredentialRotationPolicy)
    work_item_collectors: dict[ProviderKind, WorkItemCollector] = field(default_factory=dict)

    def collector(self, provider: ProviderKind) -> WorkItemCollector:
        collector = self.work_item_collectors.get(provider)
        if collector is None:
            raise RuntimeError("provider_work_item_collector_not_configured")
        return collector


def gitlab_issue_collector(client: Any) -> WorkItemCollector:
    def collect(repository_id: str, options: Mapping[str, Any]) -> WorkItemCollection:
        return client.collect(
            str(options.get("project") or repository_id),
            repository_id=repository_id,
            state=str(options.get("state") or "all"),
        )

    return collect


def bitbucket_issue_collector(client: Any) -> WorkItemCollector:
    def collect(repository_id: str, options: Mapping[str, Any]) -> WorkItemCollection:
        del options
        return client.collect(repository_id)

    return collect


def azure_boards_collector(client: Any) -> WorkItemCollector:
    def collect(repository_id: str, options: Mapping[str, Any]) -> WorkItemCollection:
        return client.collect(
            repository_id=repository_id,
            wiql=str(
                options.get("wiql")
                or "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project ORDER BY [System.ChangedDate] DESC"
            ),
            max_items=int(options.get("max_items") or 1000),
        )

    return collect


def _runtime(request: Request) -> ProviderAdminRuntime:
    runtime = getattr(request.app.state, "provider_admin_runtime", None)
    if not isinstance(runtime, ProviderAdminRuntime):
        raise HTTPException(status_code=503, detail="provider_admin_runtime_not_configured")
    if not runtime.authorizer(request):
        raise HTTPException(status_code=403, detail="provider_admin_authorization_required")
    return runtime


def _provider(value: str) -> ProviderKind:
    try:
        return normalize_provider(value)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="provider_not_supported") from exc


async def _payload(request: Request) -> Mapping[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="request_body_must_be_object") from exc
    if not isinstance(payload, Mapping):
        raise HTTPException(status_code=422, detail="request_body_must_be_object")
    return payload


def _safe(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


def _work_items(collection: WorkItemCollection) -> dict[str, Any]:
    return {
        "provider": collection.provider.value,
        "project_id": collection.project_id,
        "repository_id": collection.repository_id,
        "collected_at": collection.collected_at,
        "requests_made": collection.requests_made,
        "pages_fetched": collection.pages_fetched,
        "warnings": list(collection.warnings),
        "items": [_safe(asdict(item)) for item in collection.items],
        "item_count": len(collection.items),
        "read_only": True,
    }


def _credential_version(record: Any, *, policy: CredentialRotationPolicy) -> dict[str, Any]:
    safe = _safe(asdict(record))
    safe["rotation_due"] = rotation_due(record, policy=policy)
    safe["raw_secret_present"] = False
    return safe


def _route_count(app: FastAPI, method: str, path: str) -> int:
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def register_provider_admin_routes(
    app: FastAPI,
    *,
    runtime: ProviderAdminRuntime | None = None,
) -> None:
    existing = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    overlap = PROVIDER_ADMIN_ROUTES.intersection(existing)
    if overlap:
        if overlap == PROVIDER_ADMIN_ROUTES:
            if runtime is not None:
                app.state.provider_admin_runtime = runtime
            return
        raise RuntimeError("provider_admin_partial_route_group_detected")
    if runtime is not None:
        runtime.rotation_policy.validate()
        runtime.credential_ledger.ensure_schema()
        app.state.provider_admin_runtime = runtime

    @app.post("/admin/providers/{provider}/work-items/{repository_id:path}/collect")
    async def collect_work_items(provider: str, repository_id: str, request: Request) -> dict[str, Any]:
        try:
            payload = await _payload(request)
            kind = _provider(provider)
            result = _runtime(request).collector(kind)(repository_id, payload)
            if result.provider is not kind:
                raise RuntimeError("provider_work_item_kind_mismatch")
            return {
                "artifact_schema": VERSION,
                "operation": "work_items_collected",
                **_work_items(result),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "provider_work_item_collection_failed") from exc

    @app.get("/admin/providers/{provider}/credentials/{key_id}/versions")
    async def credential_versions(provider: str, key_id: str, request: Request) -> dict[str, Any]:
        runtime_value = _runtime(request)
        kind = _provider(provider)
        records = runtime_value.credential_ledger.list_versions(kind, key_id)
        return {
            "artifact_schema": VERSION,
            "operation": "credential_versions",
            "provider": kind.value,
            "key_id": key_id,
            "versions": [
                _credential_version(item, policy=runtime_value.rotation_policy)
                for item in records
            ],
            "raw_secret_present": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @app.post("/admin/providers/{provider}/credentials/{key_id}/activate")
    async def activate_credential(provider: str, key_id: str, request: Request) -> dict[str, Any]:
        try:
            runtime_value = _runtime(request)
            payload = await _payload(request)
            allowed = {
                "version",
                "secret_reference",
                "activated_by",
                "approved_by",
                "activated_at",
                "expires_at",
            }
            unexpected = set(payload) - allowed
            if unexpected:
                raise CredentialRotationError("credential_activation_fields_invalid")
            record = runtime_value.credential_ledger.activate(
                provider=_provider(provider),
                key_id=key_id,
                version=str(payload.get("version") or ""),
                secret_reference=str(payload.get("secret_reference") or ""),
                activated_by=str(payload.get("activated_by") or ""),
                approved_by=str(payload.get("approved_by") or ""),
                activated_at=str(payload.get("activated_at") or ""),
                expires_at=str(payload.get("expires_at") or ""),
                policy=runtime_value.rotation_policy,
            )
            return {
                "artifact_schema": VERSION,
                "operation": "credential_activated",
                "credential": _credential_version(record, policy=runtime_value.rotation_policy),
                "raw_secret_present": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        except HTTPException:
            raise
        except CredentialRotationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/admin/providers/{provider}/credentials/{key_id}/retire")
    async def retire_credential(provider: str, key_id: str, request: Request) -> dict[str, Any]:
        try:
            runtime_value = _runtime(request)
            payload = await _payload(request)
            allowed = {"version", "retired_by", "retired_at"}
            unexpected = set(payload) - allowed
            if unexpected:
                raise CredentialRotationError("credential_retirement_fields_invalid")
            record = runtime_value.credential_ledger.retire(
                provider=_provider(provider),
                key_id=key_id,
                version=str(payload.get("version") or ""),
                retired_by=str(payload.get("retired_by") or ""),
                retired_at=str(payload.get("retired_at") or ""),
            )
            return {
                "artifact_schema": VERSION,
                "operation": "credential_retired",
                "credential": _credential_version(record, policy=runtime_value.rotation_policy),
                "raw_secret_present": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        except HTTPException:
            raise
        except CredentialRotationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = [
    "AdminAuthorizer",
    "HeaderAdminAuthorizer",
    "PROVIDER_ADMIN_ROUTES",
    "ProviderAdminRuntime",
    "VERSION",
    "WorkItemCollector",
    "azure_boards_collector",
    "bitbucket_issue_collector",
    "gitlab_issue_collector",
    "register_provider_admin_routes",
]
