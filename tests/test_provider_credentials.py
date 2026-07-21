from __future__ import annotations

import pytest

from nico.provider_credentials import (
    CredentialError,
    CredentialScheme,
    EnvironmentCredentialResolver,
    SecretValue,
    assert_url_allowed,
    authorization_headers,
    build_reference,
    validate_reference,
)


def test_secret_value_is_redacted_and_metadata_never_contains_token() -> None:
    reference = build_reference(
        provider="gitlab",
        env_var="NICO_GITLAB_TOKEN",
        scheme=CredentialScheme.PRIVATE_TOKEN,
        key_id="gitlab-prod-1",
        allowed_hosts=("gitlab.example.com",),
        scopes=("read_api", "read_repository"),
    )
    resolved = EnvironmentCredentialResolver({"NICO_GITLAB_TOKEN": "secret-token"}).resolve(reference)

    assert str(resolved.secret) == "<redacted>"
    assert repr(resolved.secret) == "SecretValue(<redacted>)"
    assert "secret-token" not in repr(resolved)
    assert "secret-token" not in str(resolved.safe_metadata())
    assert resolved.secret.matches("secret-token")


def test_reference_fails_closed_for_expired_or_unbounded_credentials() -> None:
    reference = build_reference(
        provider="bitbucket",
        env_var="NICO_BITBUCKET_TOKEN",
        scheme="bearer",
        key_id="bitbucket-1",
        allowed_hosts=(),
        expires_at="2020-01-01T00:00:00Z",
    )
    issues = validate_reference(reference)
    assert "provider_credential_allowed_hosts_required" in issues
    assert "provider_credential_expired" in issues

    with pytest.raises(CredentialError):
        EnvironmentCredentialResolver({"NICO_BITBUCKET_TOKEN": "token"}).resolve(reference)


def test_endpoint_must_be_https_and_host_allowlisted() -> None:
    reference = build_reference(
        provider="azure_devops",
        env_var="NICO_AZURE_TOKEN",
        scheme="basic_token",
        key_id="azure-1",
        allowed_hosts=("dev.azure.com",),
    )
    assert_url_allowed(reference, "https://dev.azure.com")
    with pytest.raises(CredentialError, match="provider_endpoint_https_required"):
        assert_url_allowed(reference, "http://dev.azure.com")
    with pytest.raises(CredentialError, match="provider_endpoint_host_not_allowed"):
        assert_url_allowed(reference, "https://evil.example.com")


def test_authorization_headers_are_provider_safe() -> None:
    gitlab_ref = build_reference(
        provider="gitlab",
        env_var="TOKEN",
        scheme="private_token",
        key_id="gitlab",
        allowed_hosts=("gitlab.com",),
    )
    gitlab = EnvironmentCredentialResolver({"TOKEN": "abc"}).resolve(gitlab_ref)
    assert authorization_headers(gitlab) == {"PRIVATE-TOKEN": "abc"}

    azure_ref = build_reference(
        provider="azure_devops",
        env_var="AZURE",
        scheme="basic_token",
        key_id="azure",
        allowed_hosts=("dev.azure.com",),
    )
    azure = EnvironmentCredentialResolver({"AZURE": "pat"}).resolve(azure_ref)
    headers = authorization_headers(azure)
    assert headers["Authorization"].startswith("Basic ")
    assert "pat" not in headers["Authorization"]


def test_missing_environment_secret_is_not_treated_as_ready() -> None:
    reference = build_reference(
        provider="gitlab",
        env_var="MISSING",
        scheme="private_token",
        key_id="gitlab",
        allowed_hosts=("gitlab.com",),
    )
    with pytest.raises(CredentialError, match="provider_credential_not_configured"):
        EnvironmentCredentialResolver({}).resolve(reference)


def test_secret_wrapper_rejects_empty_values() -> None:
    with pytest.raises(CredentialError, match="provider_credential_empty"):
        SecretValue("")
