"""Exercise the production readiness gate with offline native-identity receipts."""
import pytest

from tests.test_specialist_readiness_closure_v1 import _bootstrap_assertions


@pytest.mark.parametrize("fault", [
    "native", "platform_mapping", "configured_only", "wrong_sha", "wrong_id",
    "unavailable", "redirect", "oversize", "tampered", "missing_pin",
    "backend_conflict", "backend_mismatch", "authentication", "storage",
    "mapping_unavailable", "mapping_wrong_sha",
])
def test_readiness_requires_independent_frontend_proof(fault):
    _bootstrap_assertions("fault = " + repr(fault) + "\n" + r'''
import json, os, requests
from nico import report_execution_provenance_e6 as provenance
for key in ('NICO_RELEASE_COMMIT_SHA', 'RAILWAY_GIT_COMMIT_SHA', 'NICO_FRONTEND_BUILD_COMMIT_SHA', 'VERCEL_GIT_COMMIT_SHA', 'GITHUB_SHA'):
    os.environ.pop(key, None)
sha = 'a' * 40
os.environ.update(RAILWAY_GIT_COMMIT_SHA=sha, NICO_RELEASE_COMMIT_SHA=sha,
                  NICO_FRONTEND_BUILD_COMMIT_SHA=sha, NICO_FRONTEND_DEPLOYMENT_ID='dpl_readiness_fixture')
if fault == 'missing_pin': os.environ.pop('NICO_FRONTEND_DEPLOYMENT_ID')
if fault == 'backend_conflict': os.environ['NICO_RELEASE_COMMIT_SHA'] = 'c' * 40
if fault == 'backend_mismatch':
    os.environ.update(RAILWAY_GIT_COMMIT_SHA='c' * 40, NICO_RELEASE_COMMIT_SHA='c' * 40)
bootstrap._configured_credentials = lambda: {'admin':'fixture-admin', 'operator':'fixture-operator', 'legacy_operator':'', 'session_signing':'fixture-signing'}
bootstrap._positive_authentication_self_test = lambda _: {'operator_credential_self_test':True, 'session_round_trip_self_test':True, 'positive_authentication_verified_server_side':fault != 'authentication'}
bootstrap.SPECIALIST_ACCESS = {'installed':True, 'session_signing_configured':True, 'all_assessment_routes_protected':True, 'all_report_routes_protected':True, 'rate_limiting':True}
bootstrap.REVIEW_SESSION_BRIDGE = {'installed':True}
bootstrap.APPROVED_LIFECYCLE_CONSISTENCY = {'installed':True, 'cross_format_fail_closed':True}
bootstrap.app.state.nico_comprehensive_production_runtime = {'status':'ready', 'survives_container_replacement_verified':fault != 'storage', 'human_review_required':True, 'client_delivery_allowed':False}
endpoint = {'status':'ok', 'release_sha':sha, 'release_sha_source':'VERCEL_GIT_COMMIT_SHA', 'deployment_id':'dpl_readiness_fixture', 'deployment_id_source':'VERCEL_DEPLOYMENT_ID'}
if fault == 'configured_only': endpoint.update(release_sha_source='NICO_RELEASE_SHA', deployment_id_source='configured_label')
if fault == 'wrong_sha': endpoint['release_sha'] = 'b' * 40
if fault == 'wrong_id': endpoint['deployment_id'] = 'dpl_wrong'
if fault.startswith('mapping_') or fault == 'platform_mapping': endpoint.update(release_sha='unknown', release_sha_source='unavailable')
raw = json.dumps(endpoint).encode() if fault != 'oversize' else b'x' * 20000
calls = []
class Response:
    def __init__(self, data, status=200): self.data, self.status_code = data, status
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size): yield self.data
class Session:
    trust_env = True
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs):
        assert self.trust_env is False
        assert kwargs['allow_redirects'] is False and kwargs['timeout'] == (3, 5)
        assert kwargs['headers'] == {'Accept':'application/json'}
        assert 'auth' not in kwargs and 'cookies' not in kwargs
        calls.append(url)
        if url == provenance.FRONTEND_URL:
            return Response(raw, 503 if fault == 'unavailable' else 302 if fault == 'redirect' else 200)
        assert url == 'https://api.vercel.com/v13/deployments/dpl_readiness_fixture?withGitRepoInfo=true'
        return Response(json.dumps({'id':'dpl_readiness_fixture', 'readyState':'READY', 'gitSource':{'sha':'b' * 40 if fault == 'mapping_wrong_sha' else sha}}).encode(),
                        403 if fault == 'mapping_unavailable' else 200)
requests.Session = Session
original_capture = provenance.capture_frontend_release
if fault == 'tampered':
    def corrupt(*args):
        observation = original_capture(*args)
        observation['observation_sha256'] = '0' * 64
        return observation
    provenance.capture_frontend_release = corrupt
# Labels remain unverified globally; readiness alone acquires independent proof.
assert bootstrap.comprehensive_release_provenance()['frontend_identity_established'] is False
result = bootstrap.specialist_readiness()
expected_ready = fault in {'native', 'platform_mapping'}
assert (result['status'] == 'ready') is expected_ready, result
expected_release = fault in {'native', 'platform_mapping', 'authentication', 'storage'}
assert result['release_identity_complete'] is expected_release, result
release = result['release_provenance']
assert release['frontend_build_commit'] == sha
assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
assert result['secrets_exposed'] is False
assert 'fixture-operator' not in str(result) and 'fixture-signing' not in str(result)
if expected_ready:
    assert release['frontend_identity_established'] is True
    assert release['frontend_deployment_identity_verified'] is True
    assert release['frontend_observed_source_revision'] == sha
    assert release['frontend_configured_identity_source'] == 'configured_release_label'
    assert release['frontend_identity_source'] != 'configured_release_label'
    assert release['frontend_runtime_observation']['native_provider_record_verified_by_this_code'] is (fault == 'platform_mapping')
    # Each diagnostic takes a fresh observation; old proof is not reused.
    first_count = len(calls)
    second = bootstrap.specialist_readiness()
    assert second['status'] == 'ready' and len(calls) == first_count * 2
elif fault not in {'backend_conflict', 'backend_mismatch', 'authentication', 'storage'}:
    assert release['frontend_identity_established'] is False
if fault == 'missing_pin': assert calls == []
assert bootstrap.comprehensive_release_provenance()['frontend_identity_established'] is False
''')
