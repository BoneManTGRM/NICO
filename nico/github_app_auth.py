from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class GitHubAuthResult:
    headers: dict[str, str]
    mode: str
    evidence: list[str]
    unavailable: list[str]


def _base_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "NICO-hosted-assessment",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _secret_present(value: str | None) -> bool:
    return bool((value or "").strip())


def _private_key_from_env(value: str) -> str:
    return value.replace("\\n", "\n").strip()


def github_app_env_state() -> dict[str, bool]:
    return {
        "app_id": _secret_present(os.getenv("NICO_GITHUB_APP_ID")),
        "private_key": _secret_present(os.getenv("NICO_GITHUB_APP_PRIVATE_KEY")),
        "installation_id": _secret_present(os.getenv("NICO_GITHUB_APP_INSTALLATION_ID")),
    }


def github_app_configured() -> bool:
    state = github_app_env_state()
    return all(state.values())


def build_github_app_jwt(now: int | None = None) -> tuple[str | None, str | None]:
    app_id = os.getenv("NICO_GITHUB_APP_ID")
    private_key = os.getenv("NICO_GITHUB_APP_PRIVATE_KEY")
    if not app_id or not private_key:
        return None, "GitHub App credentials are incomplete."
    try:
        import jwt
    except Exception as exc:  # pragma: no cover - exercised when dependency is absent
        return None, f"PyJWT is unavailable for GitHub App JWT creation: {exc}"

    issued_at = int(now or time.time()) - 60
    payload = {
        "iat": issued_at,
        "exp": issued_at + 540,
        "iss": str(app_id),
    }
    try:
        token = jwt.encode(payload, _private_key_from_env(private_key), algorithm="RS256")
    except Exception as exc:
        return None, f"GitHub App JWT creation failed: {exc}"
    return str(token), None


def request_installation_token(app_jwt: str, *, session: Any = requests) -> tuple[str | None, str | None]:
    installation_id = os.getenv("NICO_GITHUB_APP_INSTALLATION_ID")
    if not installation_id:
        return None, "NICO_GITHUB_APP_INSTALLATION_ID is not configured."
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = _base_headers()
    headers["Authorization"] = f"Bearer {app_jwt}"
    try:
        response = session.post(url, headers=headers, timeout=20)
    except requests.RequestException as exc:
        return None, f"GitHub App installation token request failed: {exc}"
    if response.status_code >= 400:
        return None, f"GitHub App installation token request returned HTTP {response.status_code}."
    try:
        payload = response.json()
    except ValueError:
        return None, "GitHub App installation token request returned non-JSON response."
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        return None, "GitHub App installation token response did not include a token."
    return str(token), None


def build_github_auth_headers(*, session: Any = requests) -> GitHubAuthResult:
    headers = _base_headers()
    evidence: list[str] = []
    unavailable: list[str] = []

    if github_app_configured():
        app_jwt, jwt_error = build_github_app_jwt()
        if app_jwt:
            installation_token, token_error = request_installation_token(app_jwt, session=session)
            if installation_token:
                headers["Authorization"] = f"Bearer {installation_token}"
                evidence.append("GitHub App installation token was created server-side for authorized repository assessment.")
                return GitHubAuthResult(headers=headers, mode="github_app_installation", evidence=evidence, unavailable=unavailable)
            unavailable.append(token_error or "GitHub App installation token was unavailable.")
        else:
            unavailable.append(jwt_error or "GitHub App JWT was unavailable.")
    else:
        state = github_app_env_state()
        missing = [name for name, present in state.items() if not present]
        unavailable.append("GitHub App installation auth not configured: " + ", ".join(missing) + ".")

    token = os.getenv("NICO_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        evidence.append("Server-side GitHub token auth is configured for authorized repository assessment.")
        return GitHubAuthResult(headers=headers, mode="server_token", evidence=evidence, unavailable=unavailable)

    unavailable.append("No server-side GitHub credential is configured; private repositories will be unavailable.")
    return GitHubAuthResult(headers=headers, mode="anonymous", evidence=evidence, unavailable=unavailable)
