from __future__ import annotations

import httpx

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_enterprise_clients import BitbucketDataCenterClient
from nico.provider_live_clients import RetryPolicy


def _credential():
    reference = build_reference(
        provider="bitbucket",
        env_var="TOKEN",
        scheme="bearer",
        key_id="bitbucket-dc-test",
        allowed_hosts=("bitbucket.example.com",),
        scopes=("repository:read", "pullrequest:read", "build-status:read"),
    )
    return EnvironmentCredentialResolver({"TOKEN": "secret"}).resolve(reference)


def test_bitbucket_data_center_collects_paginated_exact_snapshot() -> None:
    branch_pages = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal branch_pages
        assert request.headers["Authorization"] == "Bearer secret"
        path = request.url.path
        if path.endswith("/branches/default"):
            return httpx.Response(200, json={"id": "refs/heads/main", "displayId": "main"})
        if path.endswith("/commits"):
            return httpx.Response(
                200,
                json={"values": [{"id": "a" * 40}], "isLastPage": True},
            )
        if path.endswith("/branches"):
            branch_pages += 1
            if branch_pages == 1:
                return httpx.Response(
                    200,
                    json={
                        "values": [{"id": "refs/heads/main", "displayId": "main"}],
                        "isLastPage": False,
                        "nextPageStart": 100,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "values": [{"id": "refs/heads/release", "displayId": "release"}],
                    "isLastPage": True,
                },
            )
        if path.endswith("/pull-requests"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 7,
                            "title": "Repair",
                            "state": "MERGED",
                            "fromRef": {"displayId": "repair"},
                            "toRef": {"displayId": "main"},
                            "author": {"user": {"displayName": "Developer"}},
                            "createdDate": 1,
                            "updatedDate": 2,
                        }
                    ],
                    "isLastPage": True,
                },
            )
        if "/rest/build-status/1.0/commits/" in path:
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "key": "CI-1",
                            "name": "CI",
                            "state": "SUCCESSFUL",
                            "url": "https://ci.example.com/1",
                            "dateAdded": 3,
                        }
                    ],
                    "isLastPage": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 44,
                "slug": "repo",
                "name": "Repo",
                "project": {"key": "PROJ"},
            },
        )

    collector = BitbucketDataCenterClient(
        instance_url="https://bitbucket.example.com",
        credential=_credential(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
    )
    collection = collector.collect("PROJ/repo")
    adapted = collection.adapt()

    assert collection.revision == "a" * 40
    assert collection.pages_fetched == 4
    assert adapted.warnings == ()
    assert adapted.envelope.identity.repository_id == "44"
    assert adapted.envelope.change_requests[0].native_id == "7"
    assert adapted.envelope.ci_runs[0].revision == "a" * 40
    assert branch_pages == 2
