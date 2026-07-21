from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

import httpx

from nico.provider_credentials import (
    CredentialError,
    ResolvedCredential,
    assert_url_allowed,
    authorization_headers,
)
from nico.provider_neutral_contract import ProviderKind
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


class BaseProviderClient:
    provider: ProviderKind

    def __init__(
        self,
        *,
        base_url: str,
        credential: ResolvedCredential,
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        normalized = str(base_url or "").rstrip("/")
        assert_url_allowed(credential.reference, normalized)
        if credential.reference.provider is not self.provider:
            raise CredentialError("provider_credential_kind_mismatch")
        self.base_url = normalized
        self.credential = credential
        self.retry_policy = retry_policy or RetryPolicy()
        self.retry_policy.validate()
        self._client = client or httpx.Client(timeout=self.retry_policy.timeout_seconds)
        self._owns_client = client is None
        self._sleeper = sleeper
        self.requests_made = 0
        self.pages_fetched = 0

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

    def _get(self, url: str, *, params: Mapping[str, Any] | None = None) -> tuple[Any, httpx.Headers]:
        assert_url_allowed(self.credential.reference, url)
        last_error: ProviderClientError | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.requests_made += 1
            try:
                response = self._client.get(
                    url,
                    params=dict(params or {}),
                    headers={
                        **authorization_headers(self.credential),
                        "Accept": "application/json",
                        "User-Agent": "nico-provider-collector/1",
                    },
                    timeout=self.retry_policy.timeout_seconds,
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

            status = response.status_code
            if status in {401, 403}:
                raise ProviderClientError("provider_auth_failed", status_code=status)
            if status == 404:
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
    ) -> list[Mapping[str, Any]]:
        output: list[Mapping[str, Any]] = []
        current_url = url
        current_params = dict(params or {})
        for page_number in range(1, self.retry_policy.max_pages + 1):
            payload, headers = self._get(current_url, params=current_params)
            self.pages_fetched += 1
            output.extend(items(payload))
            following = next_page(payload, headers, page_number)
            if following is None:
                return output
            current_url, current_params = following
            assert_url_allowed(self.credential.reference, current_url)
        raise ProviderClientError("provider_pagination_limit_exceeded")


class GitLabClient(BaseProviderClient):
    provider = ProviderKind.GITLAB

    def __init__(self, *, instance_url: str = "https://gitlab.com", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/api/v4"

    @staticmethod
    def _next(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
        del payload, page
        next_page = _text(headers.get("x-next-page"))
        if not next_page:
            return None
        return "", {"page": next_page}

    def _gitlab_pages(self, url: str, params: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
        base_params = {"per_page": 100, **dict(params or {})}

        def following(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
            del payload, page
            token = _text(headers.get("x-next-page"))
            if not token:
                return None
            return url, {**base_params, "page": token}

        return self._paginate(url=url, params=base_params, items=_list, next_page=following)

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        encoded = quote(str(repository_id), safe="")
        root = f"{self.api_url}/projects/{encoded}"
        project_raw, _ = self._get(root)
        project = dict(_mapping(project_raw))
        commits = self._gitlab_pages(
            f"{root}/repository/commits",
            {"ref_name": revision or _text(project.get("default_branch") or "main")},
        )
        exact_revision = _text(revision or (commits[0].get("id") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        branches = self._gitlab_pages(f"{root}/repository/branches")
        merge_requests = self._gitlab_pages(f"{root}/merge_requests", {"state": "all"})
        pipelines = self._gitlab_pages(f"{root}/pipelines", {"sha": exact_revision})
        issues = self._gitlab_pages(f"{root}/issues", {"state": "all"})
        releases = self._gitlab_pages(f"{root}/releases")
        collected_at = _utc_now()
        payload = {
            "instance_url": self.base_url,
            "project": project,
            "revision": exact_revision,
            "commits": commits,
            "branches": branches,
            "merge_requests": merge_requests,
            "pipelines": pipelines,
            "issues": issues,
            "releases": releases,
            "scopes": list(self.credential.reference.scopes or ("read_api", "read_repository")),
            "collected_at": collected_at,
        }
        return ProviderCollection(
            provider=self.provider,
            repository_id=_text(project.get("id") or repository_id),
            revision=exact_revision,
            payload=payload,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
            collected_at=collected_at,
        )


class BitbucketCloudClient(BaseProviderClient):
    provider = ProviderKind.BITBUCKET

    def __init__(self, *, instance_url: str = "https://api.bitbucket.org", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/2.0"

    def _bitbucket_pages(self, url: str, params: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
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
        )

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        if "/" not in str(repository_id):
            raise ProviderClientError("bitbucket_repository_must_be_workspace_slug")
        workspace, slug = str(repository_id).split("/", 1)
        root = f"{self.api_url}/repositories/{quote(workspace, safe='')}/{quote(slug, safe='')}"
        repository_raw, _ = self._get(root)
        repository = dict(_mapping(repository_raw))
        commits = self._bitbucket_pages(f"{root}/commits/{quote(revision, safe='')}" if revision else f"{root}/commits")
        exact_revision = _text(revision or (commits[0].get("hash") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        branches = self._bitbucket_pages(f"{root}/refs/branches")
        pull_requests = self._bitbucket_pages(f"{root}/pullrequests", {"state": "ALL"})
        pipelines = self._bitbucket_pages(f"{root}/pipelines/", {"sort": "-created_on"})
        issues: list[Mapping[str, Any]] = []
        try:
            issues = self._bitbucket_pages(f"{root}/issues", {"sort": "-updated_on"})
        except ProviderClientError as exc:
            if exc.status_code != 404:
                raise
        collected_at = _utc_now()
        payload = {
            "instance_url": self.base_url,
            "repository": repository,
            "revision": exact_revision,
            "commits": commits,
            "branches": branches,
            "pull_requests": pull_requests,
            "pipelines": pipelines,
            "issues": issues,
            "scopes": list(
                self.credential.reference.scopes
                or ("repository:read", "pullrequest:read", "pipeline:read")
            ),
            "collected_at": collected_at,
        }
        return ProviderCollection(
            provider=self.provider,
            repository_id=_text(repository.get("uuid") or repository_id),
            revision=exact_revision,
            payload=payload,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
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

    def _azure_pages(self, url: str, params: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
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
        )

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        encoded_repo = quote(str(repository_id), safe="")
        git_root = f"{self.project_url}/_apis/git/repositories/{encoded_repo}"
        repository_raw, _ = self._get(git_root, params={"api-version": "7.1"})
        repository = dict(_mapping(repository_raw))
        commits = self._azure_pages(
            f"{git_root}/commits",
            {"$top": 100, "searchCriteria.itemVersion.version": revision} if revision else {"$top": 100},
        )
        exact_revision = _text(revision or (commits[0].get("commitId") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        refs = self._azure_pages(f"{git_root}/refs", {"filter": "heads/"})
        pull_requests = self._azure_pages(
            f"{git_root}/pullrequests",
            {"searchCriteria.status": "all"},
        )
        builds = self._azure_pages(
            f"{self.project_url}/_apis/build/builds",
            {"repositoryId": repository.get("id") or repository_id, "sourceVersion": exact_revision},
        )
        collected_at = _utc_now()
        payload = {
            "instance_url": self.base_url,
            "project": repository.get("project") or {"name": self.project},
            "repository": repository,
            "revision": exact_revision,
            "commits": commits,
            "refs": refs,
            "pull_requests": pull_requests,
            "builds": builds,
            "scopes": list(self.credential.reference.scopes or ("vso.code", "vso.build", "vso.work")),
            "collected_at": collected_at,
        }
        return ProviderCollection(
            provider=self.provider,
            repository_id=_text(repository.get("id") or repository_id),
            revision=exact_revision,
            payload=payload,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
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
