from __future__ import annotations

import httpx

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_issue_clients import BitbucketCloudIssueClient, GitLabIssueClient
from nico.provider_live_clients import RetryPolicy


def _credential(provider: str, host: str, env_var: str):
    reference = build_reference(
        provider=provider,
        env_var=env_var,
        scheme="private_token" if provider == "gitlab" else "bearer",
        key_id=f"{provider}-issues-test",
        allowed_hosts=(host,),
        scopes=("read_api", "read_repository") if provider == "gitlab" else ("issue:read",),
    )
    return EnvironmentCredentialResolver({env_var: "secret"}).resolve(reference)


def test_gitlab_issue_client_paginates_and_preserves_native_identity() -> None:
    pages = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal pages
        pages += 1
        assert request.headers["PRIVATE-TOKEN"] == "secret"
        if pages == 1:
            return httpx.Response(
                200,
                headers={"X-Next-Page": "2"},
                json=[
                    {
                        "iid": 1,
                        "title": "First issue",
                        "state": "opened",
                        "assignee": {"username": "dev"},
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-02T00:00:00Z",
                        "web_url": "https://gitlab.example.com/issues/1",
                    }
                ],
            )
        return httpx.Response(
            200,
            headers={"X-Next-Page": ""},
            json=[
                {
                    "iid": 2,
                    "title": "Second issue",
                    "state": "closed",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-03T00:00:00Z",
                    "web_url": "https://gitlab.example.com/issues/2",
                }
            ],
        )

    client = GitLabIssueClient(
        instance_url="https://gitlab.example.com",
        credential=_credential("gitlab", "gitlab.example.com", "GITLAB_TOKEN"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    result = client.collect("group/repo", repository_id="17")

    assert result.provider.value == "gitlab"
    assert result.project_id == "group/repo"
    assert result.repository_id == "17"
    assert result.pages_fetched == 2
    assert result.requests_made == 2
    assert [item.native_id for item in result.items] == ["1", "2"]
    assert result.items[0].assignee == "dev"
    assert all(item.source_fingerprint.startswith("sha256:") for item in result.items)


def test_bitbucket_issue_client_follows_next_url() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "Bearer secret"
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 7,
                            "kind": "bug",
                            "title": "Issue seven",
                            "state": "new",
                            "created_on": "2026-01-01T00:00:00Z",
                            "updated_on": "2026-01-02T00:00:00Z",
                            "links": {"html": {"href": "https://bitbucket.org/issues/7"}},
                        }
                    ],
                    "next": "https://api.bitbucket.org/2.0/repositories/workspace/repo/issues?page=2",
                },
            )
        return httpx.Response(
            200,
            json={
                "values": [
                    {
                        "id": 8,
                        "kind": "task",
                        "title": "Issue eight",
                        "state": "resolved",
                        "created_on": "2026-01-01T00:00:00Z",
                        "updated_on": "2026-01-03T00:00:00Z",
                        "links": {"html": {"href": "https://bitbucket.org/issues/8"}},
                    }
                ]
            },
        )

    client = BitbucketCloudIssueClient(
        credential=_credential("bitbucket", "api.bitbucket.org", "BITBUCKET_TOKEN"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    result = client.collect("workspace/repo")

    assert result.provider.value == "bitbucket"
    assert result.project_id == "workspace"
    assert result.repository_id == "workspace/repo"
    assert result.pages_fetched == 2
    assert [item.native_id for item in result.items] == ["7", "8"]
    assert result.items[1].item_type == "task"
