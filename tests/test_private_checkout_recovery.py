from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nico import comprehensive_scanner_checkout_recovery_v1 as module
from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session
from tests.test_scanner_recovery import _MemoryStore

RUN = 'comprun_private'
SCAN = 'scan_snapshot_private'
SHA = 'a' * 40
PATH = f'/assessment/comprehensive-run/{RUN}/scanner-checkout-recovery'

@pytest.fixture
def case(monkeypatch):
    monkeypatch.setenv('NICO_ADMIN_TOKEN', 'synthetic-owner')
    monkeypatch.setenv('NICO_OPERATOR_SESSION_SIGNING_SECRET', 'synthetic-session-signing-secret-long-enough')
    identity = dict(run_id=RUN, customer_id='customer', project_id='project', repository='example/private', commit_sha=SHA)
    snapshot = dict(repository=identity['repository'], snapshot_id='snapshot_private', commit_sha=SHA, access_mode='authenticated_read_only', credential_used=True)
    record = dict(identity=identity, status='blocked', current_stage=module.STAGE, stage_results={module.STAGE:dict(scan_id=SCAN, reason='snapshot_scanner_not_verified'), 'immutable_repository_snapshot':dict(snapshot=snapshot)})
    scan = dict(identity, scan_id=SCAN, snapshot_id=snapshot['snapshot_id'], snapshot_commit_sha=SHA, actual_commit_sha='', snapshot_match=False, status='unavailable', current_stage='snapshot_verification_failed', scanner_results=[], tools_run=[], tools_requested=['gitleaks'], authorized_by='owner', authorization_scope='defensive repository assessment', unavailable_data_notes=['Exact snapshot ancestry fetch failed: synthetic failure'])
    store = _MemoryStore([scan])
    monkeypatch.setattr(module, 'STORE', store)
    calls = []
    def load(run_id):
        calls.append(run_id)
        return deepcopy(record)
    workers = []
    class Thread:
        def __init__(self, **kw): self.kw = kw
        def start(self): workers.append(self.kw)
    monkeypatch.setattr(module, 'threading', SimpleNamespace(Thread=Thread))
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(_service=SimpleNamespace(load_read_only=load))
    install_specialist_access(app)
    module.install_scanner_checkout_recovery(app)
    token, _ = issue_specialist_session({'authority':'nico_admin'})
    return SimpleNamespace(client=TestClient(app), headers={'X-NICO-Operator-Session':token}, record=record, store=store, workers=workers, calls=calls)

def inspect(c): return c.client.get(PATH, headers=c.headers)
def retry(c, value): return c.client.post(PATH, headers=c.headers, json={k:value[k] for k in ('scan_id','commit_sha','failure_fingerprint')})

def test_inspect_is_read_only_and_retry_preserves_same_scan_and_failure(case):
    before = deepcopy(case.store.records[SCAN])
    record = deepcopy(case.record)
    response = inspect(case)
    assert response.status_code == 200 and response.json()['retry_allowed'] is True
    assert case.store.records[SCAN] == before and case.workers == []
    assert 'synthetic failure' not in response.text
    result = retry(case, response.json())
    assert result.status_code == 202
    assert len(case.store.records) == 1 and case.record == record
    updated = case.store.records[SCAN]
    assert updated[module.MARKER]['previous_failure'] == before
    assert updated['status'] == 'queued'
    assert updated['provider_access_mode'] == 'authenticated_read_only'
    from nico.snapshot_scanner_worker import _run_snapshot_scan
    assert case.workers[0]['target'] is _run_snapshot_scan
    scan_id, payload = case.workers[0]['args']
    assert scan_id == SCAN and payload['run_id'] == RUN and payload['snapshot_commit_sha'] == SHA
    assert payload['authorized'] is True and payload['provider_credential_used'] is True
    assert payload['tools'] == before['tools_requested']
    assert retry(case, response.json()).status_code == 409
    # Even a fast failed worker returning to the original state cannot be retried.
    updated.update(status='unavailable', current_stage='snapshot_verification_failed')
    assert inspect(case).json()['retry_allowed'] is False
    assert len(case.workers) == 1

@pytest.mark.parametrize('authority', [None, 'nico_comprehensive_operator', 'nico_internal'])
def test_nonowner_denied_before_read(case, authority):
    headers = {}
    if authority:
        token,_ = issue_specialist_session({'authority':authority})
        headers={'X-NICO-Operator-Session':token}
    for method in ('get','post'):
        assert getattr(case.client,method)(PATH,headers=headers).status_code in (401,403)
    assert case.calls == [] and case.workers == []

@pytest.mark.parametrize('field,value', [('status','complete'), ('actual_commit_sha',SHA), ('snapshot_match',True), ('scanner_results',[{'tool':'gitleaks'}]), ('tools_run',['gitleaks']), ('unavailable_data_notes',['different failure']), ('authorized_by',''), ('tools_requested',[])])
def test_no_replacement_of_executed_or_unrelated_scans(case, field, value):
    case.store.records[SCAN][field] = value
    response=inspect(case)
    assert response.json()['retry_allowed'] is False
    assert retry(case,response.json()).status_code == 409
    assert case.workers == []

@pytest.mark.parametrize('field', ['run_id','repository','customer_id','project_id','snapshot_id','snapshot_commit_sha'])
def test_identity_mismatch_fail_closed(case, field):
    case.store.records[SCAN][field] = 'wrong'
    assert inspect(case).status_code == 409
    assert case.workers == []

def test_stale_diagnosis_or_extra_payload_rejected(case):
    value=inspect(case).json()
    case.store.records[SCAN]['updated_at']='changed'
    assert retry(case,value).status_code == 409
    assert case.client.post(PATH,headers=case.headers,json={**value,'authorized':True}).status_code == 409
    assert case.workers == []

def test_worker_start_failure_retains_failure_and_marker(case, monkeypatch):
    class BadThread:
        def __init__(self, **kw): pass
        def start(self): raise RuntimeError('sensitive-details')
    monkeypatch.setattr(module,'threading',SimpleNamespace(Thread=BadThread))
    result=retry(case,inspect(case).json())
    assert result.status_code == 503 and 'sensitive-details' not in result.text
    assert case.store.records[SCAN]['status'] == 'unavailable'
    assert module.MARKER in case.store.records[SCAN]

def test_public_snapshot_not_promoted(case):
    snapshot=case.record['stage_results']['immutable_repository_snapshot']['snapshot']
    snapshot.update(access_mode='anonymous_public',credential_used=False)
    assert inspect(case).status_code == 409
    assert case.workers == []

def test_atomic_marker_cannot_be_claimed_twice(case):
    from nico.scanner_recovery import atomic_scanner_transition
    first=atomic_scanner_transition(SCAN,{'unavailable'},'unavailable',{module.MARKER:{}},store=case.store,require_absent_field=module.MARKER)
    second=atomic_scanner_transition(SCAN,{'unavailable'},'queued',{},store=case.store,require_absent_field=module.MARKER)
    assert first and second is None
