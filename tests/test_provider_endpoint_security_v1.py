from __future__ import annotations

import pytest

from nico.provider_endpoint_security_v1 import (
    EndpointSecurityPolicy,
    ProviderEndpointSecurityError,
    assert_dns_pin_stable,
    self_managed_endpoint_policy,
    validate_provider_endpoint,
    validate_redirect_destination,
)


def resolver(*addresses: str):
    return lambda host, port: list(addresses)


def test_public_https_endpoint_is_dns_pinned_and_tls_verification_required() -> None:
    policy = EndpointSecurityPolicy(allowed_hosts=("git.example.com",))
    result = validate_provider_endpoint(
        "https://git.example.com/api/v4",
        policy,
        resolver=resolver("8.8.8.8"),
    )

    assert result.canonical_url == "https://git.example.com/api/v4"
    assert result.resolved_ips == ("8.8.8.8",)
    assert result.tls_verification_required is True


@pytest.mark.parametrize(
    "url,code",
    (
        ("http://git.example.com", "provider_endpoint_https_required"),
        ("https://user:secret@git.example.com", "provider_endpoint_embedded_credentials_prohibited"),
        ("https://other.example.com", "provider_endpoint_host_not_allowlisted"),
        ("https://git.example.com:8443", "provider_endpoint_port_not_allowlisted"),
        ("https://git.example.com?token=no", "provider_endpoint_query_prohibited"),
        ("https://git.example.com/#fragment", "provider_endpoint_fragment_prohibited"),
    ),
)
def test_endpoint_syntax_and_authority_fail_closed(url: str, code: str) -> None:
    policy = EndpointSecurityPolicy(allowed_hosts=("git.example.com",))
    with pytest.raises(ProviderEndpointSecurityError, match=code):
        validate_provider_endpoint(url, policy, resolver=resolver("8.8.8.8"))


def test_private_dns_answer_requires_explicit_cidr_allowlist() -> None:
    default_policy = self_managed_endpoint_policy(allowed_hosts=("git.internal.example",))
    with pytest.raises(ProviderEndpointSecurityError, match="private_ip_not_allowlisted"):
        validate_provider_endpoint(
            "https://git.internal.example",
            default_policy,
            resolver=resolver("10.20.30.40"),
        )

    allowed = self_managed_endpoint_policy(
        allowed_hosts=("git.internal.example",),
        allowed_private_cidrs=("10.20.30.0/24",),
    )
    result = validate_provider_endpoint(
        "https://git.internal.example",
        allowed,
        resolver=resolver("10.20.30.40"),
    )
    assert result.resolved_ips == ("10.20.30.40",)


@pytest.mark.parametrize("address", ("127.0.0.1", "169.254.1.1", "0.0.0.0", "224.0.0.1"))
def test_loopback_link_local_unspecified_and_multicast_are_never_allowed(address: str) -> None:
    policy = self_managed_endpoint_policy(
        allowed_hosts=("git.internal.example",),
        allowed_private_cidrs=("0.0.0.0/0",),
    )
    with pytest.raises(ProviderEndpointSecurityError, match="resolved_ip_unsafe"):
        validate_provider_endpoint(
            "https://git.internal.example",
            policy,
            resolver=resolver(address),
        )


def test_mixed_public_and_private_dns_answer_fails_closed() -> None:
    policy = EndpointSecurityPolicy(allowed_hosts=("git.example.com",))
    with pytest.raises(ProviderEndpointSecurityError, match="private_ip_not_allowlisted"):
        validate_provider_endpoint(
            "https://git.example.com",
            policy,
            resolver=resolver("8.8.8.8", "10.0.0.5"),
        )


def test_dns_rebinding_is_detected_between_pin_and_request() -> None:
    policy = EndpointSecurityPolicy(allowed_hosts=("git.example.com",))
    pinned = validate_provider_endpoint(
        "https://git.example.com",
        policy,
        resolver=resolver("8.8.8.8"),
    )
    with pytest.raises(ProviderEndpointSecurityError, match="dns_rebinding_detected"):
        assert_dns_pin_stable(
            pinned,
            "https://git.example.com",
            policy,
            resolver=resolver("1.1.1.1"),
        )


def test_redirect_is_revalidated_and_cross_origin_redirect_is_prohibited() -> None:
    policy = EndpointSecurityPolicy(
        allowed_hosts=("git.example.com", "evil.example.com"),
        max_redirects=2,
    )
    current = validate_provider_endpoint(
        "https://git.example.com/api",
        policy,
        resolver=resolver("8.8.8.8"),
    )
    same_origin = validate_redirect_destination(
        current,
        "/api/v2",
        policy,
        redirect_count=0,
        resolver=resolver("8.8.8.8"),
    )
    assert same_origin.host == "git.example.com"

    with pytest.raises(ProviderEndpointSecurityError, match="cross_origin_redirect_prohibited"):
        validate_redirect_destination(
            current,
            "https://evil.example.com/steal",
            policy,
            redirect_count=0,
            resolver=resolver("1.1.1.1"),
        )


def test_redirect_limit_and_tls_disable_configuration_fail_closed() -> None:
    policy = EndpointSecurityPolicy(allowed_hosts=("git.example.com",), max_redirects=1)
    current = validate_provider_endpoint(
        "https://git.example.com",
        policy,
        resolver=resolver("8.8.8.8"),
    )
    with pytest.raises(ProviderEndpointSecurityError, match="redirect_limit_exceeded"):
        validate_redirect_destination(
            current,
            "/next",
            policy,
            redirect_count=1,
            resolver=resolver("8.8.8.8"),
        )

    insecure = EndpointSecurityPolicy(
        allowed_hosts=("git.example.com",),
        tls_verification_required=False,
    )
    with pytest.raises(ProviderEndpointSecurityError, match="tls_verification_required"):
        validate_provider_endpoint(
            "https://git.example.com",
            insecure,
            resolver=resolver("8.8.8.8"),
        )
