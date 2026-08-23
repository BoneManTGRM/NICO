from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote, urlencode

import httpx

from nico.provider_credentials import (
    CredentialError,
    ResolvedCredential,
    assert_url_allowed,
    authorization_headers,
)
from nico.provider_neutral_contract import Capability, CapabilityState, ProviderKind
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
        self.rate_limit_state: dict[str, str] = {}
        self.collection_limitations: list[str] = []
        self.capability_status: list[dict[str, str]] = []

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
                        "User-Agent": "nico-provider-collector/2",
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

            self._capture_rate_limit(response.headers)
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
        seen_pages: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for page_number in range(1, self.retry_policy.max_pages + 1):
            identity = (
                current_url,
                tuple(sorted((str(key), str(value)) for key, value in current_params.items())),
            )
            if identity in seen_pages:
                raise ProviderClientError("provider_pagination_loop_detected")
            seen_pages.add(identity)
            payload, headers = self._get(current_url, params=current_params)
            self.pages_fetched += 1
            output.extend(items(payload))
            following = next_page(payload, headers, page_number)
            if following is None:
                return output
            current_url, current_params = following
            assert_url_allowed(self.credential.reference, current_url)
        raise ProviderClientError("provider_pagination_limit_exceeded")

    def _optional_collection(
        self,
        capability: Capability,
        loader: Callable[[], list[Mapping[str, Any]]],
    ) -> list[Mapping[str, Any]]:
        try:
            values = loader()
        except ProviderClientError as exc:
            if exc.status_code == 403:
                reason = f"{capability.value} evidence unavailable with current provider permission"
                self.capability_status.append(
                    _capability_status(capability, CapabilityState.UNAVAILABLE_PERMISSION, reason)
                )
                self.collection_limitations.append(reason)
                return []
            if exc.status_code == 404:
                reason = f"{capability.value} is unavailable from this provider or repository"
                self.capability_status.append(
                    _capability_status(capability, CapabilityState.UNAVAILABLE_PROVIDER, reason)
                )
                self.collection_limitations.append(reason)
                return []
            raise
        self.capability_status.append(_capability_status(capability, CapabilityState.SUPPORTED))
        return values

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
            pagination_complete=True,
            rate_limit_state=dict(self.rate_limit_state),
            collection_limitations=tuple(dict.fromkeys(self.collection_limitations)),
        )


