from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

VERSION = "nico.provider-endpoint-security.v1"


class ProviderEndpointSecurityError(ValueError):
    """Fail-closed provider endpoint validation error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EndpointSecurityPolicy:
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...] = (443,)
    allowed_private_cidrs: tuple[str, ...] = ()
    require_https: bool = True
    allow_query: bool = False
    max_redirects: int = 3
    tls_verification_required: bool = True

    def validate(self) -> None:
        if not self.allowed_hosts:
            raise ProviderEndpointSecurityError("provider_endpoint_allowed_hosts_required")
        normalized_hosts = tuple(_normalize_host(item) for item in self.allowed_hosts)
        if any(not item for item in normalized_hosts):
            raise ProviderEndpointSecurityError("provider_endpoint_allowed_host_invalid")
        if not self.allowed_ports or any(int(port) < 1 or int(port) > 65535 for port in self.allowed_ports):
            raise ProviderEndpointSecurityError("provider_endpoint_allowed_port_invalid")
        if self.max_redirects < 0 or self.max_redirects > 10:
            raise ProviderEndpointSecurityError("provider_endpoint_redirect_limit_invalid")
        for raw in self.allowed_private_cidrs:
            try:
                network = ipaddress.ip_network(str(raw), strict=False)
            except ValueError as exc:
                raise ProviderEndpointSecurityError("provider_endpoint_private_cidr_invalid") from exc
            if network.is_loopback or network.is_link_local or network.is_multicast or network.is_unspecified:
                raise ProviderEndpointSecurityError("provider_endpoint_private_cidr_unsafe")
        if not self.tls_verification_required:
            raise ProviderEndpointSecurityError("provider_endpoint_tls_verification_required")


@dataclass(frozen=True)
class EndpointValidation:
    canonical_url: str
    host: str
    port: int
    resolved_ips: tuple[str, ...]
    tls_verification_required: bool


Resolver = Callable[[str, int], Sequence[object]]


def _normalize_host(value: str) -> str:
    raw = str(value or "").strip().rstrip(".").casefold()
    if not raw or "://" in raw or "/" in raw or "@" in raw:
        return ""
    try:
        return raw.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def _default_resolver(host: str, port: int) -> Sequence[object]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def _resolved_addresses(host: str, port: int, resolver: Resolver) -> tuple[ipaddress._BaseAddress, ...]:
    try:
        records = resolver(host, port)
    except OSError as exc:
        raise ProviderEndpointSecurityError("provider_endpoint_dns_resolution_failed") from exc
    addresses: set[ipaddress._BaseAddress] = set()
    for record in records:
        candidate = ""
        if isinstance(record, str):
            candidate = record
        elif isinstance(record, (tuple, list)):
            if len(record) >= 5 and isinstance(record[4], (tuple, list)) and record[4]:
                candidate = str(record[4][0])
            elif record:
                candidate = str(record[0])
        if not candidate:
            continue
        try:
            addresses.add(ipaddress.ip_address(candidate.split("%", 1)[0]))
        except ValueError:
            continue
    if not addresses:
        raise ProviderEndpointSecurityError("provider_endpoint_dns_resolution_empty")
    return tuple(sorted(addresses, key=lambda value: (value.version, int(value))))


def _private_networks(policy: EndpointSecurityPolicy) -> tuple[ipaddress._BaseNetwork, ...]:
    return tuple(ipaddress.ip_network(item, strict=False) for item in policy.allowed_private_cidrs)


def _assert_address_allowed(address: ipaddress._BaseAddress, policy: EndpointSecurityPolicy) -> None:
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        raise ProviderEndpointSecurityError("provider_endpoint_resolved_ip_unsafe")
    if address.is_private:
        networks = _private_networks(policy)
        if not networks or not any(address in network for network in networks if network.version == address.version):
            raise ProviderEndpointSecurityError("provider_endpoint_private_ip_not_allowlisted")


def validate_provider_endpoint(
    url: str,
    policy: EndpointSecurityPolicy,
    *,
    resolver: Resolver | None = None,
) -> EndpointValidation:
    """Validate and DNS-pin a provider endpoint before credentials or requests are used."""

    policy.validate()
    raw = str(url or "").strip()
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.hostname:
        raise ProviderEndpointSecurityError("provider_endpoint_url_invalid")
    if parsed.username or parsed.password:
        raise ProviderEndpointSecurityError("provider_endpoint_embedded_credentials_prohibited")
    if policy.require_https and parsed.scheme.casefold() != "https":
        raise ProviderEndpointSecurityError("provider_endpoint_https_required")
    if parsed.fragment:
        raise ProviderEndpointSecurityError("provider_endpoint_fragment_prohibited")
    if parsed.query and not policy.allow_query:
        raise ProviderEndpointSecurityError("provider_endpoint_query_prohibited")
    host = _normalize_host(parsed.hostname)
    if not host:
        raise ProviderEndpointSecurityError("provider_endpoint_host_invalid")
    allowed_hosts = {_normalize_host(item) for item in policy.allowed_hosts}
    if host not in allowed_hosts:
        raise ProviderEndpointSecurityError("provider_endpoint_host_not_allowlisted")
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as exc:
        raise ProviderEndpointSecurityError("provider_endpoint_port_invalid") from exc
    if port not in {int(value) for value in policy.allowed_ports}:
        raise ProviderEndpointSecurityError("provider_endpoint_port_not_allowlisted")
    active_resolver = resolver or _default_resolver
    addresses = _resolved_addresses(host, port, active_resolver)
    for address in addresses:
        _assert_address_allowed(address, policy)
    netloc = host if port == 443 else f"{host}:{port}"
    canonical = urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "", parsed.query if policy.allow_query else "", ""))
    return EndpointValidation(
        canonical_url=canonical,
        host=host,
        port=port,
        resolved_ips=tuple(str(item) for item in addresses),
        tls_verification_required=True,
    )


def assert_dns_pin_stable(
    pinned: EndpointValidation,
    url: str,
    policy: EndpointSecurityPolicy,
    *,
    resolver: Resolver | None = None,
) -> EndpointValidation:
    """Reject DNS rebinding between validation and a later request/redirect."""

    current = validate_provider_endpoint(url, policy, resolver=resolver)
    if current.host != pinned.host or current.port != pinned.port:
        raise ProviderEndpointSecurityError("provider_endpoint_dns_pin_identity_changed")
    if set(current.resolved_ips) != set(pinned.resolved_ips):
        raise ProviderEndpointSecurityError("provider_endpoint_dns_rebinding_detected")
    return current


def validate_redirect_destination(
    current: EndpointValidation,
    location: str,
    policy: EndpointSecurityPolicy,
    *,
    redirect_count: int,
    resolver: Resolver | None = None,
) -> EndpointValidation:
    if redirect_count < 0 or redirect_count >= policy.max_redirects:
        raise ProviderEndpointSecurityError("provider_endpoint_redirect_limit_exceeded")
    destination = urljoin(current.canonical_url, str(location or ""))
    validated = validate_provider_endpoint(destination, policy, resolver=resolver)
    if validated.host != current.host or validated.port != current.port:
        raise ProviderEndpointSecurityError("provider_endpoint_cross_origin_redirect_prohibited")
    return validated


def self_managed_endpoint_policy(
    *,
    allowed_hosts: Iterable[str],
    allowed_private_cidrs: Iterable[str] = (),
    allowed_ports: Iterable[int] = (443,),
) -> EndpointSecurityPolicy:
    """Create the explicit allowlist required for a self-managed/server provider."""

    policy = EndpointSecurityPolicy(
        allowed_hosts=tuple(str(item) for item in allowed_hosts),
        allowed_ports=tuple(int(item) for item in allowed_ports),
        allowed_private_cidrs=tuple(str(item) for item in allowed_private_cidrs),
        require_https=True,
        allow_query=False,
        max_redirects=3,
        tls_verification_required=True,
    )
    policy.validate()
    return policy


__all__ = [
    "EndpointSecurityPolicy",
    "EndpointValidation",
    "ProviderEndpointSecurityError",
    "VERSION",
    "assert_dns_pin_stable",
    "self_managed_endpoint_policy",
    "validate_provider_endpoint",
    "validate_redirect_destination",
]
