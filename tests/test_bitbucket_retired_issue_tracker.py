"""Retired provider APIs are unavailable evidence, not empty successful evidence."""
from __future__ import annotations

import httpx
import pytest

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import (
    BitbucketCloudClient, GitLabClient, ProviderClientError, RetryPolicy,
)
from nico.provider_neutral_contract import Capability, CapabilityState

REVISION = "b" * 40


def _collector(*, issue_status: int = 410, pull_status: int = 200,
               root_status: int = 200, authenticated: bool = False):
    observed: list[httpx.Request] = []
    root = "/2.0/repositories/workspace/repo"

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.bitbucket.org"
        path = request.url.path
        if path == root:
            return httpx.Response(root_status, json={
                "uuid": "repo-uuid", "slug": "repo", "is_private": authenticated,
                "workspace": {"slug": "workspace"}, "mainbranch": {"name": "main"},
            })
        if path == f"{root}/commit/{REVISION}":
            return httpx.Response(200, json={"hash": REVISION})
        if path == f"{root}/src/{REVISION}/":
            return httpx.Response(200, json={"values": [{
                "path": "README.md", "type": "commit_file", "commit": {"hash": REVISION},
            }]})
        if path == f"{root}/pullrequests":
            return httpx.Response(pull_status, json={"values": [{
                "id": 7, "title": "Retained pull request", "state": "MERGED",
                "source": {"branch": {"name": "fix"}},
                "destination": {"branch": {"name": "main"}},
            }]})
        if path == f"{root}/issues":
            return httpx.Response(issue_status, json={"values": []})
        return httpx.Response(200, json={"values": []})

    reference = build_reference(
        provider="bitbucket", env_var="TOKEN", scheme="bearer", key_id="fixture",
        allowed_hosts=("api.bitbucket.org",), scopes=("read",),
    )
    credential = (EnvironmentCredentialResolver({"TOKEN": "fixture-not-a-secret"})
                  .resolve(reference) if authenticated else None)
    collector = BitbucketCloudClient(
        credential_reference=reference, credential=credential,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
    )
    return collector, observed


def _capability(collection, name: Capability):
    return next(item for item in collection.payload["capability_status"]
                if item["capability"] == name.value)


@pytest.mark.parametrize("authenticated", [False, True])
def test_retired_native_issue_tracker_remains_explicitly_unavailable(authenticated):
    collector, requests = _collector(authenticated=authenticated)
    collection = collector.collect("workspace/repo", revision=REVISION)
    status = _capability(collection, Capability.WORK_ITEMS)
    assert status["state"] == CapabilityState.UNAVAILABLE_PROVIDER.value
    assert status["reason"] == "work_items is unavailable from this provider or repository"
    assert status["reason"] in collection.collection_limitations
    assert collection.payload["issues"] == []
    assert collection.revision == REVISION
    assert collection.payload["pull_requests"][0]["id"] == 7
    adapted = collection.adapt()
    assert adapted.envelope.snapshot.revision == REVISION
    assert adapted.envelope.change_requests[0].native_id == "7"
    assert sum(request.url.path.endswith("/issues") for request in requests) == 1
    assert collection.credential_used is authenticated
    if not authenticated:
        assert all("authorization" not in request.headers for request in requests)


@pytest.mark.parametrize("http_status,expected", [
    (200, CapabilityState.SUPPORTED_EMPTY),
    (401, CapabilityState.UNAVAILABLE_AUTHENTICATION),
    (403, CapabilityState.UNAVAILABLE_AUTHENTICATION),
    (404, CapabilityState.UNAVAILABLE_PROVIDER),
    (429, CapabilityState.RATE_LIMITED),
    (500, CapabilityState.COLLECTION_FAILED),
])
def test_other_issue_api_outcomes_keep_their_existing_meaning(http_status, expected):
    collector, _ = _collector(issue_status=http_status)
    collection = collector.collect("workspace/repo", revision=REVISION)
    assert _capability(collection, Capability.WORK_ITEMS)["state"] == expected.value


def test_gone_pull_request_api_is_not_mistaken_for_retired_issue_tracker():
    collector, _ = _collector(pull_status=410)
    collection = collector.collect("workspace/repo", revision=REVISION)
    assert _capability(collection, Capability.CHANGE_REQUESTS)["state"] == "collection_failed"


def test_gone_required_repository_still_stops_acquisition():
    collector, _ = _collector(root_status=410)
    with pytest.raises(ProviderClientError) as caught:
        collector.collect("workspace/repo", revision=REVISION)
    assert caught.value.status_code == 410
    assert caught.value.code == "provider_request_failed"


def test_other_provider_http_gone_is_not_silently_reclassified():
    reference = build_reference(
        provider="gitlab", env_var="TOKEN", scheme="private_token", key_id="fixture",
        allowed_hosts=("gitlab.com",), scopes=("read",),
    )
    collector = GitLabClient(credential_reference=reference)
    try:
        collector._record_optional_failure(
            Capability.WORK_ITEMS,
            ProviderClientError("provider_request_failed", status_code=410),
        )
        assert collector._capability(Capability.WORK_ITEMS)["state"] == "collection_failed"
    finally:
        collector.close()
