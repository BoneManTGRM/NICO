"""Real JWT signatures; only the external JWKS fetch is substituted."""
from types import SimpleNamespace
import time

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from nico import assessment_worker_auth as auth

RELEASE = "c" * 40
JOB = "workerjob_" + "b" * 64


@pytest.fixture
def signed_worker(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", RELEASE)
    monkeypatch.setenv("NICO_ASSESSMENT_WORKER_REPOSITORY_ID", "123456")
    monkeypatch.setattr(auth, "_jwk_client", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))
    now = int(time.time())
    claims = {
        "iss": auth.ISSUER, "aud": auth.AUDIENCE + "/" + JOB,
        "sub": "repo:BoneManTGRM/NICO:ref:refs/heads/main",
        "iat": now, "nbf": now, "exp": now + 300, "jti": "synthetic-unique-id",
        "repository": "BoneManTGRM/NICO", "repository_id": "123456",
        "ref": "refs/heads/main", "sha": RELEASE, "workflow_sha": RELEASE,
        "workflow_ref": "BoneManTGRM/NICO/" + auth.WORKFLOW + "@refs/heads/main",
        "event_name": "workflow_dispatch", "run_id": "12345678", "run_attempt": "1",
        "runner_environment": "github-hosted",
    }
    def sign(changes=None, missing=None):
        values = {**claims, **(changes or {})}
        if missing:
            values.pop(missing)
        return jwt.encode(values, key, algorithm="RS256", headers={"kid": "synthetic-key"})
    return sign, key, claims


def test_valid_signature_yields_only_job_scoped_worker_authority(signed_worker):
    sign, _, _ = signed_worker
    authority = auth.verify_worker_token(sign(), JOB)
    assert authority.job_id == JOB and authority.release_revision == RELEASE
    assert authority.worker_id == "github:123456:12345678:1"
    assert len(authority.nonce_sha256) == 64
    assert not hasattr(authority, "operator_session")


@pytest.mark.parametrize("changes", [
    {"iss": "https://example.invalid"}, {"aud": "https://app.nicoaudit.com/nico-production-proof"},
    {"aud": auth.AUDIENCE + "/workerjob_" + "d" * 64},
    {"repository": "another/repository"}, {"repository_id": "654321"},
    {"ref": "refs/pull/1/merge"}, {"sha": "d" * 40}, {"workflow_sha": "d" * 40},
    {"workflow_ref": "BoneManTGRM/NICO/.github/workflows/spanish-comprehensive-production-proof.yml@refs/heads/main"},
    {"sub": "repo:BoneManTGRM/NICO:environment:production-smoke"},
    {"event_name": "pull_request"}, {"environment": "production-smoke"},
    {"runner_environment": "self-hosted"}, {"job_workflow_ref": "untrusted/reusable.yml"},
    {"run_id": "0"}, {"run_attempt": "two"}, {"jti": ""},
    {"exp": 1}, {"exp": int(time.time()) + 3600}, {"nbf": int(time.time()) + 1000},
    {"iat": True},
])
def test_wrong_scope_identity_or_lifetime_rejected(signed_worker, changes):
    sign, _, _ = signed_worker
    with pytest.raises(ValueError):
        auth.verify_worker_token(sign(changes), JOB)


@pytest.mark.parametrize("missing", ["repository_id", "workflow_sha", "jti", "exp", "aud", "run_attempt"])
def test_missing_mandatory_claim_rejected(signed_worker, missing):
    sign, _, _ = signed_worker
    with pytest.raises(ValueError):
        auth.verify_worker_token(sign(missing=missing), JOB)


def test_forged_signature_and_unsigned_token_rejected(signed_worker):
    _, _, claims = signed_worker
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for encoded in (jwt.encode(claims, other, algorithm="RS256"),
                    jwt.encode(claims, "", algorithm="none")):
        with pytest.raises(ValueError):
            auth.verify_worker_token(encoded, JOB)


def test_unknown_repository_identity_or_malformed_release_fails_closed(signed_worker, monkeypatch):
    sign, _, _ = signed_worker
    monkeypatch.delenv("NICO_ASSESSMENT_WORKER_REPOSITORY_ID")
    with pytest.raises(ValueError):
        auth.verify_worker_token(sign(), JOB)
    monkeypatch.setenv("NICO_ASSESSMENT_WORKER_REPOSITORY_ID", "123456")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "malformed")
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", RELEASE)
    with pytest.raises(ValueError):
        auth.verify_worker_token(sign(), JOB)
