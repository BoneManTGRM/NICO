from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from nico.provider_live_clients import ProviderClientError, RetryPolicy
from scripts import provider_live_acceptance as acceptance


def github_client(responses, *, mode="anonymous_public", credential=None, attempts=3):
    requests, delays = [], []

    def respond(request):
        requests.append(request)
        return responses[min(len(requests) - 1, len(responses) - 1)]

    http = httpx.Client(transport=httpx.MockTransport(respond))
    client = acceptance.GitHubAcceptanceClient(
        credential_reference=acceptance._credential_reference("github"),
        credential=credential,
        client=http,
        retry_policy=RetryPolicy(max_attempts=attempts, max_delay_seconds=30),
        access_mode=mode,
        sleeper=delays.append,
        clock=lambda: 1000.0,
    )
    return client, http, requests, delays


def test_primary_rate_limit_preserves_evidence_without_early_retry_or_auth_fallback():
    reference = acceptance._credential_reference("github")
    credential = acceptance.EnvironmentCredentialResolver(
        {reference.env_var: "owned-fixture-credential-never-export"}
    ).resolve(reference)
    response = httpx.Response(403, headers={
        "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1400",
        "x-ratelimit-limit": "60", "x-ratelimit-used": "60",
        "set-cookie": "private-value", "x-unrelated": "private-value",
    }, json={"message": "API rate limit exceeded for private-address"})
    client, http, requests, delays = github_client(
        [response], mode="auto", credential=credential
    )
    with http, pytest.raises(ProviderClientError) as caught:
        client._get("https://api.github.com/repos/octocat/Hello-World", required=True)
    error = caught.value
    assert error.code == "provider_rate_limited"
    assert error.status_code == 403
    assert error.retry_after_seconds == 401
    assert error.rate_limit_state == {"remaining": 0, "reset": 1400, "limit": 60, "used": 60}
    assert len(requests) == 1 and delays == []
    assert client.credential_used is False
    assert all("authorization" not in request.headers for request in requests)
    assert "private" not in json.dumps(error.rate_limit_state)


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limit_honors_server_delay_before_bounded_retry(status):
    client, http, requests, delays = github_client([
        httpx.Response(status, headers={"retry-after": "3"}, json={}),
        httpx.Response(200, json={"id": 1}),
    ])
    with http:
        payload, _ = client._get("https://api.github.com/repos/octocat/Hello-World")
    assert payload == {"id": 1}
    assert len(requests) == 2 and delays == [3.0]
    assert all("authorization" not in request.headers for request in requests)


@pytest.mark.parametrize("headers,body", [
    ({}, {"message": "You have exceeded a secondary rate limit."}),
    ({"x-ratelimit-remaining": "0"}, {}),
    ({"retry-after": "100"}, {}),
])
def test_rate_limit_without_an_affordable_safe_wait_fails_after_one_request(headers, body):
    client, http, requests, delays = github_client([httpx.Response(403, headers=headers, json=body)])
    with http, pytest.raises(ProviderClientError, match="^provider_rate_limited$"):
        client._get("https://api.github.com/repos/octocat/Hello-World")
    assert len(requests) == 1 and delays == []


@pytest.mark.parametrize("status", [401, 403])
def test_real_access_denial_is_not_reclassified_as_rate_limiting(status):
    client, http, requests, delays = github_client([httpx.Response(status, json={})])
    with http, pytest.raises(ProviderClientError) as caught:
        client._get("https://api.github.com/repos/octocat/Hello-World")
    assert caught.value.code == "provider_read_only_authentication_required"
    assert caught.value.status_code == status
    assert len(requests) == 1 and delays == []


def test_retry_budget_is_not_reset_by_repeated_throttling():
    client, http, requests, delays = github_client([
        httpx.Response(429, headers={"retry-after": "2"}, json={})
    ])
    with http, pytest.raises(ProviderClientError, match="^provider_rate_limited$"):
        client._get("https://api.github.com/repos/octocat/Hello-World")
    assert len(requests) == 3 and delays == [2.0, 4.0]


