from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from nico.provider_live_clients import BaseProviderClient, ProviderClientError
from nico.provider_neutral_contract import ProviderKind
from nico.provider_work_items import WorkItemCollection, adapt_bitbucket_issues, adapt_gitlab_issues


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GitLabIssueClient(BaseProviderClient):
    provider = ProviderKind.GITLAB

    def __init__(self, *, instance_url: str = "https://gitlab.com", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/api/v4"

    def collect(
        self,
        project: str,
        *,
        repository_id: str = "",
        state: str = "all",
    ) -> WorkItemCollection:
        encoded = quote(str(project or ""), safe="")
        if not encoded:
            raise ProviderClientError("gitlab_project_required")
        state_token = str(state or "all").lower()
        if state_token not in {"all", "opened", "closed"}:
            raise ValueError("gitlab_issue_state_invalid")
        url = f"{self.api_url}/projects/{encoded}/issues"
        params = {"scope": "all", "state": state_token, "per_page": 100, "page": 1}

        def next_page(payload: Any, headers: httpx.Headers, page: int):
            del payload, page
            token = str(headers.get("X-Next-Page") or "").strip()
            if not token:
                return None
            return url, {**params, "page": int(token)}

        issues = self._paginate(
            url=url,
            params=params,
            items=_list,
            next_page=next_page,
        )
        native_repository_id = str(repository_id or project)
        items = adapt_gitlab_issues(
            issues,
            project_id=str(project),
            repository_id=native_repository_id,
        )
        return WorkItemCollection(
            provider=self.provider,
            project_id=str(project),
            repository_id=native_repository_id,
            items=items,
            collected_at=_utc_now(),
            requests_made=self.requests_made,
            pages_fetched=self.pages_fetched,
        )


class BitbucketCloudIssueClient(BaseProviderClient):
    provider = ProviderKind.BITBUCKET

    def __init__(self, *, instance_url: str = "https://api.bitbucket.org", **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/2.0"

    def collect(self, repository: str) -> WorkItemCollection:
        token = str(repository or "")
        if "/" not in token:
            raise ProviderClientError("bitbucket_repository_must_be_workspace_slug")
        workspace, repo_slug = token.split("/", 1)
        url = (
            f"{self.api_url}/repositories/"
            f"{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/issues"
        )
        params = {"pagelen": 100, "sort": "-updated_on"}

        def items(payload: Any) -> list[Mapping[str, Any]]:
            return _list(_mapping(payload).get("values"))

        def next_page(payload: Any, headers: httpx.Headers, page: int):
            del headers, page
            following = str(_mapping(payload).get("next") or "").strip()
            if not following:
                return None
            return following, None

        issues = self._paginate(
            url=url,
            params=params,
            items=items,
            next_page=next_page,
        )
        canonical = adapt_bitbucket_issues(
            issues,
            project_id=workspace,
            repository_id=token,
        )
        return WorkItemCollection(
            provider=self.provider,
            project_id=workspace,
            repository_id=token,
            items=canonical,
            collected_at=_utc_now(),
            requests_made=self.requests_made,
            pages_fetched=self.pages_fetched,
        )


__all__ = ["BitbucketCloudIssueClient", "GitLabIssueClient"]
