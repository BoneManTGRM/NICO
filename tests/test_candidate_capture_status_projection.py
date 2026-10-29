from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session, PRODUCTION_PROOF_SCOPE
from tests.test_github_actions_production_proof_auth_v1 import _environment, CLAIMS
from tests.test_candidate_capture_diagnostics import record

URL = '/assessment/comprehensive-run/run?projection=candidate-source-capture-v1'


class ReadOnlyService:
    def __init__(self, value):
        self.value, self.reads = value, 0
    def load_capture_diagnostics_record(self, run_id):
        assert run_id == 'run'
        self.reads += 1
        return self.value
    def __getattr__(self, name):
        raise AssertionError('Unexpected service operation: ' + name)


def client_for(monkeypatch, value):
    _environment(monkeypatch)
    service = ReadOnlyService(value)
    # Registration probes this optional binder; no persisted projection is used.
    service.bind_browser_projection_builder = None
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=ComprehensiveApiController(service))
    install_specialist_access(app)
    token, _ = issue_specialist_session({'authority': 'github_actions_production_proof'},
        scope=PRODUCTION_PROOF_SCOPE, retained_claims={**CLAIMS, 'proof_role': 'recovery'})
    return TestClient(app), service, {'X-NICO-Operator-Session': token}


def test_authenticated_diagnostic_reads_once_without_render_cache_or_mutation(monkeypatch):
    value = record(); value['terminal'] = True
    value['final_report'] = {'private_artifact': 'x' * 1000000}
    before = deepcopy(value)
    client, service, headers = client_for(monkeypatch, value)
    denied = client.get(URL)
    assert denied.status_code in (401, 403)
    assert service.reads == 0
    headers['X-NICO-Browser-Projection'] = 'terminal-manifest-v1'
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    assert service.reads == 1
    assert len(response.content) < 2048
    assert response.json()['candidate_source_capture_diagnostics']['observation_count'] == 2
    assert 'private' not in response.text and 'secret' not in response.text
    assert value == before


@pytest.mark.parametrize('kind', ['absent', 'zero', 'mismatch'])
def test_diagnostic_states_remain_distinct(monkeypatch, kind):
    value = record(); value['terminal'] = True
    capture = value['stage_results']['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations']
    if kind == 'absent':
        value['stage_results'] = {}
    elif kind == 'zero':
        capture['observations'] = {}
    else:
        capture['scope']['project_id'] = 'different'
    client, _, headers = client_for(monkeypatch, value)
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    diagnostic = response.json()['candidate_source_capture_diagnostics']
    assert diagnostic['observation_count'] == (0 if kind == 'zero' else None)
    assert diagnostic['status'] == {'absent': 'missing', 'zero': 'available', 'mismatch': 'scope_mismatch'}[kind]


@pytest.mark.parametrize('damage', ['different_run', 'nonterminal'])
def test_invalid_target_fails_without_continuation(monkeypatch, damage):
    value = record(); value['terminal'] = True
    if damage == 'different_run':
        value['identity']['run_id'] = 'other'
    else:
        value['terminal'] = False
    client, service, headers = client_for(monkeypatch, value)
    response = client.get(URL, headers=headers)
    assert response.status_code == 422
    assert service.reads == 1
    assert 'observation_count' not in response.text


def test_malformed_capture_returns_small_unavailable_response(monkeypatch):
    value = record(); value['terminal'] = True
    value['stage_results']['repository_and_delivery_evidence']['repository_evidence']['candidate_source_observations']['observations'] = ['private error']
    client, service, headers = client_for(monkeypatch, value)
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    assert response.json()['candidate_source_capture_diagnostics']['status'] == 'malformed'
    assert response.json()['candidate_source_capture_diagnostics']['observation_count'] is None
    assert len(response.content) < 2048
    assert 'private error' not in response.text
    assert service.reads == 1


def test_failed_explicit_operator_login_does_not_fall_back(monkeypatch):
    from fastapi import HTTPException
    import nico.comprehensive_api_routes as routes
    value = record(); value['terminal'] = True
    client, service, headers = client_for(monkeypatch, value)
    def denied(token):
        raise HTTPException(status_code=403, detail='operator_access_denied')
    monkeypatch.setattr(routes, '_authorize_review', denied)
    headers['x-nico-admin-token'] = 'invalid-synthetic-token'
    response = client.get(URL, headers=headers)
    assert response.status_code == 403
    assert service.reads == 0


@pytest.mark.parametrize('missing_commitment', [False, True])
def test_real_store_diagnostic_read_works_with_database_query_only(tmp_path, missing_commitment):
    import sqlite3
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from tests.test_comprehensive_run_store import _record
    database = tmp_path / 'readonly.sqlite3'
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database), dialect='sqlite')
    store.ensure_schema()
    original = store.create(_record())
    if missing_commitment:
        with sqlite3.connect(database) as connection:
            connection.execute('DELETE FROM nico_comprehensive_review_history_commitments')
    before = database.read_bytes()
    def readonly_connection():
        connection = sqlite3.connect(database)
        connection.execute('PRAGMA query_only = ON')
        return connection
    readonly = ComprehensiveRunStore(readonly_connection, dialect='sqlite')
    if missing_commitment:
        with pytest.raises(ValueError, match='capture_diagnostic_review_commitment_unavailable'):
            readonly.load_without_maintenance('comprun_001')
    else:
        assert readonly.load_without_maintenance('comprun_001') == original
    assert database.read_bytes() == before


def test_storage_failure_does_not_expose_raw_error(monkeypatch):
    value = record(); value['terminal'] = True
    client, service, headers = client_for(monkeypatch, value)
    def failed(run_id):
        raise ValueError('private-path and secret payload')
    service.load_capture_diagnostics_record = failed
    response = client.get(URL, headers=headers)
    assert response.status_code == 503
    assert response.json() == {'detail': {'code': 'capture_diagnostic_unavailable'}}
