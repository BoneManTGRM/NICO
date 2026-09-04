from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_AUDIENCE = "https://app.nicoaudit.com/nico-production-proof"
SESSION_COOKIE = "nico-specialist-session"
SESSION_HEADER = "X-NICO-Operator-Session"


def _https_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("production_proof_frontend_origin_invalid")
    if parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError("production_proof_frontend_origin_invalid")
    if parsed.query or parsed.fragment:
        raise ValueError("production_proof_frontend_origin_invalid")
    return f"https://{parsed.netloc}"


def _read_json(response: Any) -> dict[str, Any]:
    value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("production_proof_auth_response_invalid")
    return value


def acquire_production_proof_session(frontend_url: str) -> tuple[str, dict[str, str]]:
    """Exchange the current GitHub Actions OIDC identity for a restricted NICO session.

    Neither the GitHub OIDC token nor the resulting NICO session is printed, persisted,
    written to workflow outputs, or included in retained proof artifacts.
    """

    origin = _https_origin(frontend_url)
    request_url = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")).strip()
    request_token = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")).strip()
    if not request_url or not request_token:
        raise ValueError("github_actions_oidc_environment_unavailable")
    audience = str(
        os.getenv("NICO_GITHUB_ACTIONS_OIDC_AUDIENCE", DEFAULT_AUDIENCE)
    ).strip()
    separator = "&" if "?" in request_url else "?"
    oidc_url = request_url + separator + urllib.parse.urlencode({"audience": audience})
    oidc_request = urllib.request.Request(
        oidc_url,
        headers={
            "Authorization": f"Bearer {request_token}",
            "Accept": "application/json",
            "User-Agent": "nico-production-proof-auth",
        },
    )
    with urllib.request.urlopen(oidc_request, timeout=30) as response:
        oidc_payload = _read_json(response)
    oidc_token = str(oidc_payload.get("value") or "").strip()
    if not oidc_token:
        raise ValueError("github_actions_oidc_token_unavailable")

    exchange_request = urllib.request.Request(
        origin + "/api/nico/ci-session",
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {oidc_token}",
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "User-Agent": "nico-production-proof-auth",
        },
    )
    with urllib.request.urlopen(exchange_request, timeout=45) as response:
        session_payload = _read_json(response)
    session = str(session_payload.get("session_token") or "").strip()
    scope = str(session_payload.get("scope") or "").strip()
    release_sha = str(session_payload.get("release_sha") or "").strip().lower()
    expected_sha = str(os.getenv("RELEASE_SHA", "")).strip().lower()
    if (
        not session
        or scope != "nico_production_proof"
        or not expected_sha
        or release_sha != expected_sha
    ):
        raise ValueError("production_proof_session_exchange_invalid")
    retained = {
        "scope": scope,
        "release_sha": release_sha,
        "repository": str(session_payload.get("repository") or ""),
        "workflow_ref": str(session_payload.get("workflow_ref") or ""),
        "run_id": str(session_payload.get("run_id") or ""),
        "run_attempt": str(session_payload.get("run_attempt") or ""),
        "oidc_audience": str(session_payload.get("oidc_audience") or ""),
    }
    return session, retained


class AuthenticatedBrowser:
    """Wrap Playwright Browser so every context starts inside the proof session."""

    def __init__(self, browser: Any, *, session: str, frontend_url: str) -> None:
        self._browser = browser
        self._session = session
        self._origin = _https_origin(frontend_url)

    def new_context(self, *args: Any, **kwargs: Any) -> Any:
        existing = dict(kwargs.get("extra_http_headers") or {})
        existing[SESSION_HEADER] = self._session
        kwargs["extra_http_headers"] = existing
        context = self._browser.new_context(*args, **kwargs)
        context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE,
                    "value": self._session,
                    "url": self._origin,
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Strict",
                }
            ]
        )
        return context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)


def install_authenticated_httpx_client(module: Any, session: str) -> None:
    """Add the restricted session to direct report/status reads in one proof process."""

    httpx_module = module.httpx
    original = getattr(httpx_module.Client, "_nico_proof_original", httpx_module.Client)

    def authenticated_client(*args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.get("headers") or {})
        headers[SESSION_HEADER] = session
        kwargs["headers"] = headers
        return original(*args, **kwargs)

    setattr(authenticated_client, "_nico_proof_original", original)
    httpx_module.Client = authenticated_client


__all__ = [
    "AuthenticatedBrowser",
    "acquire_production_proof_session",
    "install_authenticated_httpx_client",
]
