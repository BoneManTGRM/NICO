from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Mapping
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from nico.admin_security import require_comprehensive_operator
from nico.github_actions_proof_auth_v1 import (
    proof_audience,
    verify_github_actions_oidc_token,
)

VERSION = "nico.specialist_access.v2"
SESSION_ROUTE = "/assessment/comprehensive-operator/session"
GITHUB_ACTIONS_SESSION_ROUTE = "/assessment/github-actions-production-proof/session"
SESSION_HEADER = "x-nico-operator-session"
ADMIN_HEADER = "x-nico-admin-token"
SESSION_SIGNING_SECRET_ENV = "NICO_OPERATOR_SESSION_SIGNING_SECRET"
SPECIALIST_SCOPE = "nico_specialist_operation"
PRODUCTION_PROOF_SCOPE = "nico_production_proof"
_ALLOWED_SESSION_SCOPES = {SPECIALIST_SCOPE, PRODUCTION_PROOF_SCOPE}
_MINIMUM_SIGNING_SECRET_BYTES = 32
_PROTECTED_PREFIX = "/assessment/"
_PROOF_STATUS = re.compile(r"^/assessment/comprehensive-run/[^/]+$")
_PROOF_CONTINUE = re.compile(r"^/assessment/comprehensive-run/[^/]+/continue$")
_PROOF_ARTIFACT = re.compile(
    r"^/assessment/comprehensive-run/[^/]+/"
    r"(?:report/(?:markdown|html|json|pdf)|localized-report/(?:en|es-MX)(?:/pdf)?)$"
)


def _integer_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _session_ttl_seconds() -> int:
    return _integer_env("NICO_SPECIALIST_SESSION_TTL_SECONDS", 14_400, 300, 43_200)


def _session_secret() -> bytes | None:
    """Return only the dedicated high-entropy session-signing key.

    Operator passwords and the site-wide admin token are authentication credentials,
    not key-derivation material. Keeping the signing key separate permits independent
    rotation and avoids retaining or fast-hashing a password for secondary use.
    """

    value = os.getenv(SESSION_SIGNING_SECRET_ENV, "").strip().encode("utf-8")
    return value if len(value) >= _MINIMUM_SIGNING_SECRET_BYTES else None


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_specialist_session(
    authority: Mapping[str, Any],
    *,
    now: int | None = None,
    scope: str = SPECIALIST_SCOPE,
    ttl_seconds: int | None = None,
    retained_claims: Mapping[str, Any] | None = None,
) -> tuple[str, int]:
    secret = _session_secret()
    if secret is None:
        raise RuntimeError("specialist_session_signing_secret_unavailable")
    normalized_scope = str(scope or "").strip()
    if normalized_scope not in _ALLOWED_SESSION_SCOPES:
        raise ValueError("specialist_session_scope_invalid")
    issued_at = int(time.time() if now is None else now)
    default_ttl = _session_ttl_seconds()
    ttl = default_ttl if ttl_seconds is None else max(300, min(14_400, int(ttl_seconds)))
    payload: dict[str, Any] = {
        "v": 2,
        "iat": issued_at,
        "exp": issued_at + ttl,
        "authority": str(authority.get("authority") or "nico_comprehensive_operator"),
        "scope": normalized_scope,
    }
    if normalized_scope == PRODUCTION_PROOF_SCOPE:
        claims = retained_claims if isinstance(retained_claims, Mapping) else {}
        proof_role = str(claims.get("proof_role") or "producer")
        if proof_role not in {"producer", "consumer"}:
            raise ValueError("production_proof_session_role_invalid")
        payload["proof_role"] = proof_role
        for key in ("repository", "ref", "sha", "workflow_ref", "run_id", "run_attempt"):
            value = str(claims.get(key) or "").strip()
            if not value:
                raise ValueError(f"production_proof_session_{key}_required")
            payload[key] = value[:600]
    encoded = _b64url_encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _b64url_encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}", ttl


