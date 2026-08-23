from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from nico import comprehensive_api_routes as api_routes
from nico.admin_security import require_admin_write
from nico.hosted_assessment import GITHUB_API, GitHubAssessmentClient
from nico.hosted_provider_comprehensive_runtime_v1 import build_hosted_provider_client
from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY as ROLLOUT_STATE_KEY

VERSION = "nico.provider-repository-enumeration.v1"
OPERATOR_REPOSITORIES_ROUTE = "/providers/operator/repositories"
_MAX_RETURNED_REPOSITORIES = 1000


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _required(value: Any, field: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _provider(value: Any) -> ProviderKind:
    token = _required(value, "provider").casefold().replace("-", "_")
    aliases = {
        "github": ProviderKind.GITHUB,
        "gitlab": ProviderKind.GITLAB,
        "bitbucket": ProviderKind.BITBUCKET_CLOUD,
        "bitbucket_cloud": ProviderKind.BITBUCKET_CLOUD,
        "azure": ProviderKind.AZURE_DEVOPS,
        "azure_devops": ProviderKind.AZURE_DEVOPS,
        "azure_repos": ProviderKind.AZURE_DEVOPS,
    }
    selected = aliases.get(token)
    if selected is None:
        raise ValueError("provider_not_supported")
    return selected


def _operator_required(token: str) -> None:
    allowed, status = require_admin_write(token)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "authorized_nico_operator_required",
                "admin_write": status,
                "operator_run_only": True,
                "customer_self_service": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )


def _github_authorized_repositories() -> list[Mapping[str, Any]]:
    client = GitHubAssessmentClient()
    repositories: list[Mapping[str, Any]] = []
    for page in range(1, 101):
        payload, error = client.get_json(
            f"{GITHUB_API}/user/repos",
            {
                "affiliation": "owner,collaborator,organization_member",
                "visibility": "all",
                "sort": "full_name",
                "direction": "asc",
                "per_page": 100,
                "page": page,
            },
        )
        if error:
            raise ValueError(f"github_repository_enumeration_unavailable:{error}")
        items = payload if isinstance(payload, list) else []
        repositories.extend(item for item in items if isinstance(item, Mapping))
        if len(items) < 100:
            return repositories
    raise ValueError("github_repository_enumeration_pagination_limit_exceeded")


def _repository_summary(
    provider: ProviderKind,
    item: Mapping[str, Any],
    *,
    organization: str = "",
    project: str = "",
) -> dict[str, Any]:
    if provider is ProviderKind.GITHUB:
        locator = _required(item.get("full_name"), "github_repository_full_name")
        return {
            "provider": provider.value,
            "repository_id": _text(item.get("id")) or locator,
            "repository_locator": locator,
            "display_name": _text(item.get("name")) or locator.rsplit("/", 1)[-1],
            "default_branch": _text(item.get("default_branch")) or None,
            "private": bool(item.get("private")),
            "archived": bool(item.get("archived")),
            "web_url": _text(item.get("html_url")) or None,
        }
    if provider is ProviderKind.GITLAB:
        locator = _required(item.get("path_with_namespace"), "gitlab_repository_path")
        return {
            "provider": provider.value,
            "repository_id": _text(item.get("id")) or locator,
            "repository_locator": locator,
            "display_name": _text(item.get("name")) or locator.rsplit("/", 1)[-1],
            "default_branch": _text(item.get("default_branch")) or None,
            "private": _text(item.get("visibility")).casefold() == "private",
            "archived": bool(item.get("archived")),
            "web_url": _text(item.get("web_url")) or None,
        }
    if provider is ProviderKind.BITBUCKET_CLOUD:
        locator = _text(item.get("full_name"))
        if not locator:
            workspace = _text((item.get("workspace") or {}).get("slug") if isinstance(item.get("workspace"), Mapping) else "")
            slug = _text(item.get("slug"))
            locator = f"{workspace}/{slug}" if workspace and slug else ""
        locator = _required(locator, "bitbucket_repository_full_name")
        return {
            "provider": provider.value,
            "repository_id": _text(item.get("uuid")) or locator,
            "repository_locator": locator,
            "display_name": _text(item.get("name")) or locator.rsplit("/", 1)[-1],
            "default_branch": _text((item.get("mainbranch") or {}).get("name") if isinstance(item.get("mainbranch"), Mapping) else "") or None,
            "private": bool(item.get("is_private")),
            "archived": False,
            "web_url": _text((item.get("links") or {}).get("html", {}).get("href") if isinstance(item.get("links"), Mapping) and isinstance((item.get("links") or {}).get("html"), Mapping) else "") or None,
        }
    if provider is ProviderKind.AZURE_DEVOPS:
        name = _required(item.get("name"), "azure_repository_name")
        locator = name
        return {
            "provider": provider.value,
            "repository_id": _text(item.get("id")) or name,
            "repository_locator": locator,
            "display_name": name,
            "default_branch": _text(item.get("defaultBranch")).removeprefix("refs/heads/") or None,
            "private": True,
            "archived": False,
            "web_url": _text(item.get("webUrl")) or None,
            "provider_organization": organization,
            "provider_project": project,
        }
    raise ValueError("provider_not_supported")


