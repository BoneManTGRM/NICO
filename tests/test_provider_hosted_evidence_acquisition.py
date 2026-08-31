from __future__ import annotations

import httpx
import pytest

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import (
    AzureDevOpsClient,
    BitbucketCloudClient,
    GitLabClient,
    ProviderClientError,
    RetryPolicy,
)
from nico.provider_neutral_contract import Capability, CapabilityState


def credential(provider: str, host: str, scheme: str = "bearer"):
    reference = build_reference(
        provider=provider,
        env_var="TOKEN",
        scheme=scheme,
        key_id=f"{provider}-hosted-test",
        allowed_hosts=(host,),
        scopes=("read",),
    )
    return EnvironmentCredentialResolver({"TOKEN": "secret"}).resolve(reference)


def status_map(envelope) -> dict[Capability, CapabilityState]:
    return {item.capability: item.state for item in envelope.capability_status}


def test_gitlab_collects_tree_tags_jobs_environments_deployments_and_releases() -> None:
    revision = "a" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v4/projects":
            return httpx.Response(200, json=[{"id": 17, "path_with_namespace": "group/repo"}])
        if path.endswith("/repository/commits"):
            return httpx.Response(200, json=[{"id": revision}])
        if path.endswith("/repository/branches"):
            return httpx.Response(200, json=[{"name": "main"}])
        if path.endswith("/repository/tree"):
            return httpx.Response(
                200,
                json=[{"id": "f" * 40, "path": "src/app.py", "type": "blob", "mode": "100644"}],
            )
        if path.endswith("/repository/tags"):
            return httpx.Response(200, json=[{"name": "v1", "commit": {"id": revision}}])
        if path.endswith("/merge_requests"):
            return httpx.Response(200, json=[])
        if path.endswith("/pipelines"):
            return httpx.Response(
                200,
                json=[{"id": 9, "sha": revision, "ref": "main", "status": "success"}],
            )
        if path.endswith("/pipelines/9/jobs"):
            return httpx.Response(
                200,
                json=[{"id": 91, "name": "test", "stage": "verify", "status": "success"}],
            )
        if path.endswith("/issues"):
            return httpx.Response(200, json=[])
        if path.endswith("/environments"):
            return httpx.Response(
                200,
                json=[{"id": 4, "name": "production", "state": "available", "tier": "production"}],
            )
        if path.endswith("/deployments"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 5,
                        "environment": {"id": 4, "name": "production"},
                        "sha": revision,
                        "status": "success",
                    }
                ],
            )
        if path.endswith("/releases"):
            return httpx.Response(
                200,
                json=[{"name": "Release 1", "tag_name": "v1", "commit": {"id": revision}}],
            )
        return httpx.Response(
            200,
            json={
                "id": 17,
                "path": "repo",
                "path_with_namespace": "group/repo",
                "namespace": "group",
                "default_branch": "main",
                "web_url": "https://gitlab.com/group/repo",
            },
        )

    collector = GitLabClient(
        credential=credential("gitlab", "gitlab.com", "private_token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    assert collector.list_authorized_repositories()[0]["id"] == 17
    result = collector.collect("group/repo").adapt()
    envelope = result.envelope

    assert result.warnings == ()
    assert envelope.pagination_complete is True
    assert envelope.snapshot.source_fingerprint.startswith("sha256:")
    assert envelope.source_objects[0].path == "src/app.py"
    assert envelope.exact_source_locators[0].exact_url.endswith(f"/-/blob/{revision}/src/app.py")
    assert envelope.tags[0].target_revision == revision
    assert envelope.ci_jobs[0].run_id == "9"
    assert envelope.environments[0].name == "production"
    assert envelope.deployments[0].revision == revision
    assert envelope.releases[0].tag_name == "v1"
    states = status_map(envelope)
    for capability in (
        Capability.TREE,
        Capability.BLOBS,
        Capability.TAGS,
        Capability.CI_JOBS,
        Capability.ENVIRONMENTS,
        Capability.DEPLOYMENTS,
        Capability.RELEASES,
        Capability.SOURCE_LINKS,
    ):
        assert states[capability] is CapabilityState.SUPPORTED


def test_bitbucket_collects_source_tags_steps_and_deployment_evidence() -> None:
    revision = "b" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/2.0/repositories/workspace":
            return httpx.Response(200, json={"values": [{"uuid": "repo-uuid", "slug": "repo"}]})
        if path.endswith("/commits"):
            return httpx.Response(200, json={"values": [{"hash": revision}]})
        if path.endswith("/refs/branches"):
            return httpx.Response(200, json={"values": [{"name": "main"}]})
        if path.endswith("/refs/tags"):
            return httpx.Response(
                200,
                json={"values": [{"name": "v1", "target": {"hash": revision}}]},
            )
        if f"/src/{revision}/" in path:
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "type": "commit_file",
                            "path": "src/app.ts",
                            "size": 12,
                            "commit": {"hash": revision},
                        }
                    ]
                },
            )
        if path.endswith("/pullrequests"):
            return httpx.Response(200, json={"values": []})
        if path.endswith("/pipelines/"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "uuid": "pipeline-1",
                            "target": {"commit": {"hash": revision}, "ref_name": "main"},
                            "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
                        }
                    ]
                },
            )
        if path.endswith("/pipelines/pipeline-1/steps/"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "uuid": "step-1",
                            "name": "test",
                            "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
                        }
                    ]
                },
            )
        if path.endswith("/issues"):
            return httpx.Response(404, json={"error": "disabled"})
        if path.endswith("/environments"):
            return httpx.Response(
                200,
                json={"values": [{"uuid": "env-1", "name": "production"}]},
            )
        if path.endswith("/deployments/"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "uuid": "dep-1",
                            "environment": {"uuid": "env-1", "name": "production"},
                            "pipeline": {"target": {"commit": {"hash": revision}}},
                            "state": {"name": "COMPLETED"},
                        }
                    ]
                },
            )
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
        credential=credential("bitbucket", "api.bitbucket.org"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    assert collector.list_authorized_repositories("workspace")[0]["uuid"] == "repo-uuid"
    result = collector.collect("workspace/repo").adapt()
    envelope = result.envelope

    assert result.warnings == ()
    assert envelope.source_objects[0].path == "src/app.ts"
    assert envelope.exact_source_locators[0].exact_url.endswith(f"/src/{revision}/src/app.ts")
    assert envelope.tags[0].name == "v1"
    assert envelope.ci_jobs[0].run_id == "pipeline-1"
    assert envelope.environments[0].native_id == "env-1"
    assert envelope.deployments[0].revision == revision
    assert status_map(envelope)[Capability.RELEASES] is CapabilityState.UNAVAILABLE_PROVIDER


def test_azure_collects_items_tags_timeline_and_environment_deployment_records() -> None:
    revision = "c" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = request.url.params
        if path.endswith("/_apis/git/repositories"):
            return httpx.Response(200, json={"value": [{"id": "azure-repo", "name": "repo"}]})
        if path.endswith("/commits"):
            return httpx.Response(200, json={"value": [{"commitId": revision}]})
        if path.endswith("/refs"):
            if query.get("filter") == "tags/":
                return httpx.Response(
                    200,
                    json={"value": [{"name": "refs/tags/v1", "objectId": revision}]},
                )
            return httpx.Response(200, json={"value": [{"name": "refs/heads/main"}]})
        if path.endswith("/items"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "path": "/src/app.cs",
                            "objectId": "d" * 40,
                            "gitObjectType": "blob",
                            "contentMetadata": {"fileSize": 15},
                        }
                    ]
                },
            )
        if path.endswith("/pullrequests"):
            return httpx.Response(200, json={"value": []})
        if path.endswith("/_apis/build/builds"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": 11,
                            "sourceVersion": revision,
                            "sourceBranch": "refs/heads/main",
                            "status": "completed",
                            "result": "succeeded",
                            "definition": {"name": "CI"},
                        }
                    ]
                },
            )
        if path.endswith("/_apis/build/builds/11/timeline"):
            return httpx.Response(
                200,
                json={"records": [{"id": "job-1", "name": "test", "type": "Job", "state": "completed", "result": "succeeded"}]},
            )
        if path.endswith("/_apis/distributedtask/environments"):
            return httpx.Response(200, json={"value": [{"id": 4, "name": "production"}]})
        if path.endswith("/environments/4/environmentdeploymentrecords"):
            return httpx.Response(
                200,
                json={"value": [{"id": 5, "environment": {"id": 4, "name": "production"}, "sourceVersion": revision, "result": "succeeded"}]},
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
        credential=credential("azure_devops", "dev.azure.com", "basic_token"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    assert collector.list_authorized_repositories()[0]["id"] == "azure-repo"
    result = collector.collect("azure-repo").adapt()
    envelope = result.envelope

    assert result.warnings == ()
    assert envelope.source_objects[0].path == "src/app.cs"
    assert "version=GC" + revision in envelope.exact_source_locators[0].exact_url
    assert envelope.tags[0].name == "v1"
    assert envelope.ci_jobs[0].run_id == "11"
    assert envelope.environments[0].name == "production"
    assert envelope.deployments[0].revision == revision
    assert status_map(envelope)[Capability.RELEASES] is CapabilityState.NOT_CONFIGURED


def test_pagination_loop_fails_closed() -> None:
    url = "https://api.bitbucket.org/2.0/repositories/workspace/repo/refs/tags"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"values": [], "next": url})

    collector = BitbucketCloudClient(
        credential=credential("bitbucket", "api.bitbucket.org"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(max_pages=10, base_delay_seconds=0, max_delay_seconds=0),
    )
    with pytest.raises(ProviderClientError, match="pagination_loop_detected"):
        collector._bitbucket_pages(url)


def test_rate_limit_headers_are_retained_without_credentials() -> None:
    revision = "e" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        headers = {"RateLimit-Remaining": "42", "RateLimit-Reset": "1234"}
        if path.endswith("/repository/commits"):
            return httpx.Response(200, headers=headers, json=[{"id": revision}])
        if path.endswith("/repository/tree"):
            return httpx.Response(
                200,
                headers=headers,
                json=[{"id": "f" * 40, "path": "src/app.py", "type": "blob"}],
            )
        if any(path.endswith(suffix) for suffix in (
            "/repository/branches", "/repository/tags", "/merge_requests", "/pipelines",
            "/issues", "/environments", "/deployments", "/releases",
        )):
            return httpx.Response(200, headers=headers, json=[])
        return httpx.Response(
            200,
            headers=headers,
            json={"id": 1, "path": "repo", "namespace": "group", "default_branch": "main"},
        )

    collector = GitLabClient(
        instance_url="https://gitlab.example.com",
        credential=None,
        credential_reference=build_reference(
            provider="gitlab",
            env_var="TOKEN",
            scheme="private_token",
            key_id="gitlab-anonymous-rate-limit-test",
            allowed_hosts=("gitlab.example.com",),
            scopes=("read",),
        ),
        access_mode="anonymous_public",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    collection = collector.collect("group/repo")
    assert collection.rate_limit_state == {"remaining": "42", "reset": "1234"}
    assert "secret" not in str(collection.rate_limit_state)
