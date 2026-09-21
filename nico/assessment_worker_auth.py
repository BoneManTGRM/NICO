"""Dedicated GitHub OIDC authority for one immutable assessment worker job.

No operator session is minted and no existing production-proof trust is reused.
The endpoint has no job creation, enumeration, command or credential API.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import os
import re
import time

import jwt

from nico.github_actions_proof_auth_v1 import expected_release_sha

ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "https://app.nicoaudit.com/assessment-worker"
WORKFLOW = ".github/workflows/assessment-worker.yml"
JOB_ID = re.compile(r"workerjob_[0-9a-f]{64}")


@dataclass(frozen=True)
class WorkerAuthority:
    job_id: str
    release_revision: str
    worker_id: str
    nonce_sha256: str


@lru_cache(maxsize=1)
def _jwk_client():
    return jwt.PyJWKClient(ISSUER + "/.well-known/jwks", cache_keys=True,
                           lifespan=3600, timeout=10)


def verify_worker_token(token: str, job_id: str) -> WorkerAuthority:
    if not JOB_ID.fullmatch(job_id) or not token or len(token) > 16384:
        raise ValueError("worker_authentication_invalid")
    release = expected_release_sha()
    repository = os.getenv("NICO_ASSESSMENT_WORKER_REPOSITORY", "BoneManTGRM/NICO")
    repository_id = os.getenv("NICO_ASSESSMENT_WORKER_REPOSITORY_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", repository_id):
        raise ValueError("worker_repository_identity_unconfigured")
    try:
        claims = jwt.decode(
            token, _jwk_client().get_signing_key_from_jwt(token).key,
            algorithms=["RS256"], issuer=ISSUER, audience=f"{AUDIENCE}/{job_id}",
            options={"require": ["iss", "aud", "sub", "exp", "iat", "nbf", "jti",
                "repository", "repository_id", "ref", "sha", "workflow_ref",
                "workflow_sha", "event_name", "run_id", "run_attempt", "runner_environment"]},
        )
    except (jwt.PyJWTError, OSError) as exc:
        raise ValueError("worker_authentication_invalid") from exc
    expected = {
        "repository": repository, "repository_id": repository_id,
        "ref": "refs/heads/main", "sha": release, "workflow_sha": release,
        "workflow_ref": f"{repository}/{WORKFLOW}@refs/heads/main",
        "sub": f"repo:{repository}:ref:refs/heads/main",
        "event_name": "workflow_dispatch", "runner_environment": "github-hosted",
        "aud": f"{AUDIENCE}/{job_id}",
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise ValueError("worker_authority_mismatch")
    # This version trusts only the dedicated, non-reusable protected-main workflow.
    if claims.get("environment") or claims.get("job_workflow_ref"):
        raise ValueError("worker_authority_mismatch")
    if any(type(claims.get(key)) is not int for key in ("iat", "nbf", "exp")):
        raise ValueError("worker_lifetime_invalid")
    if not 0 < claims["exp"] - claims["iat"] <= 600 or claims["exp"] <= time.time():
        raise ValueError("worker_lifetime_invalid")
    if any(not isinstance(claims.get(key), str) or not re.fullmatch(r"[1-9][0-9]{0,19}", claims[key])
           for key in ("run_id", "run_attempt")):
        raise ValueError("worker_run_identity_invalid")
    nonce = claims.get("jti")
    if not isinstance(nonce, str) or not 1 <= len(nonce) <= 256:
        raise ValueError("worker_nonce_invalid")
    return WorkerAuthority(
        job_id, release, f"github:{repository_id}:{claims['run_id']}:{claims['run_attempt']}",
        hashlib.sha256(nonce.encode()).hexdigest(),
    )
