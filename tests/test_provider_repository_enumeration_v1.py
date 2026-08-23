from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from nico import provider_repository_enumeration_v1 as enumeration
from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import (
    STATE_KEY,
    ProviderRolloutConfig,
    ProviderRolloutError,
    ProviderRolloutRegistry,
    ProviderRolloutState,
    install_provider_rollout_routes,
)


def _configs() -> dict[ProviderKind, ProviderRolloutConfig]:
    return {
        ProviderKind.GITHUB: ProviderRolloutConfig(
            ProviderKind.GITHUB,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="github-server-reference",
            capability_evidence_reference="artifact://github/engineering",
            native_ci_evidence_supported=True,
        ),
        ProviderKind.GITLAB: ProviderRolloutConfig(
            ProviderKind.GITLAB,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="gitlab-server-reference",
            capability_evidence_reference="artifact://gitlab/engineering",
            native_ci_evidence_supported=True,
        ),
        ProviderKind.BITBUCKET_CLOUD: ProviderRolloutConfig(
            ProviderKind.BITBUCKET_CLOUD,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="bitbucket-server-reference",
            capability_evidence_reference="artifact://bitbucket/engineering",
        ),
        ProviderKind.AZURE_DEVOPS: ProviderRolloutConfig(
            ProviderKind.AZURE_DEVOPS,
            ProviderRolloutState.INTERNAL_TEST,
            True,
            credential_reference_id="azure-server-reference",
            capability_evidence_reference="artifact://azure/engineering",
            native_ci_evidence_supported=True,
        ),
    }


def _app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    configs: dict[ProviderKind, ProviderRolloutConfig] | None = None,
) -> FastAPI:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-token")
    app = FastAPI()
    registry = ProviderRolloutRegistry(configs=configs or _configs())
    install_provider_rollout_routes(app, registry=registry)
    enumeration.install_provider_repository_enumeration(app)
    return app


class FakeHostedClient:
    def __init__(self, provider: ProviderKind, items: list[dict]) -> None:
        self.provider = provider
        self.items = items
        self.calls: list[tuple] = []
        self.closed = False
        self.secret = "must-not-appear-in-enumeration"

    def list_authorized_repositories(self, *args):
        self.calls.append(tuple(args))
        return list(self.items)

    def close(self) -> None:
        self.closed = True


def _query(provider: str, **extra: str) -> dict[str, str]:
    return {
        "provider": provider,
        "customer_id": "client-1",
        "project_id": "project-1",
        "session_id": "session-1",
        **extra,
    }


