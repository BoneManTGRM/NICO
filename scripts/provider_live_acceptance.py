from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, urlparse

import httpx

from nico.provider_credentials import (
    CredentialReference,
    EnvironmentCredentialResolver,
    ProviderAccessMode,
    ResolvedCredential,
    assert_url_allowed,
    authorization_headers,
    build_reference,
)
from nico.provider_live_clients import (
    AzureDevOpsClient,
    BitbucketCloudClient,
    GitLabClient,
    ProviderClientError,
    RetryPolicy,
)
from nico.provider_neutral_contract import (
    CanonicalExactSourceLocator,
    CanonicalSourceObject,
    Capability,
    CapabilityState,
    ProviderAccess,
    ProviderCapabilityStatus,
    ProviderEvidenceEnvelope,
    ProviderIdentity,
    ProviderKind,
    SnapshotIdentity,
    validate_provider_envelope,
)
from nico.provider_payload_adapters import AdapterResult
from nico.provider_support_policy_v1 import ProviderSupportMaturity


ARTIFACT_SCHEMA = "nico.provider_live_acceptance.v3"
AUTO = ProviderAccessMode.AUTO.value
ANONYMOUS_PUBLIC = "anonymous_public"
AUTHENTICATED_READ_ONLY = "authenticated_read_only"
EXPECTED_SUCCESS = "success"
EXPECTED_AUTHENTICATION_REQUIRED = "authentication_required"

OFFICIAL_ENDPOINTS = {
    "github": "https://api.github.com",
    "gitlab": "https://gitlab.com",
    "bitbucket_cloud": "https://api.bitbucket.org",
    "azure_devops": "https://dev.azure.com",
}
PROVIDER_CREDENTIAL_ENV = {
    "github": "NICO_GITHUB_TOKEN",
    "gitlab": "NICO_GITLAB_TOKEN",
    "bitbucket_cloud": "NICO_BITBUCKET_CLOUD_TOKEN",
    "azure_devops": "NICO_AZURE_DEVOPS_TOKEN",
}
# Anonymous proof must not inherit provider credentials from a shell or runner configuration.
PROVIDER_CREDENTIAL_ALIASES = (
    "NICO_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
    "NICO_GITLAB_TOKEN", "GITLAB_TOKEN",
    "NICO_BITBUCKET_CLOUD_TOKEN", "BITBUCKET_TOKEN",
    "NICO_AZURE_DEVOPS_TOKEN", "AZURE_DEVOPS_TOKEN", "AZURE_DEVOPS_EXT_PAT",
    "SYSTEM_ACCESSTOKEN",
)
FORBIDDEN_ANONYMOUS_HEADERS = frozenset(
    {"authorization", "private-token", "proxy-authorization", "cookie", "x-auth-token"}
)
SECRET_QUERY_NAMES = frozenset(
    {"access_token", "api_key", "apikey", "authorization", "private_token", "sig", "token"}
)
AUTHENTICATION_REQUIRED_CODES = frozenset(
    {
        "provider_authentication_required",
        "provider_read_only_authentication_required",
        "provider_repository_not_publicly_accessible",
        "provider_required_source_evidence_unavailable",
        "provider_required_source_unavailable",
        "read_only_authentication_required",
    }
)
SAFE_CAPABILITY_STATES = frozenset(
    {
        "collected", "supported", "supported_empty", "supported_limited",
        "unavailable_authentication", "unavailable_permission", "unavailable_provider",
        "unavailable_repository_configuration", "rate_limited", "collection_failed",
        "not_applicable", "not_assessed", "not_configured", "unsupported",
    }
)
LIMITATION_STATES = SAFE_CAPABILITY_STATES - {"collected", "supported", "supported_empty"}
SECRET_PATTERN = re.compile(
    r"(?i)(?:authorization|private-token|access[_-]?token|api[_-]?key|password)\s*[:=]\s*"
    r"(?:bearer\s+|basic\s+)?[A-Za-z0-9_+./=-]{12,}"
)


class LiveAcceptanceError(RuntimeError):
    pass