@pytest.mark.parametrize("value", ["nan", "inf", "-2", "not-a-number"])
def test_invalid_retry_header_cannot_trigger_early_or_unbounded_sleep(value):
    client, http, requests, delays = github_client([
        httpx.Response(429, headers={"retry-after": value}, json={})
    ])
    with http, pytest.raises(ProviderClientError, match="^provider_rate_limited$") as caught:
        client._get("https://api.github.com/repos/octocat/Hello-World")
    assert len(requests) == 1 and delays == []
    assert caught.value.retry_after_seconds is None


def test_malformed_explicit_retry_signal_never_resolves_an_auto_credential():
    reference = acceptance._credential_reference("github")
    credential = acceptance.EnvironmentCredentialResolver(
        {reference.env_var: "owned-fixture-credential"}
    ).resolve(reference)
    client, http, requests, delays = github_client([
        httpx.Response(403, headers={"retry-after": "unparseable"}, json={})
    ], mode="auto", credential=credential)
    with http, pytest.raises(ProviderClientError, match="^provider_rate_limited$") as caught:
        client._get("https://api.github.com/repos/octocat/Hello-World", required=True)
    assert len(requests) == 1 and delays == []
    assert client.credential_used is False
    assert "authorization" not in requests[0].headers
    assert caught.value.retry_after_seconds is None


def test_failed_artifact_retains_status_without_claiming_acceptance_or_copying_raw_values():
    error = ProviderClientError("provider_rate_limited", status_code=403,
                               retryable=True, retry_after_seconds=401)
    error.rate_limit_state = {"remaining": 0, "reset": 1400,
                              "limit": "private-value", "set-cookie": "private-value"}
    args = SimpleNamespace(provider="github", repository="octocat/Hello-World",
                           access_mode="anonymous_public", expected_outcome="success",
                           workflow_sha="a" * 40, workflow_run_id="1", workflow_run_attempt="1")
    result = acceptance._failed_payload(args, error)
    assert result["http_status"] == 403
    assert result["retryable"] is True
    assert result["retry_after_seconds"] == 401
    assert result["rate_limit_state"] == {"remaining": 0, "reset": 1400}
    assert result["status"] == "failed"
    assert result["client_delivery_allowed"] is False
    assert result["human_approval_proven"] is False
    assert "private-value" not in json.dumps(result)
    assert acceptance._error_code(error) == "provider_acceptance_unexpected_provider_failure"


def test_cli_failure_artifact_contains_actual_response_status_and_no_response_body(monkeypatch, tmp_path):
    client, http, _, _ = github_client([
        httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1400"},
                       json={"message": "private-response-text"})
    ])

    def run(**kwargs):
        with http:
            return client.collect("octocat/Hello-World")

    out = tmp_path / "failure.json"
    monkeypatch.setattr(acceptance, "run_acceptance", run)
    monkeypatch.setattr(sys, "argv", ["provider_live_acceptance", "--repository",
                                   "octocat/Hello-World", "--output", str(out)])
    assert acceptance.main() == 1
    result = json.loads(out.read_text())
    assert result["status"] == "failed" and result["http_status"] == 403
    assert result["error_code"] == "provider_rate_limited"
    assert result["rate_limit_state"] == {"remaining": 0, "reset": 1400}
    assert "private-response-text" not in out.read_text()


def test_real_auth_denial_still_allows_previously_authorized_auto_fallback():
    reference = acceptance._credential_reference("github")
    credential = acceptance.EnvironmentCredentialResolver(
        {reference.env_var: "owned-fixture-credential"}
    ).resolve(reference)
    client, http, requests, delays = github_client([
        httpx.Response(401, json={}), httpx.Response(200, json={"id": 1})
    ], mode="auto", credential=credential)
    with http:
        result, _ = client._get("https://api.github.com/repos/octocat/Hello-World", required=True)
    assert result == {"id": 1}
    assert "authorization" not in requests[0].headers
    assert "authorization" in requests[1].headers
    assert client.credential_used is True and delays == []