def test_repository_enumeration_route_requires_authorized_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    called = False

    def forbidden_call():
        nonlocal called
        called = True
        raise AssertionError("provider enumeration must not run without operator authorization")

    monkeypatch.setattr(enumeration, "_github_authorized_repositories", forbidden_call)
    response = TestClient(app).get(
        enumeration.OPERATOR_REPOSITORIES_ROUTE,
        params=_query("github"),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "authorized_nico_operator_required"
    assert called is False


def test_github_repository_enumeration_is_operator_bound_and_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch)
    monkeypatch.setattr(
        enumeration,
        "_github_authorized_repositories",
        lambda: [
            {
                "id": 123,
                "full_name": "Acme/alpha",
                "name": "alpha",
                "default_branch": "main",
                "private": True,
                "archived": False,
                "html_url": "https://github.com/Acme/alpha",
            }
        ],
    )

    response = TestClient(app).get(
        enumeration.OPERATOR_REPOSITORIES_ROUTE,
        params=_query("github"),
        headers={"X-NICO-Admin-Token": "operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authorized_operator_repository_enumeration"
    assert body["provider"] == "github"
    assert body["repository_count"] == 1
    assert body["repositories"] == [
        {
            "provider": "github",
            "repository_id": "123",
            "repository_locator": "Acme/alpha",
            "display_name": "alpha",
            "default_branch": "main",
            "private": True,
            "archived": False,
            "web_url": "https://github.com/Acme/alpha",
        }
    ]
    assert body["connection_binding_id"]
    assert body["operator_run_only"] is True
    assert body["customer_self_service"] is False
    assert body["credentials_server_side_only"] is True
    assert body["credential_reference_exposed"] is False
    assert body["client_delivery_allowed"] is False


@pytest.mark.parametrize(
    "provider,query_extra,items,expected_locator,expected_args",
    (
        (
            ProviderKind.GITLAB,
            {},
            [
                {
                    "id": 21,
                    "path_with_namespace": "group/subgroup/repo",
                    "name": "repo",
                    "default_branch": "main",
                    "visibility": "private",
                    "archived": False,
                    "web_url": "https://gitlab.com/group/subgroup/repo",
                }
            ],
            "group/subgroup/repo",
            (),
        ),
        (
            ProviderKind.BITBUCKET_CLOUD,
            {"workspace": "workspace"},
            [
                {
                    "uuid": "{repo-uuid}",
                    "full_name": "workspace/repo",
                    "name": "repo",
                    "mainbranch": {"name": "main"},
                    "is_private": True,
                    "links": {"html": {"href": "https://bitbucket.org/workspace/repo"}},
                }
            ],
            "workspace/repo",
            ("workspace",),
        ),
        (
            ProviderKind.AZURE_DEVOPS,
            {"provider_organization": "Org", "provider_project": "Project"},
            [
                {
                    "id": "azure-repo-id",
                    "name": "repo",
                    "defaultBranch": "refs/heads/main",
                    "webUrl": "https://dev.azure.com/Org/Project/_git/repo",
                }
            ],
            "repo",
            (),
        ),
    ),
)
def test_hosted_repository_enumeration_reuses_server_side_provider_clients(
    monkeypatch: pytest.MonkeyPatch,
    provider: ProviderKind,
    query_extra: dict[str, str],
    items: list[dict],
    expected_locator: str,
    expected_args: tuple,
) -> None:
    app = _app(monkeypatch)
    clients: list[FakeHostedClient] = []

    def build_client(selected: ProviderKind, context: dict):
        assert selected is provider
        if provider is ProviderKind.AZURE_DEVOPS:
            assert context["provider_organization"] == "Org"
            assert context["provider_project"] == "Project"
        client = FakeHostedClient(selected, items)
        clients.append(client)
        return client

    monkeypatch.setattr(enumeration, "build_hosted_provider_client", build_client)

    response = TestClient(app).get(
        enumeration.OPERATOR_REPOSITORIES_ROUTE,
        params=_query(provider.value, **query_extra),
        headers={"X-NICO-Admin-Token": "operator-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == provider.value
    assert body["repository_count"] == 1
    assert body["repositories"][0]["repository_locator"] == expected_locator
    assert body["operator_run_only"] is True
    assert body["customer_self_service"] is False
    assert body["credential_reference_exposed"] is False
    assert body["human_review_required"] is True
    assert body["client_delivery_allowed"] is False
    assert clients[0].calls == [expected_args]
    assert clients[0].closed is True
    assert "must-not-appear-in-enumeration" not in repr(body)


def test_disabled_provider_enumeration_fails_closed_before_provider_client_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configs = _configs()
    configs[ProviderKind.GITLAB] = ProviderRolloutConfig(
        ProviderKind.GITLAB,
        ProviderRolloutState.DISABLED,
        False,
        credential_reference_id="gitlab-server-reference",
        capability_evidence_reference="artifact://gitlab/engineering",
    )
    app = _app(monkeypatch, configs=configs)
    used = False

    def build_client(*args, **kwargs):
        nonlocal used
        used = True
        raise AssertionError("disabled provider must fail before client construction")

    monkeypatch.setattr(enumeration, "build_hosted_provider_client", build_client)
    registry = getattr(app.state, STATE_KEY)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": enumeration.OPERATOR_REPOSITORIES_ROUTE,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 443),
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "app": app,
        }
    )
    assert isinstance(registry, ProviderRolloutRegistry)
    with pytest.raises(ProviderRolloutError, match="provider_operationally_disabled"):
        enumeration.enumerate_authorized_repositories(
            request,
            provider_value="gitlab",
            customer_id="client-1",
            project_id="project-1",
            session_id="session-1",
            token="operator-token",
        )
    assert used is False


def test_repository_enumeration_is_bound_once_in_production_bootstrap() -> None:
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(encoding="utf-8")
    assert "install_provider_repository_enumeration" in source
    assert "PROVIDER_REPOSITORY_ENUMERATION = install_provider_repository_enumeration(app)" in source
    assert '"customer_self_service"' in source
    assert '"client_delivery_allowed"' in source