def _text(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip()


def _utc_now() -> str:
    return httpx.codes.__class__.__module__ and __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat().replace("+00:00", "Z")


def assert_anonymous_environment_clean() -> None:
    if any(_text(os.environ.get(name)) for name in PROVIDER_CREDENTIAL_ALIASES):
        raise LiveAcceptanceError("provider_acceptance_anonymous_credential_resolved")


def _official_host(provider: str) -> str:
    return _text(urlparse(OFFICIAL_ENDPOINTS[provider]).hostname).lower()


def _credential_reference(provider: str) -> CredentialReference:
    schemes = {
        "github": "bearer",
        "gitlab": "private_token",
        "bitbucket_cloud": "bearer",
        "azure_devops": "basic_token",
    }
    scopes = {
        "github": ("repo:read",),
        "gitlab": ("read_api", "read_repository"),
        "bitbucket_cloud": ("repository:read", "pullrequest:read", "pipeline:read"),
        "azure_devops": ("vso.code", "vso.build", "vso.work"),
    }
    reference = build_reference(
        provider="bitbucket" if provider == "bitbucket_cloud" else provider,
        env_var=PROVIDER_CREDENTIAL_ENV[provider],
        scheme=schemes[provider],
        key_id=f"live-{provider.replace('_', '-')}",
        allowed_hosts=(_official_host(provider),),
        scopes=scopes[provider],
    )
    return reference


def _credential(provider: str, *, optional: bool = False) -> ResolvedCredential | None:
    reference = _credential_reference(provider)
    resolver = EnvironmentCredentialResolver()
    if optional:
        return resolver.resolve_optional(reference)
    return resolver.resolve(reference)


@dataclass
class RequestContractAudit:
    expected_access_mode: str
    request_count: int = 0
    approved_hosts: set[str] | None = None
    authorization_header_observed: bool = False
    cookie_header_observed: bool = False
    secret_query_observed: bool = False

    def __post_init__(self) -> None:
        self.approved_hosts = set()

    def inspect(self, request: httpx.Request) -> None:
        self.request_count += 1
        host = _text(request.url.host).lower()
        if host:
            assert self.approved_hosts is not None
            self.approved_hosts.add(host)
        headers = {name.lower() for name in request.headers}
        auth_headers = {"authorization", "private-token", "proxy-authorization", "x-auth-token"}
        if headers & auth_headers:
            self.authorization_header_observed = True
        if "cookie" in headers:
            self.cookie_header_observed = True
        query_names = {name.lower() for name, _ in parse_qsl(request.url.query.decode("utf-8"))}
        if query_names & SECRET_QUERY_NAMES:
            self.secret_query_observed = True
        if self.expected_access_mode == ANONYMOUS_PUBLIC and headers & FORBIDDEN_ANONYMOUS_HEADERS:
            raise LiveAcceptanceError("provider_acceptance_anonymous_auth_header_sent")
        if self.secret_query_observed:
            raise LiveAcceptanceError("provider_acceptance_secret_query_sent")

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "approved_hosts": sorted(self.approved_hosts or ()),
            "authorization_header_observed": self.authorization_header_observed,
            "cookie_header_observed": self.cookie_header_observed,
            "secret_query_observed": self.secret_query_observed,
        }


@dataclass
class CollectorHandle:
    collector: Any
    http_client: httpx.Client | None
    request_audit: RequestContractAudit
    credential: ResolvedCredential | None
    credential_reference: CredentialReference

    def close(self) -> None:
        self.collector.close()
        if self.http_client is not None:
            self.http_client.close()


@dataclass(frozen=True)
class AcceptanceCollection:
    provider: ProviderKind
    repository_id: str
    revision: str
    pages_fetched: int
    requests_made: int
    envelope: ProviderEvidenceEnvelope
    warnings: tuple[str, ...] = ()

    def adapt(self) -> AdapterResult:
        return AdapterResult(self.envelope, self.warnings)


