"""Diagnose the existing worker verifier without contacting the backend.

Only fixed check names, booleans and error categories may leave this process.
The raw token, claim values and exception messages are never output. This is
not an alternate authenticator and does not create or claim a worker job.
"""
from __future__ import annotations

import json
import os
import re
import time

import jwt

from nico import assessment_worker_auth as auth
from nico.assessment_worker_launch import ActionsWorkerToken

_ERRORS = frozenset({
    'worker_authentication_invalid', 'worker_repository_identity_unconfigured',
    'worker_authority_mismatch', 'worker_lifetime_invalid',
    'worker_run_identity_invalid', 'worker_nonce_invalid',
})
_JWT_ERRORS = frozenset({
    'DecodeError', 'ExpiredSignatureError', 'ImmatureSignatureError',
    'InvalidAudienceError', 'InvalidIssuerError', 'InvalidIssuedAtError',
    'InvalidSignatureError', 'MissingRequiredClaimError', 'InvalidAlgorithmError',
    'InvalidSubjectError', 'InvalidJTIError', 'PyJWKClientConnectionError',
    'PyJWKClientError',
})


def inspect_token(token, job_id):
    if not auth.JOB_ID.fullmatch(job_id) or not isinstance(token, str) or len(token) > 16384:
        return {'status': 'failed', 'code': 'worker_identity_input_invalid'}
    try:
        # Verify provenance before even reporting diagnostic comparisons. None
        # of these comparisons grant authority; the unmodified verifier below
        # remains the acceptance gate.
        claims = jwt.decode(token, auth._jwk_client().get_signing_key_from_jwt(token).key,
            algorithms=['RS256'], issuer=auth.ISSUER, audience=auth.AUDIENCE + '/' + job_id,
            options={'require': ['iss', 'aud', 'sub', 'exp', 'iat', 'nbf', 'jti']})
    except (jwt.PyJWTError, OSError) as exc:
        category = type(exc).__name__
        return {'status': 'failed', 'code': 'worker_jwt_invalid',
                'category': category if category in _JWT_ERRORS else 'verification_error'}
    release = auth.expected_release_sha()
    repository = os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY', 'BoneManTGRM/NICO')
    expected = {
        'repository': repository,
        'repository_id': os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY_ID', ''),
        'ref': 'refs/heads/main', 'sha': release, 'workflow_sha': release,
        'workflow_ref': repository + '/' + auth.WORKFLOW + '@refs/heads/main',
        'sub': 'repo:' + repository + ':ref:refs/heads/main',
        'event_name': 'workflow_dispatch', 'runner_environment': 'github-hosted',
        'aud': auth.AUDIENCE + '/' + job_id,
    }
    checks = {key: claims.get(key) == value for key, value in expected.items()}
    numeric_times = all(type(claims.get(key)) is int for key in ('iat', 'nbf', 'exp'))
    checks.update(
        no_environment=not bool(claims.get('environment')),
        job_workflow_identity=(
            ('job_workflow_ref' not in claims and 'job_workflow_sha' not in claims)
            or (claims.get('job_workflow_ref') == expected['workflow_ref']
                and claims.get('job_workflow_sha') == release)),
        job_workflow_ref_matches=claims.get('job_workflow_ref', expected['workflow_ref']) == expected['workflow_ref'],
        job_workflow_sha_matches=claims.get('job_workflow_sha', release) == release,
        numeric_times=numeric_times,
        lifetime=bool(numeric_times and 0 < claims['exp'] - claims['iat'] <= 600
                      and claims['exp'] > time.time()),
        run_identity=all(isinstance(claims.get(key), str)
            and re.fullmatch(r'[1-9][0-9]{0,19}', claims[key]) is not None
            for key in ('run_id', 'run_attempt')),
        nonce=isinstance(claims.get('jti'), str) and 1 <= len(claims['jti']) <= 256,
    )
    try:
        auth.verify_worker_token(token, job_id)
    except ValueError as exc:
        code = str(exc)
        return {'status': 'failed', 'code': code if code in _ERRORS else 'worker_identity_invalid',
                'checks': checks}
    return {'status': 'verified', 'checks': checks}


def main():
    try:
        job_id = os.environ.get('NICO_WORKER_JOB_ID', '')
        result = inspect_token(ActionsWorkerToken(job_id)(), job_id)
    except Exception:
        result = {'status': 'failed', 'code': 'worker_identity_preflight_unavailable'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
