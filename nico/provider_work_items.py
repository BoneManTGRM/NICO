from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import httpx

from nico.provider_credentials import ResolvedCredential, assert_url_allowed, authorization_headers
from nico.provider_live_clients import ProviderClientError, RetryPolicy
from nico.provider_neutral_contract import ProviderKind


@dataclass(frozen=True)
class CanonicalWorkItem:
    provider: ProviderKind
    native_id: str
    project_id: str
    repository_id: str
    item_type: str
    title: str
    state: str
    assignee: str
    created_at: str
    updated_at: str
    url: str
    source_fingerprint: str


@dataclass(frozen=True)
class WorkItemCollection:
    provider: ProviderKind
    project_id: str
    repository_id: str
    items: tuple[CanonicalWorkItem, ...]
    collected_at: str
    requests_made: int
    pages_fetched: int
    warnings: tuple[str, ...] = ()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _fingerprint(parts: tuple[str, ...]) -> str:
    return f"sha256:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def adapt_gitlab_issues(
    issues: Sequence[Mapping[str, Any]],
    *,
    project_id: str,
    repository_id: str,
) -> tuple[CanonicalWorkItem, ...]:
    output: list[CanonicalWorkItem] = []
    for issue in issues:
        native_id = _text(issue.get("iid") or issue.get("id"))
        if not native_id:
            continue
        assignee = _mapping(issue.get("assignee"))
        title = _text(issue.get("title"))
        state = _text(issue.get("state") or "unknown").lower()
        created = _text(issue.get("created_at"))
        updated = _text(issue.get("updated_at") or created)
        url = _text(issue.get("web_url"))
        output.append(
            CanonicalWorkItem(
                provider=ProviderKind.GITLAB,
                native_id=native_id,
                project_id=project_id,
                repository_id=repository_id,
                item_type="issue",
                title=title,
                state=state,
                assignee=_text(assignee.get("username") or assignee.get("name")),
                created_at=created,
                updated_at=updated,
                url=url,
                source_fingerprint=_fingerprint(("gitlab", project_id, repository_id, native_id, title, state, updated)),
            )
        )
    return tuple(output)


def adapt_bitbucket_issues(
    issues: Sequence[Mapping[str, Any]],
    *,
    project_id: str,
    repository_id: str,
) -> tuple[CanonicalWorkItem, ...]:
    output: list[CanonicalWorkItem] = []
    for issue in issues:
        native_id = _text(issue.get("id"))
        if not native_id:
            continue
        assignee = _mapping(issue.get("assignee"))
        links = _mapping(issue.get("links"))
        html = _mapping(links.get("html"))
        title = _text(issue.get("title"))
        state = _text(issue.get("state") or "unknown").lower()
        created = _text(issue.get("created_on"))
        updated = _text(issue.get("updated_on") or created)
        output.append(
            CanonicalWorkItem(
                provider=ProviderKind.BITBUCKET,
                native_id=native_id,
                project_id=project_id,
                repository_id=repository_id,
                item_type=_text(issue.get("kind") or "issue").lower(),
                title=title,
                state=state,
                assignee=_text(assignee.get("display_name") or assignee.get("nickname")),
                created_at=created,
                updated_at=updated,
                url=_text(html.get("href")),
                source_fingerprint=_fingerprint(("bitbucket", project_id, repository_id, native_id, title, state, updated)),
            )
        )
    return tuple(output)