class GitHubAcceptanceClient:
    provider = ProviderKind.GITHUB

    def __init__(
        self,
        *,
        instance_url: str = OFFICIAL_ENDPOINTS["github"],
        credential: ResolvedCredential | None = None,
        credential_reference: CredentialReference,
        client: httpx.Client,
        retry_policy: RetryPolicy,
        access_mode: ProviderAccessMode | str = ANONYMOUS_PUBLIC,
    ) -> None:
        self.base_url = str(instance_url or "").rstrip("/")
        self.credential = credential
        self.credential_reference = credential_reference
        self._client = client
        self.retry_policy = retry_policy
        self.retry_policy.validate()
        self.requested_access_mode = (
            access_mode if isinstance(access_mode, ProviderAccessMode) else ProviderAccessMode(str(access_mode))
        )
        if self.requested_access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY and credential is None:
            raise LiveAcceptanceError("provider_credential_not_configured")
        self._active_credential = (
            credential if self.requested_access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY else None
        )
        self._auth_fallback_attempted = False
        self.requests_made = 0
        self.pages_fetched = 0
        self.pagination_complete = True
        self.collection_limitations: list[str] = []

    @property
    def credential_used(self) -> bool:
        return self._active_credential is not None

    @property
    def actual_access_mode(self) -> ProviderAccessMode:
        return (
            ProviderAccessMode.AUTHENTICATED_READ_ONLY
            if self.credential_used
            else ProviderAccessMode.ANONYMOUS_PUBLIC
        )

    def close(self) -> None:
        return None

    def _delay(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None and retry_after >= 0:
            return min(self.retry_policy.max_delay_seconds, retry_after)
        return min(
            self.retry_policy.max_delay_seconds,
            self.retry_policy.base_delay_seconds * (2 ** max(0, attempt - 1)),
        )

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if value in (None, ""):
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    def _get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        required: bool = False,
    ) -> tuple[Any, httpx.Headers]:
        assert_url_allowed(self.credential_reference, url)
        last_error: ProviderClientError | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.requests_made += 1
            try:
                response = self._client.get(
                    url,
                    params=dict(params or {}),
                    headers={
                        **authorization_headers(self._active_credential),
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "nico-provider-collector/2",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=self.retry_policy.timeout_seconds,
                    follow_redirects=False,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = ProviderClientError("provider_network_unavailable", retryable=True)
                if attempt >= self.retry_policy.max_attempts:
                    raise last_error from exc
                continue

            status = response.status_code
            if 300 <= status <= 399:
                raise ProviderClientError("provider_redirect_not_allowed", status_code=status)
            if status in {401, 403}:
                if (
                    required
                    and self.requested_access_mode is ProviderAccessMode.AUTO
                    and self._active_credential is None
                    and self.credential is not None
                    and not self._auth_fallback_attempted
                ):
                    self._auth_fallback_attempted = True
                    self._active_credential = self.credential
                    return self._get(url, params=params, required=required)
                if self._active_credential is None:
                    raise ProviderClientError("provider_read_only_authentication_required", status_code=status)
                raise ProviderClientError("provider_auth_failed", status_code=status)
            if status == 404:
                if required and self._active_credential is None:
                    if (
                        self.requested_access_mode is ProviderAccessMode.AUTO
                        and self.credential is not None
                        and not self._auth_fallback_attempted
                    ):
                        self._auth_fallback_attempted = True
                        self._active_credential = self.credential
                        return self._get(url, params=params, required=required)
                    raise ProviderClientError("provider_repository_not_publicly_accessible", status_code=status)
                raise ProviderClientError("provider_repository_not_found", status_code=status)
            if status == 429:
                retry_after = self._retry_after(response)
                last_error = ProviderClientError(
                    "provider_rate_limited",
                    status_code=status,
                    retryable=True,
                    retry_after_seconds=retry_after,
                )
                if attempt >= self.retry_policy.max_attempts:
                    raise last_error
                continue
            if 500 <= status <= 599:
                last_error = ProviderClientError(
                    "provider_service_unavailable",
                    status_code=status,
                    retryable=True,
                )
                if attempt >= self.retry_policy.max_attempts:
                    raise last_error
                continue
            if status < 200 or status >= 300:
                raise ProviderClientError("provider_request_failed", status_code=status)
            try:
                return response.json(), response.headers
            except ValueError as exc:
                raise ProviderClientError("provider_response_not_json", status_code=status) from exc
        if last_error is not None:
            raise last_error
        raise ProviderClientError("provider_request_failed")

    @staticmethod
    def _next_link(headers: httpx.Headers) -> str:
        value = _text(headers.get("link"))
        if not value:
            return ""
        for part in value.split(","):
            if 'rel="next"' not in part:
                continue
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
        return ""

    def _pages(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        required: bool = False,
    ) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        current_url = url
        current_params = dict(params or {})
        seen_pages: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for _page_number in range(1, self.retry_policy.max_pages + 1):
            identity = (
                current_url,
                tuple(sorted((str(key), str(value)) for key, value in current_params.items())),
            )
            if identity in seen_pages:
                raise ProviderClientError("provider_pagination_loop_detected")
            seen_pages.add(identity)
            payload, headers = self._get(current_url, params=current_params, required=required)
            self.pages_fetched += 1
            if not isinstance(payload, list):
                raise ProviderClientError("provider_response_not_json")
            output.extend(item for item in payload if isinstance(item, Mapping))
            next_url = self._next_link(headers)
            if not next_url:
                return output
            assert_url_allowed(self.credential_reference, next_url)
            current_url, current_params = next_url, {}
        raise ProviderClientError("provider_pagination_limit_exceeded")

    def collect(self, repository_id: str, *, revision: str = "") -> AcceptanceCollection:
        parts = [part for part in _text(repository_id).split("/") if part]
        if len(parts) != 2:
            raise LiveAcceptanceError("provider_acceptance_github_repository_format_required")
        owner, repo = parts
        root = f"{self.base_url}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        repo_raw, _ = self._get(root, required=True)
        repo_payload = dict(repo_raw if isinstance(repo_raw, Mapping) else {})
        default_branch = _text(repo_payload.get("default_branch")) or "main"
        commits = self._pages(
            f"{root}/commits",
            {"sha": revision or default_branch, "per_page": 1},
            required=True,
        )
        exact_revision = _text(revision or (commits[0].get("sha") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        tree_raw, _ = self._get(
            f"{root}/git/trees/{quote(exact_revision, safe='')}",
            params={"recursive": "1"},
            required=True,
        )
        tree_payload = dict(tree_raw if isinstance(tree_raw, Mapping) else {})
        tree_items = [
            dict(item)
            for item in tree_payload.get("tree", ())
            if isinstance(item, Mapping) and _text(item.get("path"))
        ]
        if not tree_items:
            raise ProviderClientError("provider_required_source_evidence_unavailable")
        self.pages_fetched += 1
        immutable_repository_id = _text(repo_payload.get("id") or repository_id)
        source_objects: list[CanonicalSourceObject] = []
        exact_source_locators: list[CanonicalExactSourceLocator] = []
        for item in tree_items:
            path = _text(item.get("path"))
            object_id = _text(item.get("sha")) or path
            object_type = _text(item.get("type")) or "blob"
            exact_url = (
                f"https://github.com/{owner}/{repo}/"
                f"{'tree' if object_type == 'tree' else 'blob'}/"
                f"{quote(exact_revision, safe='')}/{quote(path, safe='/')}"
            )
            source_objects.append(
                CanonicalSourceObject(
                    provider=ProviderKind.GITHUB,
                    repository_id=immutable_repository_id,
                    revision=exact_revision,
                    path=path,
                    object_id=object_id,
                    object_type=object_type,
                    size=item.get("size"),
                    mode=_text(item.get("mode")),
                    exact_url=exact_url,
                )
            )
            exact_source_locators.append(
                CanonicalExactSourceLocator(
                    provider=ProviderKind.GITHUB,
                    repository_id=immutable_repository_id,
                    revision=exact_revision,
                    path=path,
                    object_id=object_id,
                    exact_url=exact_url,
                )
            )
        self.pagination_complete = not bool(tree_payload.get("truncated"))
        if not self.pagination_complete:
            self.collection_limitations.append("github recursive source tree was truncated")
        collected_at = _utc_now()
        capabilities = (
            Capability.REPOSITORY,
            Capability.COMMITS,
            Capability.TREE,
            Capability.BLOBS,
            Capability.SOURCE_LINKS,
        )
        envelope = ProviderEvidenceEnvelope(
            identity=ProviderIdentity(
                provider=ProviderKind.GITHUB,
                instance_url=self.base_url,
                namespace=owner,
                repository=repo,
                repository_id=immutable_repository_id,
                default_branch=default_branch,
            ),
            access=ProviderAccess(
                read_only=True,
                scopes=tuple(self.credential_reference.scopes) if self.credential_used else (),
                capabilities=capabilities,
                partial_access=False,
                limitation_reason="",
                access_mode=self.actual_access_mode.value,
                credential_used=self.credential_used,
            ),
            snapshot=SnapshotIdentity(
                provider=ProviderKind.GITHUB,
                repository_id=immutable_repository_id,
                revision=exact_revision,
                collected_at=collected_at,
                source_fingerprint=_fingerprint(
                    {
                        "provider": "github",
                        "repository_id": immutable_repository_id,
                        "revision": exact_revision,
                        "tree_sha": _text(tree_payload.get("sha")),
                        "source_objects": [
                            {
                                "path": item.path,
                                "object_id": item.object_id,
                                "object_type": item.object_type,
                                "size": item.size,
                                "mode": item.mode,
                            }
                            for item in source_objects
                        ],
                    }
                ),
            ),
            source_objects=tuple(source_objects),
            exact_source_locators=tuple(exact_source_locators),
            capability_status=tuple(
                ProviderCapabilityStatus(capability=capability, state=CapabilityState.SUPPORTED)
                for capability in capabilities
            ),
            pagination_complete=self.pagination_complete,
            collection_limitations=tuple(self.collection_limitations),
        )
        return AcceptanceCollection(
            provider=ProviderKind.GITHUB,
            repository_id=immutable_repository_id,
            revision=exact_revision,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
            envelope=envelope,
            warnings=tuple(validate_provider_envelope(envelope)),
        )


def _parse_azure_repository(repository: str) -> tuple[str, str, str]:
    parts = [part for part in _text(repository).split("/") if part]
    if len(parts) != 3:
        raise LiveAcceptanceError("provider_acceptance_azure_repository_format_required")
    return parts[0], parts[1], parts[2]


def build_collector(provider: str, access_mode: str) -> CollectorHandle:
    provider = _text(provider).lower().replace("-", "_")
    if provider not in OFFICIAL_ENDPOINTS:
        raise LiveAcceptanceError(f"provider_acceptance_unsupported:{provider}")
    if access_mode not in {AUTO, ANONYMOUS_PUBLIC, AUTHENTICATED_READ_ONLY}:
        raise LiveAcceptanceError("provider_acceptance_access_mode_invalid")
    credential_reference = _credential_reference(provider)
    if access_mode == ANONYMOUS_PUBLIC:
        assert_anonymous_environment_clean()
        credential = None
    elif access_mode == AUTO:
        credential = _credential(provider, optional=True)
    else:
        credential = _credential(provider)
    request_audit = RequestContractAudit(access_mode)
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=1, max_delay_seconds=30,
                         timeout_seconds=45, max_pages=200)
    http_client = httpx.Client(
        timeout=policy.timeout_seconds,
        follow_redirects=False,
        trust_env=False,
        event_hooks={"request": [request_audit.inspect]},
    )
    common = {"credential": credential, "credential_reference": credential_reference, "client": http_client,
              "retry_policy": policy, "access_mode": access_mode}
    if provider == "github":
        collector = GitHubAcceptanceClient(instance_url=OFFICIAL_ENDPOINTS[provider], **common)
    elif provider == "gitlab":
        collector = GitLabClient(instance_url=OFFICIAL_ENDPOINTS[provider], **common)
    elif provider == "bitbucket_cloud":
        collector = BitbucketCloudClient(instance_url=OFFICIAL_ENDPOINTS[provider], **common)
    else:
        collector = None
    return CollectorHandle(collector, http_client, request_audit, credential, credential_reference)


def _build_azure_collector(repository: str, access_mode: str) -> tuple[CollectorHandle, str]:
    organization, project, repository_id = _parse_azure_repository(repository)
    handle = build_collector("azure_devops", access_mode)
    handle.collector = AzureDevOpsClient(
        instance_url=OFFICIAL_ENDPOINTS["azure_devops"],
        organization=organization,
        project=project,
        credential=handle.credential,
        credential_reference=handle.credential_reference,
        client=handle.http_client,
        retry_policy=RetryPolicy(max_attempts=4, base_delay_seconds=1, max_delay_seconds=30,
                                 timeout_seconds=45, max_pages=200),
        access_mode=access_mode,
    )
    return handle, repository_id


def _records(envelope: Any, name: str) -> list[dict[str, Any]]:
    return [asdict(item) for item in getattr(envelope, name, ())]


def _canonical_envelope(result: Any) -> dict[str, Any]:
    envelope = result.envelope
    return {
        "identity": asdict(envelope.identity),
        "access": asdict(envelope.access),
        "snapshot": asdict(envelope.snapshot),
        "source_objects": _records(envelope, "source_objects"),
        "exact_source_locators": _records(envelope, "exact_source_locators"),
        "capability_status": _records(envelope, "capability_status"),
        "pagination_complete": bool(getattr(envelope, "pagination_complete", True)),
        "collection_limitations": list(getattr(envelope, "collection_limitations", ())),
        "warnings": list(result.warnings),
    }


def _json_safe(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _fingerprint(value: Any) -> str:
    rendered = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def _source_inventory(envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        ({"path": _text(item.get("path")), "object_id": _text(item.get("object_id")),
          "object_type": _text(item.get("object_type")), "size": item.get("size"),
          "mode": _text(item.get("mode"))} for item in envelope["source_objects"]),
        key=lambda item: (item["path"], item["object_id"]),
    )


def _exact_source_inventory(envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        ({"repository_id": _text(item.get("repository_id")),
          "revision": _text(item.get("revision")), "path": _text(item.get("path")),
          "object_id": _text(item.get("object_id")), "exact_url": _text(item.get("exact_url"))}
         for item in envelope["exact_source_locators"]),
        key=lambda item: (item["path"], item["object_id"], item["exact_url"]),
    )


def _validate_capability_truth(envelope: Mapping[str, Any]) -> None:
    for item in envelope["capability_status"]:
        state = _text(item.get("state"))
        if state not in SAFE_CAPABILITY_STATES:
            raise LiveAcceptanceError("provider_acceptance_capability_state_invalid")
        if state in LIMITATION_STATES and not _text(item.get("reason")):
            raise LiveAcceptanceError("provider_acceptance_capability_limitation_reason_missing")


def _access_truth(envelope: Mapping[str, Any]) -> tuple[str, bool]:
    access = envelope["access"]
    return _text(access.get("access_mode")), bool(access.get("credential_used"))


def _error_code(exc: Exception) -> str:
    code = _text(getattr(exc, "code", ""))
    return code if code in AUTHENTICATION_REQUIRED_CODES else "provider_acceptance_unexpected_provider_failure"


def _credential_metadata(provider: str, credential: Any | None) -> dict[str, Any]:
    if credential is None:
        return {"provider": "bitbucket" if provider == "bitbucket_cloud" else provider,
                "credential_used": False, "secret_present": False}
    return {**credential.safe_metadata(), "credential_used": True}


def _access_mode_matches(actual: str, requested: str) -> bool:
    if requested == AUTO:
        return actual in {ANONYMOUS_PUBLIC, AUTHENTICATED_READ_ONLY}
    return actual == requested


def _assert_raw_secrets_absent(payload: Mapping[str, Any], raw_secrets: list[str]) -> None:
    rendered = json.dumps(_json_safe(payload), sort_keys=True, ensure_ascii=False)
    if any(secret and secret in rendered for secret in raw_secrets):
        raise LiveAcceptanceError("provider_acceptance_raw_credential_exposed")
    if SECRET_PATTERN.search(rendered):
        raise LiveAcceptanceError("provider_acceptance_secret_pattern_exposed")


def run_acceptance(*, provider: str, repository: str, revision: str, access_mode: str,
                   expected_outcome: str = EXPECTED_SUCCESS, passes: int = 2,
                   workflow_sha: str = "", workflow_run_id: str = "",
                   workflow_run_attempt: str = "") -> dict[str, Any]:
    if passes < 2:
        raise LiveAcceptanceError("provider_acceptance_requires_two_passes")
    if access_mode == ANONYMOUS_PUBLIC:
        assert_anonymous_environment_clean()
    if expected_outcome not in {EXPECTED_SUCCESS, EXPECTED_AUTHENTICATION_REQUIRED}:
        raise LiveAcceptanceError("provider_acceptance_expected_outcome_invalid")

    provider = _text(provider).lower().replace("-", "_")
    pinned_revision = _text(revision)
    runs: list[dict[str, Any]] = []
    raw_secrets: list[str] = []
    credential_metadata: dict[str, Any] | None = None
    for index in range(passes):
        if provider == "azure_devops":
            handle, native_repository = _build_azure_collector(repository, access_mode)
        else:
            handle = build_collector(provider, access_mode)
            native_repository = repository
        try:
            if handle.credential is not None:
                raw_secrets.append(handle.credential.secret.reveal())
            current_metadata = _credential_metadata(provider, handle.credential)
            if credential_metadata is None:
                credential_metadata = current_metadata
            collection = handle.collector.collect(native_repository, revision=pinned_revision)
        except ProviderClientError as exc:
            if expected_outcome != EXPECTED_AUTHENTICATION_REQUIRED:
                raise
            code = _error_code(exc)
            if code == "provider_acceptance_unexpected_provider_failure":
                raise LiveAcceptanceError(code) from exc
            runs.append({"pass": index + 1, "outcome": EXPECTED_AUTHENTICATION_REQUIRED,
                         "error_code": code,
                         "request_contract": handle.request_audit.safe_metadata()})
            continue
        finally:
            handle.close()

        if expected_outcome != EXPECTED_SUCCESS:
            raise LiveAcceptanceError("provider_acceptance_expected_authentication_required_but_succeeded")
        if not pinned_revision:
            pinned_revision = collection.revision
        if collection.revision != pinned_revision:
            raise LiveAcceptanceError("provider_acceptance_revision_drift")
        adapted = collection.adapt()
        if adapted.warnings:
            raise LiveAcceptanceError("provider_acceptance_canonical_warnings")
        envelope = _canonical_envelope(adapted)
        if envelope["snapshot"]["revision"] != pinned_revision:
            raise LiveAcceptanceError("provider_acceptance_snapshot_revision_mismatch")
        if envelope["access"]["read_only"] is not True:
            raise LiveAcceptanceError("provider_acceptance_must_be_read_only")
        actual_access_mode, credential_used = _access_truth(envelope)
        if not _access_mode_matches(actual_access_mode, access_mode):
            raise LiveAcceptanceError("provider_acceptance_access_mode_mismatch")
        if access_mode == AUTHENTICATED_READ_ONLY and credential_used is not True:
            raise LiveAcceptanceError("provider_acceptance_credential_use_mismatch")
        if access_mode == ANONYMOUS_PUBLIC and credential_used is not False:
            raise LiveAcceptanceError("provider_acceptance_credential_use_mismatch")
        if envelope["pagination_complete"] is not True:
            raise LiveAcceptanceError("provider_acceptance_pagination_incomplete")
        if not envelope["source_objects"]:
            raise LiveAcceptanceError("provider_acceptance_source_tree_missing")
        if not envelope["exact_source_locators"]:
            raise LiveAcceptanceError("provider_acceptance_exact_source_missing")
        _validate_capability_truth(envelope)
        source_inventory = _source_inventory(envelope)
        exact_source_inventory = _exact_source_inventory(envelope)
        request_contract = handle.request_audit.safe_metadata()
        if access_mode == ANONYMOUS_PUBLIC and any(request_contract[key] for key in (
            "authorization_header_observed", "cookie_header_observed", "secret_query_observed"
        )):
            raise LiveAcceptanceError("provider_acceptance_anonymous_request_contract_failed")
        runs.append({
            "pass": index + 1, "outcome": EXPECTED_SUCCESS,
            "provider": collection.provider.value, "repository_id": collection.repository_id,
            "revision": collection.revision, "pages_fetched": collection.pages_fetched,
            "requests_made": collection.requests_made,
            "source_fingerprint": envelope["snapshot"]["source_fingerprint"],
            "source_inventory_fingerprint": _fingerprint(source_inventory),
            "exact_source_inventory_fingerprint": _fingerprint(exact_source_inventory),
            "source_object_count": len(source_inventory),
            "exact_source_locator_count": len(exact_source_inventory),
            "pagination_complete": True, "access_mode": actual_access_mode,
            "credential_used": credential_used,
            "collection_limitations": list(envelope["collection_limitations"]),
            "capability_status": list(envelope["capability_status"]),
            "request_contract": request_contract,
        })

    if credential_metadata is None:
        credential_metadata = _credential_metadata(provider, None)
    if {item["outcome"] for item in runs} != {expected_outcome}:
        raise LiveAcceptanceError("provider_acceptance_outcome_drift")
    resolved_access_mode = (
        _text(runs[0].get("access_mode"))
        if runs and runs[0]["outcome"] == EXPECTED_SUCCESS
        else access_mode
    )
    resolved_credential_used = (
        bool(runs[0].get("credential_used"))
        if runs and runs[0]["outcome"] == EXPECTED_SUCCESS
        else access_mode == AUTHENTICATED_READ_ONLY
    )
    proof: dict[str, bool] = {
        "two_fresh_client_passes": len(runs) >= 2,
        "request_contract_safe": all(
            not item["request_contract"]["cookie_header_observed"]
            and not item["request_contract"]["secret_query_observed"] for item in runs),
        "raw_credential_absent": True, "human_review_required": True,
        "human_approval_false": True, "client_delivery_false": True,
    }
    if expected_outcome == EXPECTED_SUCCESS:
        for key, run_key in (
            ("repository_identity_stable", "repository_id"),
            ("immutable_revision_stable", "revision"),
            ("source_fingerprint_stable", "source_fingerprint"),
            ("source_inventory_stable", "source_inventory_fingerprint"),
            ("exact_source_inventory_stable", "exact_source_inventory_fingerprint"),
            ("pagination_stable", "pages_fetched"),
        ):
            proof[key] = len({item[run_key] for item in runs}) == 1
        proof["required_source_complete"] = all(
            item["source_object_count"] > 0 and item["exact_source_locator_count"] > 0
            for item in runs)
        proof["access_mode_bound"] = (
            len({_text(item["access_mode"]) for item in runs}) == 1
            and all(_access_mode_matches(_text(item["access_mode"]), access_mode) for item in runs)
        )
        proof["credential_use_bound"] = (
            len({bool(item["credential_used"]) for item in runs}) == 1
            and (
                access_mode == AUTO
                or all(item["credential_used"] is (access_mode == AUTHENTICATED_READ_ONLY) for item in runs)
            )
        )
        proof["anonymous_auth_headers_absent"] = access_mode != ANONYMOUS_PUBLIC or all(
            not item["request_contract"]["authorization_header_observed"] for item in runs)
    else:
        proof["authentication_required_stable"] = len({item["error_code"] for item in runs}) == 1
        proof["no_misleading_empty_report"] = True
        proof["anonymous_auth_headers_absent"] = all(
            not item["request_contract"]["authorization_header_observed"] for item in runs)
    if not all(proof.values()):
        raise LiveAcceptanceError("provider_acceptance_stability_proof_failed")

    result = {
        "artifact_schema": ARTIFACT_SCHEMA, "status": "passed",
        "expected_outcome": expected_outcome,
        "provider_support_maturity": (
            ProviderSupportMaturity.REAL_PROVIDER_INTEGRATION_PROVEN.value
            if expected_outcome == EXPECTED_SUCCESS
            else ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN.value),
        "public_anonymous_support_proven": (
            access_mode == ANONYMOUS_PUBLIC and expected_outcome == EXPECTED_SUCCESS),
        "private_provider_support_proven": False,
        "provider": provider, "repository": repository, "requested_access_mode": access_mode,
        "access_mode": resolved_access_mode, "credential_used": resolved_credential_used,
        "expected_revision": pinned_revision, "passes_required": passes,
        "passes_completed": len(runs),
        "workflow_identity": {"sha": _text(workflow_sha), "run_id": _text(workflow_run_id),
                              "run_attempt": _text(workflow_run_attempt)},
        "runs": runs, "proof": proof, "credential_metadata": credential_metadata,
        "human_review_required": True, "human_approval_proven": False,
        "client_delivery_allowed": False, "assessment_snapshot_approved": False,
    }
    _assert_raw_secrets_absent(result, raw_secrets)
    return result


def _configured_secrets() -> list[str]:
    return [value for name in PROVIDER_CREDENTIAL_ALIASES
            if (value := _text(os.environ.get(name)))]


def verify_artifact(path: Path, *, access_mode: str, expected_outcome: str,
                    workflow_sha: str, workflow_run_id: str,
                    workflow_run_attempt: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_schema") != ARTIFACT_SCHEMA or payload.get("status") != "passed":
        raise LiveAcceptanceError("provider_acceptance_artifact_not_passing")
    if payload.get("access_mode") != access_mode:
        raise LiveAcceptanceError("provider_acceptance_artifact_access_mode_mismatch")
    if payload.get("expected_outcome") != expected_outcome:
        raise LiveAcceptanceError("provider_acceptance_artifact_outcome_mismatch")
    identity = {"sha": _text(workflow_sha), "run_id": _text(workflow_run_id),
                "run_attempt": _text(workflow_run_attempt)}
    if payload.get("workflow_identity") != identity or not all(identity.values()):
        raise LiveAcceptanceError("provider_acceptance_artifact_workflow_identity_mismatch")
    if payload.get("human_review_required") is not True:
        raise LiveAcceptanceError("provider_acceptance_human_review_boundary_missing")
    if payload.get("human_approval_proven") is not False:
        raise LiveAcceptanceError("provider_acceptance_human_approval_boundary_failed")
    if payload.get("client_delivery_allowed") is not False:
        raise LiveAcceptanceError("provider_acceptance_delivery_boundary_failed")
    if not payload.get("proof") or not all(payload["proof"].values()):
        raise LiveAcceptanceError("provider_acceptance_artifact_proof_incomplete")
    if access_mode == ANONYMOUS_PUBLIC:
        assert_anonymous_environment_clean()
        if payload.get("credential_used") is not False:
            raise LiveAcceptanceError("provider_acceptance_anonymous_credential_used")
    _assert_raw_secrets_absent(payload, _configured_secrets())


def _failed_payload(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    code = _text(getattr(exc, "code", ""))
    if not code.startswith("provider_"):
        code = _text(exc) if _text(exc).startswith("provider_") else "provider_acceptance_failed"
    return {
        "artifact_schema": ARTIFACT_SCHEMA, "status": "failed",
        "provider_support_maturity": ProviderSupportMaturity.IMPLEMENTED_BUT_UNPROVEN.value,
        "provider": args.provider, "repository": args.repository,
        "access_mode": args.access_mode, "expected_outcome": args.expected_outcome,
        "error_type": type(exc).__name__, "error_code": code,
        "workflow_identity": {"sha": _text(args.workflow_sha),
                              "run_id": _text(args.workflow_run_id),
                              "run_attempt": _text(args.workflow_run_attempt)},
        "human_review_required": True, "human_approval_proven": False,
        "client_delivery_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove tokenless or optional read-only provider acquisition at one revision.")
    parser.add_argument("--provider", choices=tuple(OFFICIAL_ENDPOINTS), default="github")
    parser.add_argument("--repository", default="")
    parser.add_argument("--revision", default="")
    parser.add_argument("--access-mode", choices=(AUTO, ANONYMOUS_PUBLIC, AUTHENTICATED_READ_ONLY),
                        default=ANONYMOUS_PUBLIC)
    parser.add_argument("--expected-outcome",
                        choices=(EXPECTED_SUCCESS, EXPECTED_AUTHENTICATION_REQUIRED),
                        default=EXPECTED_SUCCESS)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--workflow-sha", default="")
    parser.add_argument("--workflow-run-id", default="")
    parser.add_argument("--workflow-run-attempt", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-artifact", type=Path)
    args = parser.parse_args()
    if args.verify_artifact is not None:
        verify_artifact(args.verify_artifact, access_mode=args.access_mode,
                        expected_outcome=args.expected_outcome, workflow_sha=args.workflow_sha,
                        workflow_run_id=args.workflow_run_id,
                        workflow_run_attempt=args.workflow_run_attempt)
        return 0
    if args.output is None or not args.repository:
        parser.error("--repository and --output are required for live proof")
    try:
        result = run_acceptance(
            provider=args.provider, repository=args.repository, revision=args.revision,
            access_mode=args.access_mode, expected_outcome=args.expected_outcome,
            passes=args.passes, workflow_sha=args.workflow_sha,
            workflow_run_id=args.workflow_run_id,
            workflow_run_attempt=args.workflow_run_attempt)
    except Exception as exc:
        result, exit_code = _failed_payload(args, exc), 1
    else:
        exit_code = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(_json_safe(result), indent=2, sort_keys=True, ensure_ascii=False)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
