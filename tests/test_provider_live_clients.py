from __future__ import annotations

import httpx

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import (
    AzureDevOpsClient,
    BitbucketCloudClient,
    GitLabClient,
    RetryPolicy,
)
from nico.provider_neutral_contract import ProviderKind


def _credential(provider: str, host: str, scheme: str = "bearer"):
    reference = build_reference(
        provider=provider,
        env_var="TOKEN",
        scheme=scheme,
        key_id=f"{provider}-test",
        allowed_hosts=(host,),
        scopes=("read",),
    )
    return EnvironmentCredentialResolver({"TOKEN": "secret"}).resolve(reference)


def test_gitlab_client_collects_exact_snapshot_and_adapts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["PRIVATE-TOKEN"] == "secret"
        path = request.url.path
        if path.endswith("/repository/commits"):
            return httpx.Response(200, json=[{"id": "a" * 40}])
        if path.endswith("/repository/branches"):
            return httpx.Response(200, json=[{"name": "main"}])
        if path.endswith("/merge_requests"):
            return httpx.Response(
                200,
                json=[
                    {
                        "iid": 7,
                        "title": "Repair",
                        "state": "merged",
                        "source_branch": "repair",
                        "target_branch": "main",
                        "author": {"username": "dev"},
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-02T00:00:00Z",
                        "merged_at": "2026-01-02T00:00:00Z",
                    }
                ],
            )
        if path.endswith("/pipelines"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 9,
                        "sha": "a" * 40,
                        "ref": "main",
                        "status": "success",
                        "created_at": "2026-01-01T00:00:00Z",
                        "web_url": "https://gitlab.example.com/pipelines/9",
                    }
                ],
            )
        if path.endswith("/issues") or path.endswith("/releases"):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "id": 17,
                "path": "repo",
                "path_with_namespace": "group/repo",
                "namespace": "group",
                "default_branch": "main",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = GitLabClient(
        instance_url="https://gitlab.example.com",
        credential=_credential("gitlab", "gitlab.example.com", "private_token"),
        client=client,
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    collection = collector.collect("group/repo")
    adapted = collection.adapt()

    assert collection.provider is ProviderKind.GITLAB
    assert collection.revision == "a" * 40
    assert adapted.warnings == ()
    assert adapted.envelope.snapshot.revision == "a" * 40
    assert adapted.envelope.change_requests[0].native_id == "7"
    assert adapted.envelope.ci_runs[0].revision == "a" * 40


def test_bitbucket_client_collects_cloud_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        path = request.url.path
        if path.endswith("/commits"):
            return httpx.Response(200, json={"values": [{"hash": "b" * 40}]})
        if path.endswith("/refs/branches"):
            return httpx.Response(200, json={"values": [{"name": "main"}]})
        if path.endswith("/pullrequests"):
            return httpx.Response(200, json={"values": []})
        if path.endswith("/pipelines/"):
            return httpx.Response(200, json={"values": []})
        if path.endswith("/issues"):
            return httpx.Response(404, json={"error": "disabled"})
        return httpx.Response(
            200,
            json={
                "uuid": "repo-uuid",
                "slug": "repo",
                "workspace": {"slug": "workspace"},
                "mainbranch": {"name": "main"},
            },
        )

    collector = BitbucketCloudClient(
        credential=_credential("bitbucket", "api.bitbucket.org"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    collection = collector.collect("workspace/repo")
    adapted = collection.adapt()

    assert collection.revision == "b" * 40
    assert adapted.warnings == ()
    assert adapted.envelope.identity.repository_id == "repo-uuid"


def test_azure_client_collects_exact_build_revision() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Basic ")
        path = request.url.path
        if path.endswith("/commits"):
            return httpx.Response(200, json={"value": [{"commitId": "c" * 40}]})
        if path.endswith("/refs"):
            return httpx.Response(200, json={"value": [{"name": "refs/heads/main"}]})
        if path.endswith("/pullrequests"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/_apis/build/builds"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": 11,
                            "sourceVersion": "c" * 40,
                            "sourceBranch": "refs/heads/main",
                            "status": "completed",
                            "result": "succeeded",
                            "definition": {"name": "CI"},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "azure-repo",
                "name": "repo",
                "defaultBranch": "refs/heads/main",
                "project": {"name": "Project"},
            },
        )

    collector = AzureDevOpsClient(
        organization="Org",
        project="Project",
        credential=_credential("azure_devops", "dev.azure.com", "basic_token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    collection = collector.collect("azure-repo")
    adapted = collection.adapt()

    assert collection.revision == "c" * 40
    assert adapted.warnings == ()
    assert adapted.envelope.ci_runs[0].revision == "c" * 40


def test_rate_limit_retries_are_bounded() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        path = request.url.path
        if path.endswith("/repository/commits"):
            return httpx.Response(200, json=[{"id": "d" * 40}])
        if any(path.endswith(suffix) for suffix in ("/repository/branches", "/merge_requests", "/pipelines", "/issues", "/releases")):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={"id": 1, "path": "repo", "namespace": "group", "default_branch": "main"},
        )

    collector = GitLabClient(
        instance_url="https://gitlab.example.com",
        credential=_credential("gitlab", "gitlab.example.com", "private_token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
        sleeper=sleeps.append,
    )
    collection = collector.collect("group/repo")
    assert collection.revision == "d" * 40
    assert sleeps == [0]
