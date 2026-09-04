from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Mapping

import jwt

VERSION = "nico.github_actions_proof_auth.v2"
ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks"
DEFAULT_AUDIENCE = "https://app.nicoaudit.com/nico-production-proof"
DEFAULT_REPOSITORY = "BoneManTGRM/NICO"
DEFAULT_REF = "refs/heads/main"
DEFAULT_WORKFLOW_PATH = ".github/workflows/spanish-comprehensive-production-proof.yml"
FINALIZER_WORKFLOW_PATH = ".github/workflows/specialist-production-proof-finalizer.yml"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
_WORKFLOW_EVENT_POLICY = {
    DEFAULT_WORKFLOW_PATH: {"push", "workflow_dispatch"},
    FINALIZER_WORKFLOW_PATH: {"workflow_run"},
}


def _configured(name: str, default: str) -> str:
    return str(os.getenv(name, default) or "").strip()


def proof_audience() -> str:
    return _configured("NICO_GITHUB_ACTIONS_OIDC_AUDIENCE", DEFAULT_AUDIENCE)


def expected_repository() -> str:
    return _configured("NICO_GITHUB_ACTIONS_PROOF_REPOSITORY", DEFAULT_REPOSITORY)


def expected_ref() -> str:
    return _configured("NICO_GITHUB_ACTIONS_PROOF_REF", DEFAULT_REF)


def expected_workflow_path() -> str:
    return _configured(
        "NICO_GITHUB_ACTIONS_PROOF_WORKFLOW",
        DEFAULT_WORKFLOW_PATH,
    ).lstrip("/")


def expected_release_sha() -> str:
    value = _configured("NICO_RELEASE_COMMIT_SHA", "").lower()
    if not _GIT_SHA.fullmatch(value):
        raise ValueError("github_actions_proof_release_sha_unavailable")
    return value


def _required_claim(claims: Mapping[str, Any], name: str) -> str:
    value = str(claims.get(name) or "").strip()
    if not value:
        raise ValueError(f"github_actions_oidc_{name}_required")
    return value


def _allowed_workflow_paths(explicit_workflow_path: str | None) -> dict[str, set[str]]:
    if explicit_workflow_path is not None:
        normalized = str(explicit_workflow_path).strip().lstrip("/")
        return {normalized: set(_WORKFLOW_EVENT_POLICY.get(normalized, {"push", "workflow_dispatch"}))}
    configured = expected_workflow_path()
    policy = {configured: set(_WORKFLOW_EVENT_POLICY.get(configured, {"push", "workflow_dispatch"}))}
    policy[FINALIZER_WORKFLOW_PATH] = set(_WORKFLOW_EVENT_POLICY[FINALIZER_WORKFLOW_PATH])
    return policy


def validate_github_actions_claims(
    claims: Mapping[str, Any],
    *,
    release_sha: str | None = None,
    repository: str | None = None,
    ref: str | None = None,
    workflow_path: str | None = None,
) -> dict[str, str]:
    """Validate an exact trusted production-proof workflow identity.

    Only the canonical Spanish producer and the bounded post-producer specialist
    finalizer are accepted. Each workflow has an explicit event policy, while exact
    repository, protected main ref, deployed release SHA, subject, run identity,
    signature, issuer, audience, and lifetime remain mandatory.
    """

    expected_repo = str(repository or expected_repository()).strip()
    expected_branch_ref = str(ref or expected_ref()).strip()
    expected_sha = str(release_sha or expected_release_sha()).strip().lower()
    if not _GIT_SHA.fullmatch(expected_sha):
        raise ValueError("github_actions_proof_release_sha_invalid")

    observed_repo = _required_claim(claims, "repository")
    observed_ref = _required_claim(claims, "ref")
    observed_sha = _required_claim(claims, "sha").lower()
    observed_event = _required_claim(claims, "event_name")
    observed_subject = _required_claim(claims, "sub")
    observed_workflow_ref = _required_claim(claims, "workflow_ref")
    observed_run_id = _required_claim(claims, "run_id")
    observed_run_attempt = _required_claim(claims, "run_attempt")

    workflow_policy = _allowed_workflow_paths(workflow_path)
    observed_workflow_path = ""
    workflow_suffix = f"@{expected_branch_ref}"
    repo_prefix = f"{expected_repo}/"
    if observed_workflow_ref.startswith(repo_prefix) and observed_workflow_ref.endswith(workflow_suffix):
        observed_workflow_path = observed_workflow_ref[len(repo_prefix) : -len(workflow_suffix)]
    allowed_events = workflow_policy.get(observed_workflow_path, set())
    expected_subject = f"repo:{expected_repo}:ref:{expected_branch_ref}"
    checks = {
        "repository": observed_repo == expected_repo,
        "ref": observed_ref == expected_branch_ref,
        "sha": observed_sha == expected_sha,
        "event_name": observed_event in allowed_events,
        "sub": observed_subject == expected_subject,
        "workflow_ref": observed_workflow_path in workflow_policy,
        "run_id": bool(_RUN_ID.fullmatch(observed_run_id)),
        "run_attempt": bool(_RUN_ID.fullmatch(observed_run_attempt)),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    if failures:
        raise ValueError(
            "github_actions_oidc_claim_mismatch:" + ",".join(failures)
        )

    return {
        "repository": observed_repo,
        "ref": observed_ref,
        "sha": observed_sha,
        "event_name": observed_event,
        "workflow_ref": observed_workflow_ref,
        "run_id": observed_run_id,
        "run_attempt": observed_run_attempt,
        "actor": str(claims.get("actor") or "github-actions").strip()[:160],
    }


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        JWKS_URL,
        cache_keys=True,
        lifespan=3600,
        timeout=15,
    )


def verify_github_actions_oidc_token(token: str) -> dict[str, str]:
    encoded = str(token or "").strip()
    if not encoded or len(encoded) > 16_384:
        raise ValueError("github_actions_oidc_token_invalid")
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(encoded)
        claims = jwt.decode(
            encoded,
            signing_key.key,
            algorithms=["RS256"],
            audience=proof_audience(),
            issuer=ISSUER,
            leeway=30,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "iat",
                    "nbf",
                    "exp",
                    "repository",
                    "ref",
                    "sha",
                    "event_name",
                    "workflow_ref",
                    "run_id",
                    "run_attempt",
                ]
            },
        )
    except jwt.PyJWTError as exc:
        raise ValueError("github_actions_oidc_verification_failed") from exc
    if not isinstance(claims, Mapping):
        raise ValueError("github_actions_oidc_claims_invalid")
    return validate_github_actions_claims(claims)


__all__ = [
    "VERSION",
    "DEFAULT_AUDIENCE",
    "DEFAULT_WORKFLOW_PATH",
    "FINALIZER_WORKFLOW_PATH",
    "proof_audience",
    "validate_github_actions_claims",
    "verify_github_actions_oidc_token",
]
