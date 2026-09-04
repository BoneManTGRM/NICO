#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

AUDIENCE = "nico-production-proof"
SESSION_COOKIE = "nico-specialist-session"
VERSION = "nico.github_actions_proof_session_client.v1"


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name.lower()}_required")
    return value


def request_github_oidc_token(*, timeout_seconds: float = 30.0) -> str:
    request_url = _required_environment("ACTIONS_ID_TOKEN_REQUEST_URL")
    request_token = _required_environment("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    separator = "&" if "?" in request_url else "?"
    url = request_url + separator + urllib.parse.urlencode({"audience": AUDIENCE})
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"bearer {request_token}",
            "Accept": "application/json",
            "User-Agent": "nico-production-proof-oidc",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = str(payload.get("value") or "").strip() if isinstance(payload, dict) else ""
    if token.count(".") != 2 or len(token) < 100:
        raise RuntimeError("github_actions_oidc_token_unavailable")
    return token


def cookie_header(context: Any, frontend_origin: str) -> str:
    cookies = context.cookies(frontend_origin.rstrip("/"))
    values = [
        f"{item['name']}={item['value']}"
        for item in cookies
        if str(item.get("name") or "") == SESSION_COOKIE
        and str(item.get("value") or "")
    ]
    if len(values) != 1:
        raise RuntimeError("nico_specialist_session_cookie_unavailable")
    return values[0]


def authenticate_browser_context(
    context: Any,
    frontend_origin: str,
    *,
    timeout_ms: int = 60_000,
) -> dict[str, Any]:
    origin = frontend_origin.rstrip("/")
    oidc_token = request_github_oidc_token()
    response = context.request.post(
        f"{origin}/api/nico/github-actions-proof-session",
        data={"oidc_token": oidc_token},
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-store",
        },
        timeout=timeout_ms,
        fail_on_status_code=False,
    )
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(
            f"github_actions_proof_session_invalid_response:http_{response.status}"
        ) from exc
    if response.status != 200 or not isinstance(payload, dict) or payload.get("status") != "authenticated":
        code = str(payload.get("code") or payload.get("detail") or "unknown") if isinstance(payload, dict) else "unknown"
        raise RuntimeError(
            f"github_actions_proof_session_rejected:http_{response.status}:{code[:160]}"
        )
    header = cookie_header(context, origin)
    return {
        "artifact_schema": VERSION,
        "status": "authenticated",
        "authority": str(payload.get("authority") or ""),
        "release_sha": str(payload.get("release_sha") or ""),
        "workflow_file": str(payload.get("workflow_file") or ""),
        "run_id": str(payload.get("run_id") or ""),
        "run_attempt": str(payload.get("run_attempt") or ""),
        "session_cookie_present": header.startswith(f"{SESSION_COOKIE}="),
        "session_cookie_value_exposed": False,
        "oidc_token_exposed": False,
        "human_review_required": payload.get("human_review_required") is True,
        "client_delivery_allowed": payload.get("client_delivery_allowed") is True,
    }


__all__ = [
    "AUDIENCE",
    "SESSION_COOKIE",
    "VERSION",
    "authenticate_browser_context",
    "cookie_header",
    "request_github_oidc_token",
]
