"""The runner diagnostic must preserve authentication and never print credentials."""
import json
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from test_assessment_worker_auth import signed_worker, JOB
from scripts import worker_identity_preflight as preflight


def test_real_signed_identity_passes_without_returning_claims(signed_worker):
    sign, _, _ = signed_worker
    token = sign()
    result = preflight.inspect_token(token, JOB)
    assert result['status'] == 'verified'
    assert all(result['checks'].values())
    assert token not in json.dumps(result)
    assert 'synthetic-unique-id' not in json.dumps(result)


@pytest.mark.parametrize('changes,failed_check', [
    ({'sub': 'private-sensitive-subject'}, 'sub'),
    ({'workflow_sha': 'e' * 40}, 'workflow_sha'),
    ({'job_workflow_ref': 'private-sensitive-reusable'}, 'job_workflow_identity'),
    ({'environment': 'private-sensitive-environment'}, 'no_environment'),
])
def test_scope_rejection_explains_only_boolean_checks(signed_worker, changes, failed_check):
    sign, _, _ = signed_worker
    token = sign(changes)
    result = preflight.inspect_token(token, JOB)
    assert result['status'] == 'failed'
    assert result['code'] == 'worker_authority_mismatch'
    assert result['checks'][failed_check] is False
    assert token not in json.dumps(result)
    assert 'private-sensitive' not in json.dumps(result)


def test_invalid_signature_is_not_used_for_claim_diagnostics(signed_worker):
    sign, _, _ = signed_worker
    token = sign({'exp': 1})
    result = preflight.inspect_token(token, JOB)
    assert result == {'status': 'failed', 'code': 'worker_jwt_invalid',
                      'category': 'ExpiredSignatureError'}


def test_forged_token_is_rejected_without_reporting_unverified_checks(signed_worker):
    _, _, claims = signed_worker
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims, key, algorithm='RS256')
    assert preflight.inspect_token(token, JOB) == {
        'status': 'failed', 'code': 'worker_jwt_invalid',
        'category': 'InvalidSignatureError'}


def test_bad_token_and_nonce_are_never_echoed(signed_worker):
    result = preflight.inspect_token('private-sensitive-token', JOB)
    assert result['status'] == 'failed'
    assert 'checks' not in result
    assert 'private-sensitive' not in json.dumps(result)


def test_overlong_lifetime_still_fails(signed_worker):
    sign, _, claims = signed_worker
    result = preflight.inspect_token(sign({'exp': claims['iat'] + 3600}), JOB)
    assert result['status'] == 'failed'
    assert result['code'] == 'worker_lifetime_invalid'
    assert result['checks']['lifetime'] is False


def test_main_reports_only_a_fixed_code_when_token_acquisition_fails(monkeypatch, capsys):
    def unavailable(*args):
        raise RuntimeError('private-sensitive-token')
    monkeypatch.setattr(preflight, 'ActionsWorkerToken', unavailable)
    monkeypatch.setenv('NICO_WORKER_JOB_ID', JOB)
    assert preflight.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        'status': 'failed', 'code': 'worker_identity_preflight_unavailable'}


def test_exact_self_workflow_reports_verified_boolean_identity(signed_worker):
    sign, _, claims = signed_worker
    result = preflight.inspect_token(sign({
        'job_workflow_ref': claims['workflow_ref'],
        'job_workflow_sha': claims['workflow_sha'],
    }), JOB)
    assert result['status'] == 'verified'
    assert all(result['checks'].values())
    assert claims['workflow_ref'] not in json.dumps(result)