def validate_specialist_session(token: str | None, *, now: int | None = None) -> dict[str, Any] | None:
    secret = _session_secret()
    value = str(token or "").strip()
    if secret is None or not value or value.count(".") != 1 or len(value) > 4096:
        return None
    encoded, claimed_signature = value.split(".", 1)
    expected = _b64url_encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(claimed_signature, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("v") not in {1, 2}:
        return None
    current = int(time.time() if now is None else now)
    try:
        issued_at = int(payload.get("iat"))
        expires_at = int(payload.get("exp"))
    except (TypeError, ValueError):
        return None
    if issued_at > current + 60 or expires_at <= current or expires_at - issued_at > 43_200:
        return None
    scope = str(payload.get("scope") or "")
    if scope not in _ALLOWED_SESSION_SCOPES:
        return None
    if scope == PRODUCTION_PROOF_SCOPE and any(
        not str(payload.get(key) or "").strip()
        for key in ("repository", "ref", "sha", "workflow_ref", "run_id", "run_attempt")
    ):
        return None
    if scope == PRODUCTION_PROOF_SCOPE and payload.get("proof_role", "producer") not in {"producer", "consumer"}:
        return None
    return payload


def _protected_request(path: str) -> bool:
    if path in {SESSION_ROUTE, GITHUB_ACTIONS_SESSION_ROUTE}:
        return False
    return path == "/assessment" or path.startswith(_PROTECTED_PREFIX)


def _production_proof_request_allowed(method: str, path: str) -> bool:
    normalized_method = str(method or "").upper()
    if normalized_method == "POST" and path == "/assessment/comprehensive-intake":
        return True
    if normalized_method == "GET" and _PROOF_STATUS.fullmatch(path):
        return True
    if normalized_method == "POST" and _PROOF_CONTINUE.fullmatch(path):
        return True
    if normalized_method == "GET" and _PROOF_ARTIFACT.fullmatch(path):
        return True
    return False


def _credential_fingerprint(request: Request, raw_token: str, session_token: str) -> str:
    """Return a non-reversible keyed rate-limit identity without storing credentials."""

    secret = _session_secret()
    if secret is None:
        return "specialist-session-signing-unconfigured"
    credential = session_token or raw_token
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    credential_digest = hmac.new(
        secret,
        credential.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.new(
        secret,
        f"{credential_digest}:{host}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class _BoundedRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allowed(self, key: str, bucket: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        identity = (key, bucket)
        with self._lock:
            events = self._events[identity]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            if len(self._events) > 4096:
                stale = [item for item, values in self._events.items() if not values or values[-1] <= cutoff]
                for item in stale[:1024]:
                    self._events.pop(item, None)
            return True


_RATE_LIMITER = _BoundedRateLimiter()


def _rate_limit_response() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "status": "blocked",
            "detail": {
                "code": "specialist_request_rate_limited",
                "message": "The authenticated specialist request limit was reached. Retry after the bounded window.",
                "retryable": True,
            },
        },
        headers={"Cache-Control": "no-store", "Retry-After": "60"},
    )


def _authentication_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "blocked",
            "detail": {
                "code": code,
                "message": "Authenticated NICO specialist access is required.",
                "retryable": False,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


async def _specialist_access_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method == "OPTIONS" or not _protected_request(request.url.path):
        return await call_next(request)

    raw_token = request.headers.get(ADMIN_HEADER, "").strip()
    session_token = request.headers.get(SESSION_HEADER, "").strip()
    authority: dict[str, Any] | None = None
    if raw_token:
        allowed, status = require_comprehensive_operator(raw_token)
        if not allowed:
            return _authentication_response(403, "specialist_operator_authentication_invalid")
        authority = dict(status)
    elif session_token:
        authority = validate_specialist_session(session_token)
        if authority is None:
            return _authentication_response(401, "specialist_session_invalid_or_expired")
    else:
        return _authentication_response(401, "specialist_authentication_required")

    if (
        authority.get("scope") == PRODUCTION_PROOF_SCOPE
        and (
            not _production_proof_request_allowed(request.method, request.url.path)
            or (authority.get("proof_role") == "consumer" and request.method != "GET")
        )
    ):
        return _authentication_response(403, "production_proof_session_scope_forbidden")

    key = _credential_fingerprint(request, raw_token, session_token)
    general_limit = _integer_env("NICO_SPECIALIST_REQUEST_LIMIT_PER_MINUTE", 240, 30, 5000)
    if not _RATE_LIMITER.allowed(key, "general", limit=general_limit, window_seconds=60):
        return _rate_limit_response()
    if request.method == "POST" and request.url.path in {
        "/assessment/comprehensive-intake",
        "/assessment/express-run",
        "/assessment/mid-run",
        "/assessment/github",
        "/assessment/mid",
    }:
        intake_limit = _integer_env("NICO_SPECIALIST_INTAKE_LIMIT_PER_HOUR", 12, 1, 500)
        if not _RATE_LIMITER.allowed(key, "intake", limit=intake_limit, window_seconds=3600):
            return _rate_limit_response()

    request.state.nico_specialist_authority = authority
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, private, max-age=0"
    return response


def _bearer_token(value: str) -> str:
    scheme, _, token = str(value or "").strip().partition(" ")
    if scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail={
                "code": "github_actions_oidc_bearer_required",
                "message": "A GitHub Actions OIDC bearer token is required.",
            },
        )
    return token.strip()


def install_specialist_access(app: FastAPI) -> dict[str, Any]:
    if getattr(app.state, "nico_specialist_access_v1", None):
        return dict(app.state.nico_specialist_access_v1)

    async def create_session(
        request: Request,
        x_nico_admin_token: str = Header(default=""),
    ) -> dict[str, Any]:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        host = forwarded or (request.client.host if request.client else "unknown")
        login_key = hashlib.sha256(host.encode("utf-8")).hexdigest()
        login_limit = _integer_env("NICO_SPECIALIST_LOGIN_LIMIT_PER_MINUTE", 10, 1, 100)
        if not _RATE_LIMITER.allowed(login_key, "login", limit=login_limit, window_seconds=60):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "specialist_login_rate_limited",
                    "message": "Too many specialist sign-in attempts. Retry after the bounded window.",
                },
                headers={"Retry-After": "60"},
            )
        allowed, status = require_comprehensive_operator(x_nico_admin_token)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "specialist_operator_authentication_invalid",
                    "message": "The NICO operator password was not accepted.",
                },
            )
        try:
            session_token, expires_in = issue_specialist_session(status)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": str(exc),
                    "message": "Specialist session signing is not configured.",
                },
            ) from exc
        return {
            "status": "authenticated",
            "artifact_schema": VERSION,
            "session_token": session_token,
            "expires_in": expires_in,
            "scope": SPECIALIST_SCOPE,
        }

    async def validate_session(
        x_nico_operator_session: str = Header(default=""),
    ) -> dict[str, Any]:
        payload = validate_specialist_session(x_nico_operator_session)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "specialist_session_invalid_or_expired",
                    "message": "The specialist session is invalid or expired.",
                },
            )
        return {
            "status": "authenticated",
            "artifact_schema": VERSION,
            "expires_at": payload["exp"],
            "scope": payload["scope"],
        }

    async def create_github_actions_proof_session(
        authorization: str = Header(default=""),
    ) -> Response:
        encoded = _bearer_token(authorization)
        try:
            claims = await run_in_threadpool(
                verify_github_actions_oidc_token,
                encoded,
            )
            session_token, expires_in = issue_specialist_session(
                {"authority": "github_actions_production_proof"},
                scope=PRODUCTION_PROOF_SCOPE,
                ttl_seconds=10_800,
                retained_claims=claims,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": str(exc).split(":", 1)[0],
                    "message": "GitHub Actions production-proof identity was not accepted.",
                },
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": str(exc),
                    "message": "Production-proof session signing is unavailable.",
                },
            ) from exc
        return JSONResponse(
            {
                "status": "authenticated",
                "artifact_schema": VERSION,
                "session_token": session_token,
                "expires_in": expires_in,
                "scope": PRODUCTION_PROOF_SCOPE,
                "repository": claims["repository"],
                "release_sha": claims["sha"],
                "workflow_ref": claims["workflow_ref"],
                "run_id": claims["run_id"],
                "run_attempt": claims["run_attempt"],
                "oidc_audience": proof_audience(),
            },
            headers={"Cache-Control": "no-store, private, max-age=0"},
        )

    app.add_api_route(SESSION_ROUTE, create_session, methods=["POST"], tags=["specialist-access"])
    app.add_api_route(SESSION_ROUTE, validate_session, methods=["GET"], tags=["specialist-access"])
    app.add_api_route(
        GITHUB_ACTIONS_SESSION_ROUTE,
        create_github_actions_proof_session,
        methods=["POST"],
        tags=["specialist-access"],
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=_specialist_access_middleware)
    status = {
        "artifact_schema": VERSION,
        "installed": True,
        "protected_prefix": _PROTECTED_PREFIX,
        "all_assessment_routes_protected": True,
        "session_route": SESSION_ROUTE,
        "github_actions_session_route": GITHUB_ACTIONS_SESSION_ROUTE,
        "production_proof_scope_is_read_and_continue_only": True,
        "session_signing_configured": _session_secret() is not None,
        "rate_limiting": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_specialist_access_v1 = status
    app.openapi_schema = None
    return dict(status)


__all__ = [
    "VERSION",
    "SESSION_ROUTE",
    "GITHUB_ACTIONS_SESSION_ROUTE",
    "SESSION_SIGNING_SECRET_ENV",
    "SPECIALIST_SCOPE",
    "PRODUCTION_PROOF_SCOPE",
    "install_specialist_access",
    "issue_specialist_session",
    "validate_specialist_session",
]
