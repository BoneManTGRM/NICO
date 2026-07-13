from __future__ import annotations

import hashlib
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from nico.production_smoke_config import SmokeFailure

class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None

class UrlLibTransport:
    def __init__(self, backend_url: str, admin_token: str, *, timeout_seconds: float = 120.0) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.admin_token = admin_token
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirectHandler())

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        admin: bool = False,
    ) -> dict[str, Any]:
        parsed_path = urlsplit(path)
        if (
            not parsed_path.path.startswith("/")
            or parsed_path.scheme
            or parsed_path.netloc
            or parsed_path.fragment
            or (parsed_path.query and not admin)
            or "\\" in path
        ):
            raise SmokeFailure("unsafe_request_path", "Production smoke request path was not a safe relative API path.")
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "nico-production-smoke/1",
        }
        if admin:
            headers["X-NICO-Admin-Token"] = self.admin_token
        request = Request(f"{self.backend_url}{path}", data=body, method=method.upper(), headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
        except HTTPError as exc:
            raise SmokeFailure("api_http_error", f"Production API returned HTTP {exc.code} for {path}.") from None
        except (URLError, TimeoutError) as exc:
            raise SmokeFailure("api_transport_error", f"Production API transport failed for {path}: {type(exc).__name__}.") from None
        if status < 200 or status >= 300:
            raise SmokeFailure("api_http_error", f"Production API returned HTTP {status} for {path}.")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SmokeFailure("invalid_json", f"Production API returned invalid JSON for {path}.") from None
        if not isinstance(value, dict):
            raise SmokeFailure("invalid_payload", f"Production API returned a non-object payload for {path}.")
        return value

def verify_deployment_statuses(
    repository: str,
    sha: str,
    github_token: str,
    *,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    request = Request(
        f"https://api.github.com/repos/{repository}/commits/{sha}/status",
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nico-production-smoke/1",
        },
    )
    try:
        with opener(request, timeout=30.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SmokeFailure("deployment_status_error", f"GitHub deployment status lookup returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeFailure("deployment_status_error", f"GitHub deployment status lookup failed: {type(exc).__name__}.") from None
    statuses = payload.get("statuses") if isinstance(payload, dict) else None
    if not isinstance(statuses, list):
        raise SmokeFailure("deployment_status_error", "GitHub deployment status response did not include status contexts.")
    latest: dict[str, dict[str, str]] = {}
    for item in statuses:
        if not isinstance(item, dict):
            continue
        context = str(item.get("context") or "")[:120]
        state = str(item.get("state") or "unknown").lower()
        target = urlparse(str(item.get("target_url") or ""))
        host = str(target.hostname or "").lower()
        provider = ""
        if context == "Vercel" and (host == "vercel.com" or host.endswith(".vercel.com")):
            provider = "vercel"
        elif host == "railway.com" or host.endswith(".railway.com"):
            provider = "railway"
        # GitHub returns statuses newest first. Retain only the latest trusted
        # context for each deployment provider so a stale success cannot mask a
        # newer pending or failed deployment.
        if provider and provider not in latest:
            latest[provider] = {"context": context, "state": state, "provider": provider}

    failed = [provider for provider in ("vercel", "railway") if latest.get(provider, {}).get("state") != "success"]
    if failed:
        raise SmokeFailure(
            "deployment_not_verified",
            f"Latest required deployment checks are not successful for this commit: {', '.join(failed)}.",
        )
    return {
        "status": "passed",
        "frontend_commit": sha,
        "backend_commit": sha,
        "checks": [latest["vercel"], latest["railway"]],
    }

