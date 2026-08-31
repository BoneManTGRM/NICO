from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlencode

import httpx

from nico.provider_credentials import (
    CredentialError,
    CredentialReference,
    ResolvedCredential,
    assert_url_allowed,
    authorization_headers,
)
from nico.provider_neutral_contract import (
    Capability,
    CapabilityState,
    ProviderAccessMode,
    ProviderKind,
)
from nico.provider_payload_adapters import (
    AdapterResult,
    adapt_azure_devops_payload,
    adapt_bitbucket_payload,
    adapt_gitlab_payload,
)


class ProviderClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 5.0
    timeout_seconds: float = 30.0
    max_pages: int = 100

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("provider_retry_attempts_invalid")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("provider_retry_delay_invalid")
        if self.timeout_seconds <= 0:
            raise ValueError("provider_timeout_invalid")
        if self.max_pages < 1:
            raise ValueError("provider_max_pages_invalid")


@dataclass(frozen=True)
class ProviderCollection:
    provider: ProviderKind
    repository_id: str
    revision: str
    payload: Mapping[str, Any]
    pages_fetched: int
    requests_made: int
    collected_at: str
    pagination_complete: bool = True
    rate_limit_state: Mapping[str, str] | None = None
    collection_limitations: tuple[str, ...] = ()
    access_mode: str = ProviderAccessMode.AUTHENTICATED_READ_ONLY.value
    credential_used: bool = True

    def adapt(self) -> AdapterResult:
        if self.provider is ProviderKind.GITLAB:
            return adapt_gitlab_payload(self.payload)
        if self.provider is ProviderKind.BITBUCKET:
            return adapt_bitbucket_payload(self.payload)
        if self.provider is ProviderKind.AZURE_DEVOPS:
            return adapt_azure_devops_payload(self.payload)
        raise ProviderClientError("provider_adapter_not_supported")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _snapshot_manifest_sha256(
    provider: ProviderKind,
    repository_id: str,
    revision: str,
    source_objects: Sequence[Mapping[str, Any]],
) -> str:
    entries = [
        {
            "path": _text(item.get("path")),
            "object_id": _text(item.get("id") or item.get("object_id") or item.get("commitId")),
            "type": _text(item.get("type") or item.get("gitObjectType") or item.get("kind")),
            "size": _int(item.get("size"), -1),
        }
        for item in source_objects
    ]
    payload = {
        "provider": provider.value,
        "repository_id": _text(repository_id),
        "revision": _text(revision),
        "source_objects": sorted(entries, key=lambda item: (item["path"], item["object_id"])),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _capability_status(
    capability: Capability,
    state: CapabilityState,
    reason: str = "",
) -> dict[str, str]:
    return {
        "capability": capability.value,
        "state": state.value,
        "reason": _text(reason),
    }


_IMMUTABLE_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _immutable_revision(requested: str, observed: Any) -> str:
    expected = _text(requested).casefold()
    actual = _text(observed).casefold()
    if not actual or not _IMMUTABLE_REVISION_RE.fullmatch(actual):
        raise ProviderClientError("provider_snapshot_revision_invalid")
    if expected:
        if not _IMMUTABLE_REVISION_RE.fullmatch(expected):
            raise ProviderClientError("provider_snapshot_revision_invalid")
        if actual != expected:
            raise ProviderClientError("provider_snapshot_revision_mismatch")
    return actual


class BaseProviderClient:
    provider: ProviderKind

    def __init__(
        self,
        *,
        base_url: str,
        credential: ResolvedCredential | None = None,
        credential_reference: CredentialReference | None = None,
        access_mode: ProviderAccessMode | str | None = None,
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        activity_callback: Callable[[], None] | None = None,
    ) -> None:
        normalized = str(base_url or "").rstrip("/")
        reference = credential.reference if credential is not None else credential_reference
        if reference is None:
            raise CredentialError("provider_credential_reference_required")
        assert_url_allowed(reference, normalized)
        if reference.provider is not self.provider:
            raise CredentialError("provider_credential_kind_mismatch")
        if credential is not None and credential.reference != reference:
            raise CredentialError("provider_credential_reference_mismatch")
        if access_mode is None:
            requested_mode = (
                ProviderAccessMode.AUTHENTICATED_READ_ONLY
                if credential is not None
                else ProviderAccessMode.ANONYMOUS_PUBLIC
            )
        else:
            requested_mode = (
                access_mode
                if isinstance(access_mode, ProviderAccessMode)
                else ProviderAccessMode(str(access_mode))
            )
        if requested_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY and credential is None:
            raise CredentialError("provider_credential_not_configured")
        self.base_url = normalized
        self.credential = credential
        self.credential_reference = reference
        self.requested_access_mode = requested_mode
        self._active_credential = (
            credential
            if requested_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY
            else None
        )
        self._auth_fallback_attempted = False
        self.retry_policy = retry_policy or RetryPolicy()
        self.retry_policy.validate()
        self._client = client or httpx.Client(
            timeout=self.retry_policy.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        self._owns_client = client is None
        self._sleeper = sleeper
        self._activity_callback = activity_callback or (lambda: None)
        self.requests_made = 0
        self.pages_fetched = 0
        self.rate_limit_state: dict[str, str] = {}
        self.collection_limitations: list[str] = []
        self.capability_status: list[dict[str, str]] = []
        self.pagination_complete = True

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
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BaseProviderClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

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

    def _capture_rate_limit(self, headers: httpx.Headers) -> None:
        aliases = {
            "remaining": (
                "ratelimit-remaining",
                "x-ratelimit-remaining",
                "x-rate-limit-remaining",
                "x-ms-ratelimit-remaining-user-reads",
                "x-ms-ratelimit-remaining-subscription-reads",
            ),
            "reset": ("ratelimit-reset", "x-ratelimit-reset", "x-rate-limit-reset"),
            "retry_after": ("retry-after",),
        }
        for output, names in aliases.items():
            for name in names:
                value = _text(headers.get(name))
                if value:
                    self.rate_limit_state[output] = value
                    break

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
            self._activity_callback()
            try:
                # Provider APIs are stateless evidence boundaries. Some public
                # endpoints (notably Azure DevOps) set anonymous session cookies;
                # never replay them as implicit authentication on later reads.
                self._client.cookies.clear()
                response = self._client.get(
                    url,
                    params=dict(params or {}),
                    headers={
                        **authorization_headers(self._active_credential),
                        "Accept": "application/json",
                        "User-Agent": "nico-provider-collector/2",
                    },
                    timeout=self.retry_policy.timeout_seconds,
                    follow_redirects=False,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = ProviderClientError(
                    "provider_network_unavailable",
                    retryable=True,
                )
                if attempt >= self.retry_policy.max_attempts:
                    raise last_error from exc
                self._sleeper(self._delay(attempt))
                continue
            finally:
                self._activity_callback()

            self._capture_rate_limit(response.headers)
            status = response.status_code
            if 300 <= status <= 399:
                raise ProviderClientError("provider_redirect_not_allowed", status_code=status)
            # Azure returns an interactive-login 203 for some anonymous API
            # requests.  It is an auth challenge even when Content-Type is
            # absent, and must never be accepted as evidence.
            authentication_challenge = status in {401, 403} or (
                self.provider is ProviderKind.AZURE_DEVOPS and status == 203
            )
            if authentication_challenge:
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
                    raise ProviderClientError(
                        "provider_read_only_authentication_required",
                        status_code=status,
                    )
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
                    raise ProviderClientError(
                        "provider_repository_not_publicly_accessible",
                        status_code=status,
                    )
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
                self._sleeper(self._delay(attempt, retry_after))
                continue
            if 500 <= status <= 599:
                last_error = ProviderClientError(
                    "provider_service_unavailable",
                    status_code=status,
                    retryable=True,
                )
                if attempt >= self.retry_policy.max_attempts:
                    raise last_error
                self._sleeper(self._delay(attempt))
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

    def _paginate(
        self,
        *,
        url: str,
        params: Mapping[str, Any] | None,
        items: Callable[[Any], list[Mapping[str, Any]]],
        next_page: Callable[[Any, httpx.Headers, int], tuple[str, Mapping[str, Any]] | None],
        required: bool = False,
    ) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        current_url = url
        current_params = dict(params or {})
        seen_pages: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for page_number in range(1, self.retry_policy.max_pages + 1):
            identity = (
                current_url,
                tuple(sorted((str(key), str(value)) for key, value in current_params.items())),
            )
            if identity in seen_pages:
                raise ProviderClientError("provider_pagination_loop_detected")
            seen_pages.add(identity)
            payload, headers = self._get(current_url, params=current_params, required=required)
            self.pages_fetched += 1
            output.extend(items(payload))
            following = next_page(payload, headers, page_number)
            if following is None:
                return output
            current_url, current_params = following
            assert_url_allowed(self.credential_reference, current_url)
        raise ProviderClientError("provider_pagination_limit_exceeded")

    def _optional_collection(
        self,
        capability: Capability,
        loader: Callable[[], list[Mapping[str, Any]]],
    ) -> list[Mapping[str, Any]]:
        try:
            values = loader()
        except ProviderClientError as exc:
            self._record_optional_failure(capability, exc)
            return []
        self._set_capability(
            capability,
            CapabilityState.SUPPORTED if values else CapabilityState.SUPPORTED_EMPTY,
        )
        return values

    def _record_optional_failure(
        self,
        capability: Capability,
        exc: ProviderClientError,
    ) -> None:
        if exc.code in {
            "provider_read_only_authentication_required",
            "provider_repository_not_publicly_accessible",
        }:
            state = CapabilityState.UNAVAILABLE_AUTHENTICATION
            reason = f"{capability.value} evidence is unavailable without read-only authentication"
        elif exc.code == "provider_auth_failed" or exc.status_code == 403:
            state = CapabilityState.UNAVAILABLE_PERMISSION
            reason = f"{capability.value} evidence is unavailable with the current provider permission"
        elif exc.status_code == 404:
            state = CapabilityState.UNAVAILABLE_PROVIDER
            reason = f"{capability.value} is unavailable from this provider or repository"
        elif exc.code == "provider_rate_limited":
            state = CapabilityState.RATE_LIMITED
            reason = f"{capability.value} evidence collection reached the provider rate limit"
        else:
            state = CapabilityState.COLLECTION_FAILED
            reason = f"{capability.value} evidence collection failed"
        self._set_capability(capability, state, reason)
        self.collection_limitations.append(reason)

    def _set_capability(
        self,
        capability: Capability,
        state: CapabilityState,
        reason: str = "",
    ) -> None:
        self.capability_status = [
            item for item in self.capability_status if item.get("capability") != capability.value
        ]
        self.capability_status.append(_capability_status(capability, state, reason))

    def _capability(self, capability: Capability) -> Mapping[str, str] | None:
        return next(
            (
                item
                for item in reversed(self.capability_status)
                if item.get("capability") == capability.value
            ),
            None,
        )

    def _inherit_parent_capability(self, child: Capability, parent: Capability) -> bool:
        status = self._capability(parent)
        if not status or status.get("state") in {
            CapabilityState.SUPPORTED.value,
            CapabilityState.SUPPORTED_EMPTY.value,
            CapabilityState.SUPPORTED_LIMITED.value,
        }:
            return False
        reason = _text(status.get("reason")) or f"{parent.value} evidence was unavailable"
        self._set_capability(child, CapabilityState(str(status["state"])), reason)
        return True

    def _bounded_nested_parents(
        self,
        values: Sequence[Mapping[str, Any]],
        capability: Capability,
        *,
        limit: int = 20,
    ) -> Sequence[Mapping[str, Any]]:
        if len(values) <= limit:
            return values
        reason = f"{capability.value} nested evidence was bounded to {limit} parent records"
        self._set_capability(capability, CapabilityState.SUPPORTED_LIMITED, reason)
        self.collection_limitations.append(reason)
        self.pagination_complete = False
        return values[:limit]

    @staticmethod
    def _require_source_tree(values: Sequence[Mapping[str, Any]]) -> None:
        valid = [item for item in values if _text(item.get("path"))]
        if not valid:
            raise ProviderClientError("provider_required_source_evidence_unavailable")

    def _collection(
        self,
        *,
        repository_id: str,
        revision: str,
        payload: Mapping[str, Any],
        collected_at: str,
    ) -> ProviderCollection:
        return ProviderCollection(
            provider=self.provider,
            repository_id=repository_id,
            revision=revision,
            payload=payload,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
            collected_at=collected_at,
            pagination_complete=self.pagination_complete,
            rate_limit_state=dict(self.rate_limit_state),
            collection_limitations=tuple(dict.fromkeys(self.collection_limitations)),
            access_mode=self.actual_access_mode.value,
            credential_used=self.credential_used,
        )


class GitLabClient(BaseProviderClient):
    provider = ProviderKind.GITLAB

    def __init__(self, *, instance_url: str = "https://gitlab.com", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/api/v4"

    def _gitlab_pages(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        required: bool = False,
    ) -> list[Mapping[str, Any]]:
        base_params = {"per_page": 100, **dict(params or {})}

        def following(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
            del payload, page
            token = _text(headers.get("x-next-page"))
            if not token:
                return None
            return url, {**base_params, "page": token}

        return self._paginate(
            url=url,
            params=base_params,
            items=_list,
            next_page=following,
            required=required,
        )

    def list_authorized_repositories(self) -> list[Mapping[str, Any]]:
        return self._gitlab_pages(
            f"{self.api_url}/projects",
            {"membership": "true", "simple": "true", "archived": "false", "order_by": "id"},
        )

    def build_exact_source_url(
        self,
        project: Mapping[str, Any],
        revision: str,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        web_url = _text(project.get("web_url"))
        if not web_url:
            namespace = _text(project.get("path_with_namespace"))
            web_url = f"{self.base_url}/{namespace}" if namespace else self.base_url
        url = f"{web_url}/-/blob/{quote(revision, safe='')}/{quote(path, safe='/')}"
        if start_line is not None:
            url += f"#L{start_line}"
            if end_line is not None and end_line >= start_line:
                url += f"-{end_line}"
        return url

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        encoded = quote(str(repository_id), safe="")
        root = f"{self.api_url}/projects/{encoded}"
        project_raw, _ = self._get(root, required=True)
        project = dict(_mapping(project_raw))
        commits = self._gitlab_pages(
            f"{root}/repository/commits",
            {"ref_name": revision or _text(project.get("default_branch") or "main")},
            required=True,
        )
        observed_revision = commits[0].get("id") if commits else ""
        exact_revision = _immutable_revision(revision, observed_revision)
        branches = self._optional_collection(
            Capability.BRANCHES,
            lambda: self._gitlab_pages(f"{root}/repository/branches"),
        )
        source_tree = self._gitlab_pages(
            f"{root}/repository/tree",
            {"ref": exact_revision, "recursive": "true"},
            required=True,
        )
        self._require_source_tree(source_tree)
        tags = self._optional_collection(
            Capability.TAGS,
            lambda: self._gitlab_pages(f"{root}/repository/tags"),
        )
        merge_requests = self._optional_collection(
            Capability.CHANGE_REQUESTS,
            lambda: self._gitlab_pages(f"{root}/merge_requests", {"state": "all"}),
        )
        pipelines = self._optional_collection(
            Capability.CI_RUNS,
            lambda: self._gitlab_pages(f"{root}/pipelines", {"sha": exact_revision}),
        )
        pipeline_jobs: list[Mapping[str, Any]] = []
        if not self._inherit_parent_capability(Capability.CI_JOBS, Capability.CI_RUNS):
            for pipeline in self._bounded_nested_parents(pipelines, Capability.CI_JOBS):
                pipeline_id = _text(pipeline.get("id"))
                if pipeline_id:
                    try:
                        jobs = self._gitlab_pages(
                            f"{root}/pipelines/{quote(pipeline_id, safe='')}/jobs"
                        )
                    except ProviderClientError as exc:
                        self._record_optional_failure(Capability.CI_JOBS, exc)
                        break
                    for job in jobs:
                        pipeline_jobs.append({**dict(job), "pipeline_id": pipeline_id})
            if self._capability(Capability.CI_JOBS) is None:
                self._set_capability(
                    Capability.CI_JOBS,
                    CapabilityState.SUPPORTED if pipeline_jobs else CapabilityState.SUPPORTED_EMPTY,
                )
        issues = self._optional_collection(
            Capability.WORK_ITEMS,
            lambda: self._gitlab_pages(f"{root}/issues", {"state": "all"}),
        )
        environments = self._optional_collection(
            Capability.ENVIRONMENTS,
            lambda: self._gitlab_pages(f"{root}/environments"),
        )
        deployments = self._optional_collection(
            Capability.DEPLOYMENTS,
            lambda: self._gitlab_pages(f"{root}/deployments", {"order_by": "id", "sort": "desc"}),
        )
        releases = self._optional_collection(
            Capability.RELEASES,
            lambda: self._gitlab_pages(f"{root}/releases"),
        )
        for capability in (
            Capability.REPOSITORY,
            Capability.COMMITS,
            Capability.TREE,
            Capability.BLOBS,
            Capability.SOURCE_LINKS,
        ):
            self._set_capability(capability, CapabilityState.SUPPORTED)
        collected_at = _utc_now()
        immutable_repository_id = _text(project.get("id") or repository_id)
        payload = {
            "instance_url": self.base_url,
            "project": project,
            "revision": exact_revision,
            "commits": commits,
            "branches": branches,
            "source_tree": source_tree,
            "tags": tags,
            "merge_requests": merge_requests,
            "pipelines": pipelines,
            "pipeline_jobs": pipeline_jobs,
            "issues": issues,
            "environments": environments,
            "deployments": deployments,
            "releases": releases,
            "scopes": list(self.credential_reference.scopes) if self.credential_used else [],
            "access_mode": self.actual_access_mode.value,
            "credential_used": self.credential_used,
            "capability_status": list(self.capability_status),
            "pagination_complete": self.pagination_complete,
            "collection_limitations": list(dict.fromkeys(self.collection_limitations)),
            "rate_limit_state": dict(self.rate_limit_state),
            "snapshot_manifest_sha256": _snapshot_manifest_sha256(
                self.provider, immutable_repository_id, exact_revision, source_tree
            ),
            "collected_at": collected_at,
        }
        return self._collection(
            repository_id=immutable_repository_id,
            revision=exact_revision,
            payload=payload,
            collected_at=collected_at,
        )


class BitbucketCloudClient(BaseProviderClient):
    provider = ProviderKind.BITBUCKET

    def __init__(self, *, instance_url: str = "https://api.bitbucket.org", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/2.0"

    def _bitbucket_pages(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        required: bool = False,
    ) -> list[Mapping[str, Any]]:
        def following(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
            del headers, page
            next_url = _text(_mapping(payload).get("next"))
            if not next_url:
                return None
            return next_url, {}

        return self._paginate(
            url=url,
            params={"pagelen": 100, **dict(params or {})},
            items=lambda payload: _list(_mapping(payload).get("values")),
            next_page=following,
            required=required,
        )

    def _recursive_source_tree(self, root: str, revision: str) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        queue = [""]
        seen: set[str] = set()
        while queue:
            path = queue.pop(0).strip("/")
            if path in seen:
                continue
            seen.add(path)
            if len(seen) > self.retry_policy.max_pages:
                raise ProviderClientError("provider_pagination_limit_exceeded")
            suffix = f"/{quote(path, safe='/')}/" if path else "/"
            entries = self._bitbucket_pages(
                f"{root}/src/{quote(revision, safe='')}{suffix}",
                required=True,
            )
            for entry in entries:
                item = dict(entry)
                item_path = _text(item.get("path"))
                if not item_path:
                    continue
                output.append(item)
                if _text(item.get("type")).lower() in {
                    "commit_directory",
                    "directory",
                }:
                    queue.append(item_path)
        return output

    def list_authorized_repositories(self, workspace: str) -> list[Mapping[str, Any]]:
        if not _text(workspace):
            raise ProviderClientError("bitbucket_workspace_required")
        return self._bitbucket_pages(
            f"{self.api_url}/repositories/{quote(workspace, safe='')}",
            {"role": "member", "sort": "full_name"},
        )

    def build_exact_source_url(
        self,
        workspace: str,
        slug: str,
        revision: str,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        web_base = self.base_url.replace("api.bitbucket.org", "bitbucket.org")
        url = (
            f"{web_base}/{quote(workspace, safe='')}/{quote(slug, safe='')}/src/"
            f"{quote(revision, safe='')}/{quote(path, safe='/')}"
        )
        if start_line is not None:
            url += f"#lines-{start_line}"
            if end_line is not None and end_line >= start_line:
                url += f":{end_line}"
        return url

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        if "/" not in str(repository_id):
            raise ProviderClientError("bitbucket_repository_must_be_workspace_slug")
        workspace, slug = str(repository_id).split("/", 1)
        root = f"{self.api_url}/repositories/{quote(workspace, safe='')}/{quote(slug, safe='')}"
        repository_raw, _ = self._get(root, required=True)
        repository = dict(_mapping(repository_raw))
        if revision:
            commit_raw, _ = self._get(
                f"{root}/commit/{quote(revision, safe='')}",
                required=True,
            )
            commits = [dict(_mapping(commit_raw))]
        else:
            commits = self._bitbucket_pages(f"{root}/commits", required=True)
        observed_revision = commits[0].get("hash") if commits else ""
        exact_revision = _immutable_revision(revision, observed_revision)
        branches = self._optional_collection(
            Capability.BRANCHES,
            lambda: self._bitbucket_pages(f"{root}/refs/branches"),
        )
        tags = self._optional_collection(
            Capability.TAGS,
            lambda: self._bitbucket_pages(f"{root}/refs/tags"),
        )
        source_tree = self._recursive_source_tree(root, exact_revision)
        self._require_source_tree(source_tree)
        pull_requests = self._optional_collection(
            Capability.CHANGE_REQUESTS,
            lambda: self._bitbucket_pages(f"{root}/pullrequests", {"state": "ALL"}),
        )
        pipeline_query = f'target.commit.hash="{exact_revision}"'
        raw_pipelines = self._optional_collection(
            Capability.CI_RUNS,
            lambda: self._bitbucket_pages(
                f"{root}/pipelines/",
                {"sort": "-created_on", "q": pipeline_query},
            ),
        )
        pipelines = [
            item
            for item in raw_pipelines
            if _text(
                _mapping(_mapping(item.get("target")).get("commit")).get("hash")
            ).casefold()
            == exact_revision.casefold()
        ]
        pipeline_jobs: list[Mapping[str, Any]] = []
        if not self._inherit_parent_capability(Capability.CI_JOBS, Capability.CI_RUNS):
            for pipeline in self._bounded_nested_parents(pipelines, Capability.CI_JOBS):
                pipeline_id = _text(pipeline.get("uuid") or pipeline.get("build_number"))
                if pipeline_id:
                    try:
                        steps = self._bitbucket_pages(
                            f"{root}/pipelines/{quote(pipeline_id, safe='')}/steps/"
                        )
                    except ProviderClientError as exc:
                        self._record_optional_failure(Capability.CI_JOBS, exc)
                        break
                    for step in steps:
                        pipeline_jobs.append({**dict(step), "pipeline_id": pipeline_id})
            if self._capability(Capability.CI_JOBS) is None:
                self._set_capability(
                    Capability.CI_JOBS,
                    CapabilityState.SUPPORTED if pipeline_jobs else CapabilityState.SUPPORTED_EMPTY,
                )
        issues = self._optional_collection(
            Capability.WORK_ITEMS,
            lambda: self._bitbucket_pages(f"{root}/issues", {"sort": "-updated_on"}),
        )
        environments = self._optional_collection(
            Capability.ENVIRONMENTS,
            lambda: self._bitbucket_pages(f"{root}/environments"),
        )
        deployments = self._optional_collection(
            Capability.DEPLOYMENTS,
            lambda: self._bitbucket_pages(f"{root}/deployments/"),
        )
        for capability in (
            Capability.REPOSITORY,
            Capability.COMMITS,
            Capability.TREE,
            Capability.BLOBS,
            Capability.SOURCE_LINKS,
        ):
            self._set_capability(capability, CapabilityState.SUPPORTED)
        self._set_capability(
            Capability.RELEASES,
            CapabilityState.UNAVAILABLE_PROVIDER,
            "Bitbucket Cloud does not expose a repository release object equivalent through this acquisition path",
        )
        collected_at = _utc_now()
        immutable_repository_id = _text(repository.get("uuid") or repository_id)
        payload = {
            "instance_url": self.base_url,
            "repository": repository,
            "revision": exact_revision,
            "commits": commits,
            "branches": branches,
            "tags": tags,
            "source_tree": source_tree,
            "pull_requests": pull_requests,
            "pipelines": pipelines,
            "pipeline_jobs": pipeline_jobs,
            "issues": issues,
            "environments": environments,
            "deployments": deployments,
            "releases": [],
            "scopes": list(self.credential_reference.scopes) if self.credential_used else [],
            "access_mode": self.actual_access_mode.value,
            "credential_used": self.credential_used,
            "capability_status": list(self.capability_status),
            "pagination_complete": self.pagination_complete,
            "collection_limitations": list(dict.fromkeys(self.collection_limitations)),
            "rate_limit_state": dict(self.rate_limit_state),
            "snapshot_manifest_sha256": _snapshot_manifest_sha256(
                self.provider, immutable_repository_id, exact_revision, source_tree
            ),
            "collected_at": collected_at,
        }
        return self._collection(
            repository_id=immutable_repository_id,
            revision=exact_revision,
            payload=payload,
            collected_at=collected_at,
        )


class AzureDevOpsClient(BaseProviderClient):
    provider = ProviderKind.AZURE_DEVOPS

    def __init__(
        self,
        *,
        organization: str,
        project: str,
        instance_url: str = "https://dev.azure.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.organization = _text(organization)
        self.project = _text(project)
        if not self.organization or not self.project:
            raise ProviderClientError("azure_organization_and_project_required")
        self.project_url = f"{self.base_url}/{quote(self.organization, safe='')}/{quote(self.project, safe='')}"

    def _azure_pages(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        required: bool = False,
    ) -> list[Mapping[str, Any]]:
        base_params = {"api-version": "7.1", **dict(params or {})}

        def following(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
            del payload, page
            token = _text(headers.get("x-ms-continuationtoken"))
            if not token:
                return None
            return url, {**base_params, "continuationToken": token}

        return self._paginate(
            url=url,
            params=base_params,
            items=lambda payload: _list(_mapping(payload).get("value")),
            next_page=following,
            required=required,
        )

    def list_authorized_repositories(self) -> list[Mapping[str, Any]]:
        return self._azure_pages(f"{self.project_url}/_apis/git/repositories")

    def build_exact_source_url(
        self,
        repository: Mapping[str, Any],
        revision: str,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        repository_name = _text(repository.get("name") or repository.get("id"))
        params: dict[str, str] = {
            "path": "/" + path.lstrip("/"),
            "version": f"GC{revision}",
        }
        if start_line is not None:
            params["line"] = str(start_line)
            if end_line is not None and end_line >= start_line:
                params["lineEnd"] = str(end_line)
        return (
            f"{self.project_url}/_git/{quote(repository_name, safe='')}?"
            f"{urlencode(params)}"
        )

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        encoded_repo = quote(str(repository_id), safe="")
        git_root = f"{self.project_url}/_apis/git/repositories/{encoded_repo}"
        repository_raw, _ = self._get(
            git_root,
            params={"api-version": "7.1"},
            required=True,
        )
        repository = dict(_mapping(repository_raw))
        commits = self._azure_pages(
            f"{git_root}/commits",
            {"$top": 100, "searchCriteria.itemVersion.version": revision} if revision else {"$top": 100},
            required=True,
        )
        observed_revision = commits[0].get("commitId") if commits else ""
        exact_revision = _immutable_revision(revision, observed_revision)
        branches = self._optional_collection(
            Capability.BRANCHES,
            lambda: self._azure_pages(f"{git_root}/refs", {"filter": "heads/"}),
        )
        tags = self._optional_collection(
            Capability.TAGS,
            lambda: self._azure_pages(f"{git_root}/refs", {"filter": "tags/"}),
        )
        source_tree = self._azure_pages(
            f"{git_root}/items",
            {
                "scopePath": "/",
                "recursionLevel": "Full",
                "includeContentMetadata": "true",
                "versionDescriptor.version": exact_revision,
                "versionDescriptor.versionType": "commit",
            },
            required=True,
        )
        self._require_source_tree(source_tree)
        pull_requests = self._optional_collection(
            Capability.CHANGE_REQUESTS,
            lambda: self._azure_pages(
                f"{git_root}/pullrequests",
                {"searchCriteria.status": "all"},
            ),
        )
        builds = self._optional_collection(
            Capability.CI_RUNS,
            lambda: self._azure_pages(
                f"{self.project_url}/_apis/build/builds",
                {"repositoryId": repository.get("id") or repository_id, "sourceVersion": exact_revision},
            ),
        )
        pipeline_jobs: list[Mapping[str, Any]] = []
        if not self._inherit_parent_capability(Capability.CI_JOBS, Capability.CI_RUNS):
            for build in self._bounded_nested_parents(builds, Capability.CI_JOBS):
                build_id = _text(build.get("id"))
                if not build_id:
                    continue
                try:
                    timeline_raw, _ = self._get(
                        f"{self.project_url}/_apis/build/builds/{quote(build_id, safe='')}/timeline",
                        params={"api-version": "7.1"},
                    )
                except ProviderClientError as exc:
                    self._record_optional_failure(Capability.CI_JOBS, exc)
                    break
                for record in _list(_mapping(timeline_raw).get("records")):
                    if _text(record.get("type")).lower() in {"job", "stage", "task"}:
                        pipeline_jobs.append({**dict(record), "build_id": build_id})
            if self._capability(Capability.CI_JOBS) is None:
                self._set_capability(
                    Capability.CI_JOBS,
                    CapabilityState.SUPPORTED if pipeline_jobs else CapabilityState.SUPPORTED_EMPTY,
                )
        environments = self._optional_collection(
            Capability.ENVIRONMENTS,
            lambda: self._azure_pages(f"{self.project_url}/_apis/distributedtask/environments"),
        )
        deployments: list[Mapping[str, Any]] = []
        deployment_parents: Sequence[Mapping[str, Any]] = ()
        if not self._inherit_parent_capability(Capability.DEPLOYMENTS, Capability.ENVIRONMENTS):
            deployment_parents = self._bounded_nested_parents(
                environments,
                Capability.DEPLOYMENTS,
            )
        for environment in deployment_parents:
            environment_id = _text(environment.get("id"))
            if environment_id:
                try:
                    environment_deployments = self._azure_pages(
                        f"{self.project_url}/_apis/distributedtask/environments/"
                        f"{quote(environment_id, safe='')}/environmentdeploymentrecords"
                    )
                except ProviderClientError as exc:
                    self._record_optional_failure(Capability.DEPLOYMENTS, exc)
                    break
                for deployment in environment_deployments:
                    deployments.append({**dict(deployment), "environment_id": environment_id})
        if deployment_parents and self._capability(Capability.DEPLOYMENTS) is None:
            self._set_capability(
                Capability.DEPLOYMENTS,
                CapabilityState.SUPPORTED if deployments else CapabilityState.SUPPORTED_EMPTY,
            )
        for capability in (
            Capability.REPOSITORY,
            Capability.COMMITS,
            Capability.TREE,
            Capability.BLOBS,
            Capability.SOURCE_LINKS,
        ):
            self._set_capability(capability, CapabilityState.SUPPORTED)
        self._set_capability(
            Capability.RELEASES,
            CapabilityState.NOT_CONFIGURED,
            "Azure release evidence uses a separate authorized service boundary and was not configured",
        )
        collected_at = _utc_now()
        immutable_repository_id = _text(repository.get("id") or repository_id)
        payload = {
            "instance_url": self.base_url,
            "organization": self.organization,
            "project": repository.get("project") or {"name": self.project},
            "repository": repository,
            "revision": exact_revision,
            "commits": commits,
            "refs": branches,
            "tags": tags,
            "source_tree": source_tree,
            "pull_requests": pull_requests,
            "builds": builds,
            "pipeline_jobs": pipeline_jobs,
            "environments": environments,
            "deployments": deployments,
            "releases": [],
            "scopes": list(self.credential_reference.scopes) if self.credential_used else [],
            "access_mode": self.actual_access_mode.value,
            "credential_used": self.credential_used,
            "capability_status": list(self.capability_status),
            "pagination_complete": self.pagination_complete,
            "collection_limitations": list(dict.fromkeys(self.collection_limitations)),
            "rate_limit_state": dict(self.rate_limit_state),
            "snapshot_manifest_sha256": _snapshot_manifest_sha256(
                self.provider, immutable_repository_id, exact_revision, source_tree
            ),
            "collected_at": collected_at,
        }
        return self._collection(
            repository_id=immutable_repository_id,
            revision=exact_revision,
            payload=payload,
            collected_at=collected_at,
        )


__all__ = [
    "AzureDevOpsClient",
    "BaseProviderClient",
    "BitbucketCloudClient",
    "GitLabClient",
    "ProviderClientError",
    "ProviderCollection",
    "RetryPolicy",
]
