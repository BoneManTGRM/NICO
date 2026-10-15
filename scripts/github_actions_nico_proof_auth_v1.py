from __future__ import annotations

import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_AUDIENCE = "https://app.nicoaudit.com/nico-production-proof"
SESSION_COOKIE = "nico-specialist-session"
SESSION_HEADER = "X-NICO-Operator-Session"


_PROOF_SECRETS: set[str] = set()

# Script entrypoints and package callers must share the same redaction registry.
for _alias in ('github_actions_nico_proof_auth_v1', 'scripts.github_actions_nico_proof_auth_v1'):
    sys.modules.setdefault(_alias, sys.modules[__name__])


def _runner_mask_command(value: str) -> None:
    """FD9 is reserved and opened BEFORE any retained stdout/stderr pipeline.

    Affected xvfb-run versions own/close FD3 for their client; reserve FD9.

    Mask data intentionally contains the credential and may go only to this
    runner command pipe, never ordinary stdout/stderr or an artifact file.
    Missing/closed/file-backed channels fail closed; there is no log fallback.
    """
    try:
        if os.getenv('NICO_PROOF_MASK_FD') != '9' or not stat.S_ISFIFO(os.fstat(9).st_mode):
            raise ValueError
        escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        data = ('::add-mask::' + escaped + '\n').encode('utf-8')
        while data:
            written = os.write(9, data)
            if written <= 0:
                raise OSError
            data = data[written:]
    except (OSError, ValueError):
        raise RuntimeError('production_proof_runner_mask_channel_unavailable') from None


def _register_proof_secret(value: str) -> None:
    if not value:
        return
    _PROOF_SECRETS.add(value)
    if os.getenv("GITHUB_ACTIONS") == "true":
        _runner_mask_command(value)


def redact_proof_secrets(value: Any) -> Any:
    """Sanitize artifacts too: Actions masks do not cover uploaded file bytes."""
    if isinstance(value, str):
        for secret in sorted(_PROOF_SECRETS, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {redact_proof_secrets(key): redact_proof_secrets(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_proof_secrets(item) for item in value]
    return value


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


def _open_oidc_response(request: urllib.request.Request, deadline: float) -> Any:
    """Retry only temporary HTTP gateway/service failures before token parsing.

    Three attempts share a 30-second monotonic budget, with 1/2-second backoff.
    urllib's timeout bounds socket operations, not total wall time; callers must
    also reject a response that finishes after the deadline before exchanging it.
    """
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("github_actions_oidc_get_deadline_exceeded")
        try:
            return urllib.request.urlopen(request, timeout=min(10.0, remaining))
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status not in {502, 503, 504}:
                raise RuntimeError("github_actions_oidc_get_http_failure") from None
            if attempt == 2:
                raise RuntimeError("github_actions_oidc_get_temporary_failure_exhausted") from None
        except (urllib.error.URLError, OSError):
            raise RuntimeError("github_actions_oidc_get_transport_failure") from None
        delay = attempt + 1
        if deadline - time.monotonic() <= delay:
            raise RuntimeError("github_actions_oidc_get_deadline_exceeded")
        time.sleep(delay)
    raise AssertionError("unreachable")


def acquire_production_proof_session(frontend_url: str) -> tuple[str, dict[str, str]]:
    """Exchange the current GitHub Actions OIDC identity for a restricted NICO session.

    Credentials are registered with Actions masking, never emitted as ordinary
    log text or workflow outputs. Registered values are scrubbed from proof artifacts.
    """

    origin = _https_origin(frontend_url)
    request_url = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")).strip()
    request_token = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")).strip()
    if not request_url or not request_token:
        raise ValueError("github_actions_oidc_environment_unavailable")
    _register_proof_secret(request_token)
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
    deadline = time.monotonic() + 30.0
    with _open_oidc_response(oidc_request, deadline) as response:
        try:
            oidc_payload = _read_json(response)
        except (ValueError, UnicodeError):
            raise ValueError("github_actions_oidc_response_invalid") from None
        except (urllib.error.URLError, OSError):
            raise RuntimeError("github_actions_oidc_get_transport_failure") from None
    if time.monotonic() >= deadline:
        raise RuntimeError("github_actions_oidc_get_deadline_exceeded")
    oidc_token = oidc_payload.get("value")
    if not isinstance(oidc_token, str) or not oidc_token.strip():
        raise ValueError("github_actions_oidc_token_unavailable")
    oidc_token = oidc_token.strip()

    _register_proof_secret(oidc_token)
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
    _register_proof_secret(session)
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
    """Wrap Playwright Browser so NICO-origin requests carry the proof session.

    The session is installed only as a Secure, HttpOnly, SameSite=Strict cookie for
    the exact production frontend origin. It is deliberately not added to global
    Playwright extra HTTP headers, so navigations or subresources to third-party
    origins cannot receive the NICO proof credential.
    """

    def __init__(self, browser: Any, *, session: str, frontend_url: str) -> None:
        self._browser = browser
        self._session = session
        self._origin = _https_origin(frontend_url)

    def new_context(self, *args: Any, **kwargs: Any) -> Any:
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
    """Add the restricted session to direct NICO report/status reads in one proof process."""

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