class AzureBoardsClient:
    provider = ProviderKind.AZURE_DEVOPS

    def __init__(
        self,
        *,
        organization: str,
        project: str,
        credential: ResolvedCredential,
        instance_url: str = "https://dev.azure.com",
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper=time.sleep,
    ) -> None:
        self.base_url = str(instance_url or "").rstrip("/")
        assert_url_allowed(credential.reference, self.base_url)
        if credential.reference.provider is not ProviderKind.AZURE_DEVOPS:
            raise ProviderClientError("provider_credential_kind_mismatch")
        self.organization = _text(organization)
        self.project = _text(project)
        if not self.organization or not self.project:
            raise ProviderClientError("azure_organization_and_project_required")
        self.credential = credential
        self.retry_policy = retry_policy or RetryPolicy()
        self.retry_policy.validate()
        self._client = client or httpx.Client(timeout=self.retry_policy.timeout_seconds)
        self._owns_client = client is None
        self._sleeper = sleeper
        self.requests_made = 0
        self.pages_fetched = 0
        self.project_url = f"{self.base_url}/{quote(self.organization, safe='')}/{quote(self.project, safe='')}"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, method: str, url: str, *, json_body: Mapping[str, Any]) -> Mapping[str, Any]:
        assert_url_allowed(self.credential.reference, url)
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.requests_made += 1
            try:
                response = self._client.request(
                    method,
                    url,
                    params={"api-version": "7.1"},
                    json=dict(json_body),
                    headers={
                        **authorization_headers(self.credential),
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "nico-azure-boards-collector/1",
                    },
                    timeout=self.retry_policy.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.retry_policy.max_attempts:
                    raise ProviderClientError("provider_network_unavailable", retryable=True) from exc
                self._sleeper(min(self.retry_policy.max_delay_seconds, self.retry_policy.base_delay_seconds * 2 ** (attempt - 1)))
                continue
            if response.status_code in {401, 403}:
                raise ProviderClientError("provider_auth_failed", status_code=response.status_code)
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt >= self.retry_policy.max_attempts:
                    code = "provider_rate_limited" if response.status_code == 429 else "provider_service_unavailable"
                    raise ProviderClientError(code, status_code=response.status_code, retryable=True)
                self._sleeper(min(self.retry_policy.max_delay_seconds, self.retry_policy.base_delay_seconds * 2 ** (attempt - 1)))
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise ProviderClientError("provider_request_failed", status_code=response.status_code)
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderClientError("provider_response_not_json", status_code=response.status_code) from exc
            if not isinstance(payload, Mapping):
                raise ProviderClientError("provider_response_shape_invalid")
            return payload
        raise ProviderClientError("provider_request_failed")

    def collect(
        self,
        *,
        repository_id: str,
        wiql: str = "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project ORDER BY [System.ChangedDate] DESC",
        max_items: int = 1000,
    ) -> WorkItemCollection:
        if max_items < 1 or max_items > 20_000:
            raise ValueError("azure_boards_max_items_invalid")
        wiql_url = f"{self.project_url}/_apis/wit/wiql"
        query = self._request("POST", wiql_url, json_body={"query": wiql})
        self.pages_fetched += 1
        refs = _sequence(query.get("workItems"))[:max_items]
        ids = [int(item["id"]) for item in refs if str(item.get("id") or "").isdigit()]
        if not ids:
            return WorkItemCollection(
                provider=self.provider,
                project_id=self.project,
                repository_id=repository_id,
                items=(),
                collected_at=_utc_now(),
                requests_made=self.requests_made,
                pages_fetched=self.pages_fetched,
            )
        fields = [
            "System.Id",
            "System.WorkItemType",
            "System.Title",
            "System.State",
            "System.AssignedTo",
            "System.CreatedDate",
            "System.ChangedDate",
        ]
        output: list[CanonicalWorkItem] = []
        for start in range(0, len(ids), 200):
            batch_ids = ids[start : start + 200]
            payload = self._request(
                "POST",
                f"{self.project_url}/_apis/wit/workitemsbatch",
                json_body={"ids": batch_ids, "fields": fields, "errorPolicy": "Omit"},
            )
            self.pages_fetched += 1
            for item in _sequence(payload.get("value")):
                native_id = _text(item.get("id"))
                data = _mapping(item.get("fields"))
                if not native_id:
                    continue
                assignee = data.get("System.AssignedTo")
                if isinstance(assignee, Mapping):
                    assignee_text = _text(assignee.get("displayName") or assignee.get("uniqueName"))
                else:
                    assignee_text = _text(assignee)
                title = _text(data.get("System.Title"))
                state = _text(data.get("System.State") or "unknown").lower()
                updated = _text(data.get("System.ChangedDate"))
                output.append(
                    CanonicalWorkItem(
                        provider=self.provider,
                        native_id=native_id,
                        project_id=self.project,
                        repository_id=repository_id,
                        item_type=_text(data.get("System.WorkItemType") or "work_item").lower(),
                        title=title,
                        state=state,
                        assignee=assignee_text,
                        created_at=_text(data.get("System.CreatedDate")),
                        updated_at=updated,
                        url=_text(item.get("url")),
                        source_fingerprint=_fingerprint(("azure_devops", self.project, repository_id, native_id, title, state, updated)),
                    )
                )
        return WorkItemCollection(
            provider=self.provider,
            project_id=self.project,
            repository_id=repository_id,
            items=tuple(output),
            collected_at=_utc_now(),
            requests_made=self.requests_made,
            pages_fetched=self.pages_fetched,
        )


__all__ = [
    "AzureBoardsClient",
    "CanonicalWorkItem",
    "WorkItemCollection",
    "adapt_bitbucket_issues",
    "adapt_gitlab_issues",
]
