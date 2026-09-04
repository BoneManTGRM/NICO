from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from nico.github_actions_proof_session_v1 import (
    AUDIENCE,
    ISSUER,
    validate_github_actions_oidc,
)


RELEASE_SHA = "a" * 40


def _token(*, workflow: str = "spanish-comprehensive-production-proof.yml", sha: str = RELEASE_SHA):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "repo:BoneManTGRM/NICO:environment:production-smoke",
        "exp": now + 600,
        "iat": now,
        "nbf": now - 5,
        "jti": "test-jti-1234567890",
        "repository": "BoneManTGRM/NICO",
        "repository_id": "1282576027",
        "repository_visibility": "public",
        "ref": "refs/heads/main",
        "ref_protected": "true",
        "sha": sha,
        "workflow_ref": f"BoneManTGRM/NICO/.github/workflows/{workflow}@refs/heads/main",
        "workflow_sha": sha,
        "event_name": "push",
        "environment": "production-smoke",
        "runner_environment": "github-hosted",
        "run_id": "123456789",
        "run_attempt": "1",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    return token, private_key.public_key()


def test_exact_release_and_allowlisted_workflow_are_accepted(monkeypatch):
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", RELEASE_SHA)
    token, public_key = _token()

    authority = validate_github_actions_oidc(token, signing_key=public_key)

    assert authority["authority"] == "github_actions_production_proof"
    assert authority["scope"] == "nico_specialist_operation"
    assert authority["release_sha"] == RELEASE_SHA
    assert authority["workflow_file"] == ".github/workflows/spanish-comprehensive-production-proof.yml"


def test_stale_release_is_rejected(monkeypatch):
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", RELEASE_SHA)
    token, public_key = _token(sha="b" * 40)

    with pytest.raises(ValueError, match="release_sha"):
        validate_github_actions_oidc(token, signing_key=public_key)


def test_unapproved_workflow_is_rejected(monkeypatch):
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", RELEASE_SHA)
    token, public_key = _token(workflow="untrusted.yml")

    with pytest.raises(ValueError, match="workflow_ref"):
        validate_github_actions_oidc(token, signing_key=public_key)
