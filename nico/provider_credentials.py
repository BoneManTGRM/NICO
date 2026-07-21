from __future__ import annotations

import base64
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping
from urllib.parse import urlparse

from nico.provider_neutral_contract import ProviderKind, normalize_provider


class CredentialError(RuntimeError):
    """Raised when a provider credential cannot be used safely."""


class CredentialScheme(str, Enum):
    PRIVATE_TOKEN = "private_token"
    BEARER = "bearer"
    BASIC_TOKEN = "basic_token"


class SecretValue:
    """Small redacting wrapper that prevents accidental string serialization."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        normalized = str(value or "")
        if not normalized:
            raise CredentialError("provider_credential_empty")
        self.__value = normalized

    def reveal(self) -> str:
        return self.__value

    def matches(self, candidate: str) -> bool:
        return hmac.compare_digest(self.__value, str(candidate or ""))

    def __repr__(self) -> str:
        return "SecretValue(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


@dataclass(frozen=True)
class CredentialReference:
    provider: ProviderKind
    env_var: str
    scheme: CredentialScheme
    key_id: str
    allowed_hosts: tuple[str, ...]
    scopes: tuple[str, ...] = ()
    version: str = "v1"
    expires_at: str = ""


@dataclass(frozen=True)
class ResolvedCredential:
    reference: CredentialReference
    secret: SecretValue
    resolved_at: str

    def safe_metadata(self) -> dict[str, object]:
        return {
            "provider": self.reference.provider.value,
            "env_var": self.reference.env_var,
            "scheme": self.reference.scheme.value,
            "key_id": self.reference.key_id,
            "allowed_hosts": list(self.reference.allowed_hosts),
            "scopes": list(self.reference.scopes),
            "version": self.reference.version,
            "expires_at": self.reference.expires_at,
            "resolved_at": self.resolved_at,
            "secret_present": True,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError as exc:
        raise CredentialError("provider_credential_expiry_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_reference(reference: CredentialReference) -> list[str]:
    issues: list[str] = []
    if not reference.env_var or not reference.env_var.replace("_", "").isalnum():
        issues.append("provider_credential_env_var_invalid")
    if not reference.key_id:
        issues.append("provider_credential_key_id_required")
    if not reference.allowed_hosts:
        issues.append("provider_credential_allowed_hosts_required")
    for host in reference.allowed_hosts:
        normalized = str(host or "").strip().lower()
        if not normalized or "://" in normalized or "/" in normalized:
            issues.append("provider_credential_allowed_host_invalid")
            break
    expires = _parse_time(reference.expires_at)
    if expires is not None and expires <= datetime.now(timezone.utc):
        issues.append("provider_credential_expired")
    return issues


class EnvironmentCredentialResolver:
    """Resolve secret references without ever persisting raw credential material."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def resolve(self, reference: CredentialReference) -> ResolvedCredential:
        issues = validate_reference(reference)
        if issues:
            raise CredentialError(",".join(issues))
        value = self._environment.get(reference.env_var, "")
        if not value:
            raise CredentialError("provider_credential_not_configured")
        return ResolvedCredential(
            reference=reference,
            secret=SecretValue(value),
            resolved_at=_utc_now(),
        )


def assert_url_allowed(reference: CredentialReference, url: str) -> None:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise CredentialError("provider_endpoint_https_required")
    allowed = {item.lower() for item in reference.allowed_hosts}
    if host not in allowed:
        raise CredentialError("provider_endpoint_host_not_allowed")


def authorization_headers(credential: ResolvedCredential) -> dict[str, str]:
    token = credential.secret.reveal()
    scheme = credential.reference.scheme
    if scheme is CredentialScheme.PRIVATE_TOKEN:
        return {"PRIVATE-TOKEN": token}
    if scheme is CredentialScheme.BEARER:
        return {"Authorization": f"Bearer {token}"}
    if scheme is CredentialScheme.BASIC_TOKEN:
        encoded = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    raise CredentialError("provider_credential_scheme_unsupported")


def build_reference(
    *,
    provider: ProviderKind | str,
    env_var: str,
    scheme: CredentialScheme | str,
    key_id: str,
    allowed_hosts: tuple[str, ...],
    scopes: tuple[str, ...] = (),
    version: str = "v1",
    expires_at: str = "",
) -> CredentialReference:
    return CredentialReference(
        provider=provider if isinstance(provider, ProviderKind) else normalize_provider(provider),
        env_var=str(env_var or "").strip(),
        scheme=scheme if isinstance(scheme, CredentialScheme) else CredentialScheme(str(scheme)),
        key_id=str(key_id or "").strip(),
        allowed_hosts=tuple(str(item).strip().lower() for item in allowed_hosts if str(item).strip()),
        scopes=tuple(str(item).strip() for item in scopes if str(item).strip()),
        version=str(version or "v1").strip(),
        expires_at=str(expires_at or "").strip(),
    )


__all__ = [
    "CredentialError",
    "CredentialReference",
    "CredentialScheme",
    "EnvironmentCredentialResolver",
    "ResolvedCredential",
    "SecretValue",
    "assert_url_allowed",
    "authorization_headers",
    "build_reference",
    "validate_reference",
]