class GitLabClient(BaseProviderClient):
    provider = ProviderKind.GITLAB

    def __init__(self, *, instance_url: str = "https://gitlab.com", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/api/v4"

    def _gitlab_pages(self, url: str, params: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
        base_params = {"per_page": 100, **dict(params or {})}

        def following(payload: Any, headers: httpx.Headers, page: int) -> tuple[str, Mapping[str, Any]] | None:
            del payload, page
            token = _text(headers.get("x-next-page"))
            if not token:
                return None
            return url, {**base_params, "page": token}

        return self._paginate(url=url, params=base_params, items=_list, next_page=following)

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
        source_tree = self._gitlab_pages(
            f"{root}/repository/tree",
            {"ref": exact_revision, "recursive": "true"},
        )
        tags = self._gitlab_pages(f"{root}/repository/tags")
        merge_requests = self._gitlab_pages(f"{root}/merge_requests", {"state": "all"})
        pipelines = self._gitlab_pages(f"{root}/pipelines", {"sha": exact_revision})
        pipeline_jobs: list[Mapping[str, Any]] = []
        for pipeline in pipelines:
            pipeline_id = _text(pipeline.get("id"))
            if pipeline_id:
                for job in self._optional_collection(
                    Capability.CI_JOBS,
                    lambda pipeline_id=pipeline_id: self._gitlab_pages(
                        f"{root}/pipelines/{quote(pipeline_id, safe='')}/jobs"
                    ),
                ):
                    pipeline_jobs.append({**dict(job), "pipeline_id": pipeline_id})
        issues = self._gitlab_pages(f"{root}/issues", {"state": "all"})
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
        self.capability_status.extend(
            _capability_status(capability, CapabilityState.SUPPORTED)
            for capability in (
                Capability.REPOSITORY,
                Capability.COMMITS,
                Capability.BRANCHES,
                Capability.TREE,
                Capability.BLOBS,
                Capability.TAGS,
                Capability.CHANGE_REQUESTS,
                Capability.CI_RUNS,
                Capability.SOURCE_LINKS,
            )
        )
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
            "scopes": list(self.credential.reference.scopes or ("read_api", "read_repository")),
            "capability_status": list(self.capability_status),
            "pagination_complete": True,
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
        repository_raw, _ = self._get(root)
        repository = dict(_mapping(repository_raw))
        commits = self._bitbucket_pages(
            f"{root}/commits/{quote(revision, safe='')}" if revision else f"{root}/commits"
        )
        exact_revision = _text(revision or (commits[0].get("hash") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        branches = self._bitbucket_pages(f"{root}/refs/branches")
        tags = self._bitbucket_pages(f"{root}/refs/tags")
        source_tree = self._bitbucket_pages(
            f"{root}/src/{quote(exact_revision, safe='')}/",
            {"format": "meta"},
        )
        pull_requests = self._bitbucket_pages(f"{root}/pullrequests", {"state": "ALL"})
        pipelines = self._bitbucket_pages(f"{root}/pipelines/", {"sort": "-created_on"})
        pipeline_jobs: list[Mapping[str, Any]] = []
        for pipeline in pipelines:
            pipeline_id = _text(pipeline.get("uuid") or pipeline.get("build_number"))
            if pipeline_id:
                for step in self._optional_collection(
                    Capability.CI_JOBS,
                    lambda pipeline_id=pipeline_id: self._bitbucket_pages(
                        f"{root}/pipelines/{quote(pipeline_id, safe='')}/steps/"
                    ),
                ):
                    pipeline_jobs.append({**dict(step), "pipeline_id": pipeline_id})
        issues: list[Mapping[str, Any]] = []
        try:
            issues = self._bitbucket_pages(f"{root}/issues", {"sort": "-updated_on"})
        except ProviderClientError as exc:
            if exc.status_code != 404:
                raise
        environments = self._optional_collection(
            Capability.ENVIRONMENTS,
            lambda: self._bitbucket_pages(f"{root}/environments"),
        )
        deployments = self._optional_collection(
            Capability.DEPLOYMENTS,
            lambda: self._bitbucket_pages(f"{root}/deployments/"),
        )
        self.capability_status.extend(
            _capability_status(capability, CapabilityState.SUPPORTED)
            for capability in (
                Capability.REPOSITORY,
                Capability.COMMITS,
                Capability.BRANCHES,
                Capability.TREE,
                Capability.BLOBS,
                Capability.TAGS,
                Capability.CHANGE_REQUESTS,
                Capability.CI_RUNS,
                Capability.SOURCE_LINKS,
            )
        )
        self.capability_status.append(
            _capability_status(
                Capability.RELEASES,
                CapabilityState.UNAVAILABLE_PROVIDER,
                "Bitbucket Cloud does not expose a repository release object equivalent through this acquisition path",
            )
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
            "scopes": list(
                self.credential.reference.scopes
                or ("repository:read", "pullrequest:read", "pipeline:read")
            ),
            "capability_status": list(self.capability_status),
            "pagination_complete": True,
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
        repository_raw, _ = self._get(git_root, params={"api-version": "7.1"})
        repository = dict(_mapping(repository_raw))
        commits = self._azure_pages(
            f"{git_root}/commits",
            {"$top": 100, "searchCriteria.itemVersion.version": revision} if revision else {"$top": 100},
        )
        exact_revision = _text(revision or (commits[0].get("commitId") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        branches = self._azure_pages(f"{git_root}/refs", {"filter": "heads/"})
        tags = self._azure_pages(f"{git_root}/refs", {"filter": "tags/"})
        source_tree = self._azure_pages(
            f"{git_root}/items",
            {
                "scopePath": "/",
                "recursionLevel": "Full",
                "includeContentMetadata": "true",
                "versionDescriptor.version": exact_revision,
                "versionDescriptor.versionType": "commit",
            },
        )
        pull_requests = self._azure_pages(
            f"{git_root}/pullrequests",
            {"searchCriteria.status": "all"},
        )
        builds = self._azure_pages(
            f"{self.project_url}/_apis/build/builds",
            {"repositoryId": repository.get("id") or repository_id, "sourceVersion": exact_revision},
        )
        pipeline_jobs: list[Mapping[str, Any]] = []
        for build in builds:
            build_id = _text(build.get("id"))
            if not build_id:
                continue
            timeline_raw, _ = self._get(
                f"{self.project_url}/_apis/build/builds/{quote(build_id, safe='')}/timeline",
                params={"api-version": "7.1"},
            )
            for record in _list(_mapping(timeline_raw).get("records")):
                if _text(record.get("type")).lower() in {"job", "stage", "task"}:
                    pipeline_jobs.append({**dict(record), "build_id": build_id})
        environments = self._optional_collection(
            Capability.ENVIRONMENTS,
            lambda: self._azure_pages(f"{self.project_url}/_apis/distributedtask/environments"),
        )
        deployments: list[Mapping[str, Any]] = []
        for environment in environments:
            environment_id = _text(environment.get("id"))
            if environment_id:
                for deployment in self._optional_collection(
                    Capability.DEPLOYMENTS,
                    lambda environment_id=environment_id: self._azure_pages(
                        f"{self.project_url}/_apis/distributedtask/environments/"
                        f"{quote(environment_id, safe='')}/environmentdeploymentrecords"
                    ),
                ):
                    deployments.append({**dict(deployment), "environment_id": environment_id})
        self.capability_status.extend(
            _capability_status(capability, CapabilityState.SUPPORTED)
            for capability in (
                Capability.REPOSITORY,
                Capability.COMMITS,
                Capability.BRANCHES,
                Capability.TREE,
                Capability.BLOBS,
                Capability.TAGS,
                Capability.CHANGE_REQUESTS,
                Capability.CI_RUNS,
                Capability.CI_JOBS,
                Capability.SOURCE_LINKS,
            )
        )
        self.capability_status.append(
            _capability_status(
                Capability.RELEASES,
                CapabilityState.NOT_CONFIGURED,
                "Azure release evidence uses a separate authorized service boundary and was not configured",
            )
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
            "scopes": list(self.credential.reference.scopes or ("vso.code", "vso.build", "vso.work")),
            "capability_status": list(self.capability_status),
            "pagination_complete": True,
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
