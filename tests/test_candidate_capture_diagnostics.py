from copy import deepcopy
import json
import pytest
from nico.comprehensive_api_controller import _project_record

SCOPE = dict(run_id='run', repository='example/repo', commit_sha='a'*40, customer_id='c', project_id='p')


def record():
    return {'identity': dict(SCOPE), 'stage_results': {'repository_and_delivery_evidence': {
        'repository_evidence': {'candidate_source_observations': {
            'artifact_schema': 'nico.persisted-candidate-investigation.v1', 'scope': dict(SCOPE),
            'observations': {'private/file.py': {'status': 'parsed', 'source': 'secret literal'},
                             'another.py': {'status': 'source_parse_unavailable'}},
            'unavailable_reasons': {'source_time_budget': 3, 'private-error': 'secret literal'}}}}}}


def diagnostic(value):
    return _project_record(value)['candidate_source_capture_diagnostics']


def test_count_only_projection_is_read_only_and_does_not_disclose_private_fields():
    value = record(); before = deepcopy(value)
    result = diagnostic(value)
    assert result == {'artifact_schema': 'nico.candidate-source-capture-diagnostics.v1',
        'capture_present': True, 'status': 'available', 'scope_match': True,
        'observation_count': 2, 'observation_status_counts': {'parsed': 1, 'source_parse_unavailable': 1},
        'budget_reason_counts': {'source_time_budget': 3}}
    assert value == before
    assert all(text not in json.dumps(result) for text in ('private', 'secret', 'another.py', 'example/repo'))


def test_missing_capture_is_not_zero():
    result = diagnostic({'identity': SCOPE})
    assert result['capture_present'] is False
    assert result['status'] == 'missing'
    assert result['scope_match'] is None
    assert result['observation_count'] is None


@pytest.mark.parametrize('field', list(SCOPE))
def test_mismatched_scope_exposes_no_counts(field):
    value = record()
    value['stage_results']['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations']['scope'][field] = 'different'
    result = diagnostic(value)
    assert result['scope_match'] is False
    assert result['status'] == 'scope_mismatch'
    assert result['observation_count'] is None
    assert result['budget_reason_counts'] == {}


@pytest.mark.parametrize('field,bad', [('observations', []), ('observations', {'x': 'secret'}),
    ('observations', {'x': {'status': 'secret error'}}), ('unavailable_reasons', []),
    ('unavailable_reasons', {'source_time_budget': True}), ('unavailable_reasons', {'source_size_budget': -1}),
    ('scope', []), ('artifact_schema', 'wrong')])
def test_malformed_capture_is_unavailable(field, bad):
    value = record()
    value['stage_results']['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations'][field] = bad
    result = diagnostic(value)
    assert result['status'] in {'malformed', 'scope_mismatch'}
    assert result['observation_count'] is None
    assert 'secret' not in json.dumps(result)


def test_explicit_empty_valid_capture_is_zero():
    value = record()
    capture = value['stage_results']['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations']
    capture['observations'] = {}; capture['unavailable_reasons'] = {}
    assert diagnostic(value)['observation_count'] == 0


def test_existing_authenticated_status_middleware_protects_projection(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session, PRODUCTION_PROOF_SCOPE
    from tests.test_github_actions_production_proof_auth_v1 import _environment, CLAIMS
    _environment(monkeypatch)
    app = FastAPI()
    @app.get('/assessment/comprehensive-run/{run_id}')
    def status(run_id: str):
        return _project_record(record())
    install_specialist_access(app)
    client = TestClient(app)
    denied = client.get('/assessment/comprehensive-run/run')
    assert denied.status_code in (401, 403)
    assert 'candidate_source_capture_diagnostics' not in denied.text
    token, _ = issue_specialist_session({'authority': 'github_actions_production_proof'},
        scope=PRODUCTION_PROOF_SCOPE, retained_claims={**CLAIMS, 'proof_role': 'recovery'})
    accepted = client.get('/assessment/comprehensive-run/run', headers={'X-NICO-Operator-Session': token})
    assert accepted.status_code == 200
    assert accepted.json()['candidate_source_capture_diagnostics']['observation_count'] == 2
    assert 'secret literal' not in accepted.text
