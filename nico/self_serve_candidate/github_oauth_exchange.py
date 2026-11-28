"""Dormant GitHub App user-token exchange; never mounts a route or stores secrets."""
import json
import re

import httpx

from .oauth_state import Pending, TOKEN
from .provider_download import VerifiedSession

_TOKEN_URL = "https://github.com/login/oauth/access_token"
_ACTOR_URL = "https://api.github.com/user"
_USER_TOKEN = re.compile(r"ghu_[A-Za-z0-9_]{20,252}")
_CODE = re.compile(r"[A-Za-z0-9._~-]{1,256}")
_CLIENT = re.compile(r"[A-Za-z0-9_]{5,128}")


def _object(client, method, url, *, headers, data=None):
    with client.stream(method, url, headers=headers, data=data, timeout=5,
                       follow_redirects=False) as response:
        if response.status_code != 200:
            return None
        data = bytearray()
        for chunk in response.iter_bytes(chunk_size=4096):
            data.extend(chunk)
            if len(data) > 64 * 1024:
                return None
        result = json.loads(data)
        return result if type(result) is dict else None


def exchange_github_actor(client: httpx.Client, *, client_id: str, client_secret: str,
                          code: str, pending: Pending, configured_redirect: str):
    """Call only after committed state consumption; use a dedicated TLS-verifying client.

    The resulting server-only session identity is not a repository assessment grant.
    A caller still needs fresh repository standing and must cap session lifetime.
    """
    if (type(client_id) is not str or _CLIENT.fullmatch(client_id) is None
            or type(client_secret) is not str or not 1 <= len(client_secret) <= 256
            or not client_secret.isascii() or not client_secret.isalnum()
            or type(code) is not str or _CODE.fullmatch(code) is None
            or type(pending) is not Pending or type(pending.verifier) is not str
            or TOKEN.fullmatch(pending.verifier) is None
            or type(configured_redirect) is not str or not configured_redirect.startswith("https://")
            or pending.redirect_uri != configured_redirect):
        return None
    try:
        token_doc = _object(
            client, "POST", _TOKEN_URL,
            headers={"Accept": "application/json", "Cache-Control": "no-store"},
            data={"client_id": client_id, "client_secret": client_secret,
                  "code": code, "redirect_uri": configured_redirect, "code_verifier": pending.verifier},
        )
        if (token_doc is None or "error" in token_doc or token_doc.get("token_type") != "bearer"
                or token_doc.get("scope") != "" or type(token_doc.get("expires_in")) is not int
                or token_doc["expires_in"] != 28800):
            return None
        token = token_doc.get("access_token")
        if type(token) is not str or _USER_TOKEN.fullmatch(token) is None:
            return None
        actor = _object(client, "GET", _ACTOR_URL,
                        headers={"Authorization": "Bearer " + token,
                                 "Accept": "application/vnd.github+json",
                                 "X-GitHub-Api-Version": "2022-11-28",
                                 "Cache-Control": "no-cache, no-store"})
        if actor is None or actor.get("type") != "User" or type(actor.get("id")) is not int or actor["id"] <= 0:
            return None
        return VerifiedSession(actor["id"], token)
    except (ValueError, UnicodeError, httpx.HTTPError):
        return None
