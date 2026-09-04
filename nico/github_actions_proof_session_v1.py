from __future__ import annotations

import hmac
import os
import re
import time
from collections import deque
from threading import Lock
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from nico.specialist_access_v1 import issue_specialist_session

VERSION = "nico.github_actions_proof_session.v1"
ROUTE = "/assessment/github-actions-proof-session"
AUDIENCE = "nico-production-proof"
ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
REPOSITORY = "BoneManTGRM/NICO"
OWNER_ID = "235159333"
REPOSITORY_ID = "1282576027"
ENVIRONMENT = "production-smoke"
ALLOWED_EVENT_NAMES = {"push", "workflow_run", "workflow_dispatch"}
ALLOWED_WORKFLOW_FILES = {
    ".github/workflows/spanish-comprehensive-production-proof.yml",
    ".github/workflows/mobile-restart-production-proof.yml",
    ".github/workflows/ios-webkit-paint-proof.yml",
    ".github/workflows/two-service-production-acceptance.yml",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE = re.compile(r"^[0-9]+$")
_JWKS_CLIENT: jwt.PyJWKClient | None = None
_JWKS_LOCK = Lock()
_REPLAY_LOCK = Lock()
_USED_JTIS: dict[str, int] = {}
_ATTEMPT_LOCK = Lock()
_ATTEMPTS: dict[str, deque[float]] = {}


class GitHubActionsProofSessionRequest(BaseModel):
    oidc_token: str = Field(min_length=100, max_length=20_000)


def _expected_release_sha() -> str:
    for name in ("NICO_RELEASE_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA", "GITHUB_SHA"):
        value = os.getenv(name, "").strip().lower()
        if _SHA_RE.fullmatch(value):
            return value
    return ""


def _jwk_client() -> jwt.PyJWKClient:
    global _JWKS_CLIENT
    if _JWKS_CLIENT is None:
        with _JWKS_LOCK:
            if _JWKS_CLIENT is None:
                _JWKS_CLIENT = jwt.PyJWKClient(JWKS_URL)
    return _JWKS_CLIENT


def _workflow_file(workflow_ref: str) -> str:
    prefix = f"{REPOSITORY}/"
    suffix = "@refs/heads/main"
    if not workflow_ref.startswith(prefix) or not workflow_ref.endswith(suffix):
        return ""
    return workflow_ref[len(prefix) : -len(suffix)]


def _subject_is_expected(subject: str) -> bool:
    suffix = f":environment:{ENVIRONMENT}"
    legacy = f"repo:{REPOSITORY}{suffix}"
    immutable = (
        f"repo:BoneManTGRM@{OWNER_ID}/NICO@{REPOSITORY_ID}{suffix}"
    )
    return hmac.compare_digest(subject, legacy) or hmac.compare_digest(subject, immutable)


def _required_text(claims: dict[str, Any], name: str) -> str:
    value = str(claims.get(name) or "").strip()
    if not value:
        raise ValueError(f"github_actions_oidc_{name}_missing")
    return value


def validate_github_actions_oidc(
    token: str,
    *,
    signing_key: Any | None = None,
) -> dict[str, Any]:
    value = str(token or "").strip()
    if len(value) < 100 or len(value) > 20_000:
        raise ValueError("github_actions_oidc_token_size_invalid")
    try:
        key = signing_key
        if key is None:
            key = _jwk_client().get_signing_key_from_jwt(value).key
        claims = jwt.decode(
            value,
            key=key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=30,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "exp",
                    "iat",
                    "nbf",
                    "jti",
                    "repository",
                    "repository_id",
                    "repository_visibility",
                    "ref",
                    "sha",
                    "workflow_ref",
                    "workflow_sha",
                    "event_name",
                    "environment",
                    "runner_environment",
                    "run_id",
                    "run_attempt",
                ]
            },
        )
    except Exception as exc:
        raise ValueError("github_actions_oidc_signature_or_standard_claim_invalid") from exc
    if not isinstance(claims, dict):
        raise ValueError("github_actions_oidc_claims_invalid")

    repository = _required_text(claims, "repository")
    repository_id = _required_text(claims, "repository_id")
    visibility = _required_text(claims, "repository_visibility")
    ref = _required_text(claims, "ref")
    release_sha = _required_text(claims, "sha").lower()
    workflow_ref = _required_text(claims, "workflow_ref")
    workflow_sha = _required_text(claims, "workflow_sha").lower()
    event_name = _required_text(claims, "event_name")
    environment = _required_text(claims, "environment")
    runner_environment = _required_text(claims, "runner_environment")
    subject = _required_text(claims, "sub")
    run_id = _required_text(claims, "run_id")
    run_attempt = _required_text(claims, "run_attempt")
    jti = _required_text(claims, "jti")
    expected_release_sha = _expected_release_sha()
    workflow_file = _workflow_file(workflow_ref)

    checks = {
        "repository": hmac.compare_digest(repository, REPOSITORY),
        "repository_id": hmac.compare_digest(repository_id, REPOSITORY_ID),
        "repository_visibility": hmac.compare_digest(visibility, "public"),
        "ref": hmac.compare_digest(ref, "refs/heads/main"),
        "release_sha_configured": bool(expected_release_sha),
        "release_sha": bool(expected_release_sha)
        and hmac.compare_digest(release_sha, expected_release_sha),
        "workflow_ref": workflow_file in ALLOWED_WORKFLOW_FILES,
        "workflow_sha": bool(expected_release_sha)
        and hmac.compare_digest(workflow_sha, expected_release_sha),
        "event_name": event_name in ALLOWED_EVENT_NAMES,
        "environment": hmac.compare_digest(environment, ENVIRONMENT),
        "runner_environment": hmac.compare_digest(runner_environment, "github-hosted"),
        "subject": _subject_is_expected(subject),
        "run_id": bool(_RUN_ID_RE.fullmatch(run_id)),
        "run_attempt": bool(_RUN_ID_RE.fullmatch(run_attempt)),
        "jti": 8 <= len(jti) <= 512,
        "ref_protected": str(claims.get("ref_protected") or "true").lower() == "true",
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError("github_actions_oidc_claim_boundary_failed:" + ",".join(failed))

    return {
        "authority": "github_actions_production_proof",
        "scope": "nico_specialist_operation",
        "repository": repository,
        "repository_id": repository_id,
        "release_sha": release_sha,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "workflow_file": workflow_file,
        "event_name": event_name,
        "environment": environment,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "jti": jti,
        "exp": int(claims["exp"]),
    }


def _consume_jti(jti: str, expires_at: int) -> bool:
    now = int(time.time())
    with _REPLAY_LOCK:
        for key, expiration in list(_USED_JTIS.items()):
            if expiration <= now:
                _USED_JTIS.pop(key, None)
        if jti in _USED_JTIS:
            return False
        _USED_JTIS[jti] = max(now + 60, int(expires_at))
        return True


def _rate_limit_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _exchange_allowed(key: str) -> bool:
    now = time.monotonic()
    cutoff = now - 60
    with _ATTEMPT_LOCK:
        events = _ATTEMPTS.setdefault(key, deque())
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= 20:
            return False
        events.append(now)
        if len(_ATTEMPTS) > 2048:
            stale = [name for name, values in _ATTEMPTS.items() if not values or values[-1] <= cutoff]
            for name in stale[:512]:
                _ATTEMPTS.pop(name, None)
        return True


def install_github_actions_proof_session(app: FastAPI) -> dict[str, Any]:
    if getattr(app.state, "nico_github_actions_proof_session_v1", None):
        return dict(app.state.nico_github_actions_proof_session_v1)

    async def exchange(
        payload: GitHubActionsProofSessionRequest,
        request: Request,
    ) -> dict[str, Any]:
        if not _exchange_allowed(_rate_limit_key(request)):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "github_actions_proof_exchange_rate_limited",
                    "message": "The bounded production-proof authentication limit was reached.",
                },
                headers={"Retry-After": "60"},
            )
        try:
            authority = validate_github_actions_oidc(payload.oidc_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "github_actions_proof_identity_rejected",
                    "message": "The GitHub Actions production-proof identity was not accepted.",
                },
            ) from exc
        if not _consume_jti(str(authority["jti"]), int(authority["exp"])):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "github_actions_proof_identity_replayed",
                    "message": "The GitHub Actions identity token was already exchanged.",
                },
            )
        try:
            session_token, expires_in = issue_specialist_session(authority)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "specialist_session_signing_unavailable",
                    "message": "The bounded production-proof session could not be issued.",
                },
            ) from exc
        return {
            "status": "authenticated",
            "artifact_schema": VERSION,
            "session_token": session_token,
            "expires_in": expires_in,
            "authority": "github_actions_production_proof",
            "scope": "nico_specialist_operation",
            "release_sha": authority["release_sha"],
            "workflow_file": authority["workflow_file"],
            "run_id": authority["run_id"],
            "run_attempt": authority["run_attempt"],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    app.add_api_route(ROUTE, exchange, methods=["POST"], tags=["specialist-access"])
    app.openapi_schema = None
    status = {
        "artifact_schema": VERSION,
        "installed": True,
        "route": ROUTE,
        "audience": AUDIENCE,
        "repository_id_bound": True,
        "immutable_owner_id_bound": True,
        "exact_release_bound": True,
        "workflow_allowlist_bound": True,
        "workflow_sha_bound": True,
        "environment_bound": True,
        "replay_blocked": True,
        "client_delivery_allowed": False,
    }
    app.state.nico_github_actions_proof_session_v1 = status
    return dict(status)


__all__ = [
    "AUDIENCE",
    "ISSUER",
    "ROUTE",
    "VERSION",
    "GitHubActionsProofSessionRequest",
    "install_github_actions_proof_session",
    "validate_github_actions_oidc",
]
