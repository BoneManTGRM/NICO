"""Candidate GitHub App user-token authorization read; no OAuth or token storage."""
from collections.abc import Mapping
import json

import httpx

from .github_requester_standing import verify_commissioning_authority

_API = "https://api.github.com"
_PAGE_SIZE = 100
_MAX_PAGES = 5


def _get(client: httpx.Client, path: str, headers, params=None):
    with client.stream("GET", _API + path, headers=headers, params=params,
                       follow_redirects=False, timeout=4) as response:
        if response.status_code != 200:
            raise ValueError("provider_authorization_unavailable")
        chunks = bytearray()
        for chunk in response.iter_bytes():
            chunks.extend(chunk)
            if len(chunks) > 2 * 1024 * 1024:
                raise ValueError("provider_response_too_large")
        obj = json.loads(chunks)
        if not isinstance(obj, Mapping):
            raise ValueError("provider_response_invalid")
        return obj


def _list(client, path, key, headers):
    count = None
    rows = {}
    for page in range(1, _MAX_PAGES + 1):
        doc = _get(client, path, headers, {"page": page, "per_page": _PAGE_SIZE})
        n = doc.get("total_count")
        if (type(n) is not int or not 0 <= n <= _PAGE_SIZE * _MAX_PAGES
                or (count is not None and n != count)):
            raise ValueError("provider_pagination_unverified")
        count = n
        batch = doc.get(key)
        if type(batch) is not list or len(batch) != min(_PAGE_SIZE, count - len(rows)):
            raise ValueError("provider_page_incomplete")
        for row in batch:
            ident = row.get("id") if isinstance(row, Mapping) else None
            if type(ident) is not int or ident <= 0 or ident in rows:
                raise ValueError("provider_duplicate_or_unverified_id")
            rows[ident] = row
        if len(rows) == count:
            return rows
    raise ValueError("provider_pagination_unverified")


def check_requester(client: httpx.Client, *, user_token: str, actor_id: int,
                    app_id: int, installation_id: int, repository_id: int):
    """Fail closed; token and expected IDs must come from the trusted server."""
    if any(type(v) is not int or v <= 0
           for v in (actor_id, app_id, installation_id, repository_id)):
        return None
    if (type(user_token) is not str or not user_token
            or not user_token.isascii() or not user_token.replace("_", "").isalnum()):
        return None
    headers = {"Authorization": "Bearer " + user_token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache, no-store"}
    try:
        user = _get(client, "/user", headers)
        if type(user.get("id")) is not int or user["id"] != actor_id or user.get("type") != "User":
            return None
        entries = _list(client, "/user/installations", "installations", headers)
        installation = entries.get(installation_id)
        if (installation is None or type(installation.get("app_id")) is not int
                or installation["app_id"] != app_id or "suspended_at" not in installation
                or installation["suspended_at"] is not None):
            return None
        repos = _list(client, f"/user/installations/{installation_id}/repositories", "repositories", headers)
        repo = repos.get(repository_id)
        return verify_commissioning_authority(
            repository_details=repo, authenticated_user=user, user_installations=(installation,),
            installation_repositories=(repo,), expected_actor_id=actor_id, expected_app_id=app_id,
            expected_installation_id=installation_id, expected_repository_id=repository_id)
    except (ValueError, httpx.HTTPError, UnicodeError):
        return None
