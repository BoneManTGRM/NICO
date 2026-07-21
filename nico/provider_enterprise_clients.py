from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from nico.provider_live_clients import (
    BaseProviderClient,
    ProviderClientError,
    ProviderCollection,
)
from nico.provider_neutral_contract import ProviderKind


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _values(value: Any) -> list[Mapping[str, Any]]:
    payload = _mapping(value)
    raw = payload.get("values")
    return [item for item in raw or () if isinstance(item, Mapping)]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BitbucketDataCenterClient(BaseProviderClient):
    """Read-only Bitbucket Server/Data Center collector using REST API 1.0."""

    provider = ProviderKind.BITBUCKET

    def __init__(self, *, instance_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=instance_url, **kwargs)
        self.api_url = f"{self.base_url}/rest/api/1.0"
        self.build_status_url = f"{self.base_url}/rest/build-status/1.0"

    def _pages(self, url: str, params: Mapping[str, Any] | None = None) -> list[Mapping[str, Any]]:
        base_params = {"limit": 100, **dict(params or {})}

        def following(payload: Any, headers: httpx.Headers, page: int):
            del headers, page
            data = _mapping(payload)
            if bool(data.get("isLastPage", True)):
                return None
            next_start = data.get("nextPageStart")
            if next_start is None:
                raise ProviderClientError("bitbucket_dc_pagination_cursor_missing")
            return url, {**base_params, "start": next_start}

        return self._paginate(
            url=url,
            params=base_params,
            items=_values,
            next_page=following,
        )

    @staticmethod
    def _pull_request(item: Mapping[str, Any]) -> dict[str, Any]:
        source = _mapping(item.get("fromRef"))
        target = _mapping(item.get("toRef"))
        author = _mapping(_mapping(item.get("author")).get("user"))
        state = _text(item.get("state")).upper()
        updated = item.get("updatedDate") or item.get("createdDate")
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "state": state,
            "source": {"branch": {"name": source.get("displayId") or source.get("id")}},
            "destination": {"branch": {"name": target.get("displayId") or target.get("id")}},
            "author": {"display_name": author.get("displayName") or author.get("name")},
            "created_on": str(item.get("createdDate") or ""),
            "updated_on": str(updated or ""),
            "review_state": "approved" if state == "MERGED" else "unknown",
        }

    @staticmethod
    def _pipeline(item: Mapping[str, Any], *, revision: str, branch: str) -> dict[str, Any]:
        state = _text(item.get("state") or item.get("status") or "UNKNOWN").upper()
        return {
            "uuid": item.get("key") or item.get("id"),
            "name": item.get("name") or item.get("key") or "build-status",
            "target": {"commit": {"hash": revision}, "ref_name": branch},
            "state": {"name": state},
            "result": state,
            "created_on": str(item.get("dateAdded") or ""),
            "completed_on": str(item.get("dateAdded") or ""),
            "links": {"html": {"href": item.get("url") or ""}},
        }

    def collect(self, repository_id: str, *, revision: str = "") -> ProviderCollection:
        if "/" not in str(repository_id):
            raise ProviderClientError("bitbucket_dc_repository_must_be_project_slug")
        project_key, repo_slug = str(repository_id).split("/", 1)
        encoded_project = quote(project_key, safe="")
        encoded_repo = quote(repo_slug, safe="")
        root = f"{self.api_url}/projects/{encoded_project}/repos/{encoded_repo}"
        repository_raw, _ = self._get(root)
        repository_source = dict(_mapping(repository_raw))
        default_branch_raw, _ = self._get(f"{root}/branches/default")
        default_branch = dict(_mapping(default_branch_raw))
        commits = self._pages(
            f"{root}/commits",
            {"until": revision or default_branch.get("id") or "refs/heads/main"},
        )
        exact_revision = _text(revision or (commits[0].get("id") if commits else ""))
        if not exact_revision:
            raise ProviderClientError("provider_snapshot_revision_missing")
        branches = self._pages(f"{root}/branches")
        raw_pull_requests = self._pages(f"{root}/pull-requests", {"state": "ALL"})
        build_raw, _ = self._get(f"{self.build_status_url}/commits/{quote(exact_revision, safe='')}")
        build_items = _values(build_raw)
        branch_name = _text(default_branch.get("displayId") or "main")
        repository = {
            **repository_source,
            "id": repository_source.get("id") or f"{project_key}/{repo_slug}",
            "slug": repository_source.get("slug") or repo_slug,
            "project_key": _mapping(repository_source.get("project")).get("key") or project_key,
            "default_branch": branch_name,
        }
        collected_at = _utc_now()
        payload = {
            "instance_url": self.base_url,
            "repository": repository,
            "revision": exact_revision,
            "commits": commits,
            "branches": branches,
            "pull_requests": [self._pull_request(item) for item in raw_pull_requests],
            "pipelines": [
                self._pipeline(item, revision=exact_revision, branch=branch_name)
                for item in build_items
            ],
            "scopes": list(
                self.credential.reference.scopes
                or ("repository:read", "pullrequest:read", "build-status:read")
            ),
            "collected_at": collected_at,
        }
        return ProviderCollection(
            provider=self.provider,
            repository_id=_text(repository.get("id")),
            revision=exact_revision,
            payload=payload,
            pages_fetched=self.pages_fetched,
            requests_made=self.requests_made,
            collected_at=collected_at,
        )


__all__ = ["BitbucketDataCenterClient"]