def enumerate_authorized_repositories(
    request: Request,
    *,
    provider_value: str,
    customer_id: str,
    project_id: str,
    session_id: str,
    token: str,
    workspace: str = "",
    provider_organization: str = "",
    provider_project: str = "",
) -> dict[str, Any]:
    _operator_required(token)
    provider = _provider(provider_value)
    customer = _required(customer_id, "customer_id")
    project = _required(project_id, "project_id")
    session = _required(session_id, "session_id")

    registry = getattr(request.app.state, ROLLOUT_STATE_KEY, None)
    if not isinstance(registry, ProviderRolloutRegistry):
        raise ValueError("provider_rollout_control_unavailable")
    preflight = registry.preflight(
        {
            "provider": provider.value,
            "client_id": customer,
            "project_id": project,
            "session_id": session,
            "run_id": f"repoenum_{uuid4().hex}",
            "locale": "en-US",
            "execution_mode": "internal_test",
            "ci_provider": provider.value,
        },
        operator_authorized=True,
    )

    if provider is ProviderKind.GITHUB:
        raw = _github_authorized_repositories()
    else:
        context = {
            "provider_organization": _text(provider_organization),
            "provider_project": _text(provider_project),
        }
        client = build_hosted_provider_client(provider, context)
        try:
            if provider is ProviderKind.BITBUCKET_CLOUD:
                raw = client.list_authorized_repositories(_required(workspace, "workspace"))
            else:
                raw = client.list_authorized_repositories()
        finally:
            client.close()

    summaries = [
        _repository_summary(
            provider,
            item,
            organization=_text(provider_organization),
            project=_text(provider_project),
        )
        for item in raw
        if isinstance(item, Mapping)
    ]
    summaries.sort(key=lambda item: (str(item.get("repository_locator") or "").casefold(), str(item.get("repository_id") or "")))
    total = len(summaries)
    returned = summaries[:_MAX_RETURNED_REPOSITORIES]
    return {
        "artifact_schema": VERSION,
        "status": "authorized_operator_repository_enumeration",
        "provider": provider.value,
        "customer_id": customer,
        "project_id": project,
        "session_id": session,
        "connection_binding_id": preflight.get("connection_binding_id"),
        "repository_count": total,
        "returned_repository_count": len(returned),
        "truncated": total > len(returned),
        "repositories": returned,
        "operator_run_only": True,
        "customer_self_service": False,
        "credentials_server_side_only": True,
        "credential_reference_exposed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_provider_repository_enumeration(app: FastAPI) -> dict[str, Any]:
    route_count = sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == OPERATOR_REPOSITORIES_ROUTE
        and "GET" in {str(method).upper() for method in (getattr(route, "methods", set()) or set())}
    )
    if route_count == 0:
        @app.get(OPERATOR_REPOSITORIES_ROUTE)
        async def operator_repository_enumeration(
            request: Request,
            provider: str = Query(...),
            customer_id: str = Query(...),
            project_id: str = Query(...),
            session_id: str = Query(...),
            workspace: str = Query(default=""),
            provider_organization: str = Query(default=""),
            provider_project: str = Query(default=""),
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            try:
                return await run_in_threadpool(
                    enumerate_authorized_repositories,
                    request,
                    provider_value=provider,
                    customer_id=customer_id,
                    project_id=project_id,
                    session_id=session_id,
                    token=x_nico_admin_token,
                    workspace=workspace,
                    provider_organization=provider_organization,
                    provider_project=provider_project,
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise api_routes._translate_error(exc) from exc

        app.openapi_schema = None
        route_count = 1
    if route_count != 1:
        raise RuntimeError("provider_operator_repository_enumeration_route_missing_or_duplicated")
    status = {
        "artifact_schema": VERSION,
        "status": "installed",
        "route": OPERATOR_REPOSITORIES_ROUTE,
        "route_count": route_count,
        "provider_count": 4,
        "server_side_provider_clients": True,
        "server_side_credentials_only": True,
        "operator_authorization_required": True,
        "customer_self_service": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_provider_repository_enumeration = status
    return status


__all__ = [
    "OPERATOR_REPOSITORIES_ROUTE",
    "VERSION",
    "enumerate_authorized_repositories",
    "install_provider_repository_enumeration",
]
