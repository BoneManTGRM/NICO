from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from nico import review_pdf_preparation_api_v1 as api
from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session
from nico.specialist_review_session_bridge_v1 import install_specialist_review_session_bridge, _bind_session_context
from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
from tests.test_review_pdf_preparation_jobs_v1 import identity
from tests.test_review_pdf_preparation_service_v1 import seam


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('NICO_ADMIN_TOKEN', 'synthetic-admin-token')
    monkeypatch.setenv('NICO_OPERATOR_SESSION_SIGNING_SECRET', 'synthetic-signing-key-' * 3)
    app = FastAPI()
    install_specialist_access(app)
    install_specialist_review_session_bridge(app)
    app.add_middleware(BaseHTTPMiddleware, dispatch=_bind_session_context)
    api.install_review_pdf_preparation_api(app)
    runtime = Mock()
    runtime.prepare.return_value = {'state': 'queued', 'client_delivery_allowed': False}
    runtime.status.return_value = {'state': 'preparing', 'client_delivery_allowed': False}
    runtime.cancel.return_value = {'state': 'cancelled'}
    app.state.review_pdf_runtime = runtime
    return TestClient(app), runtime, app


def path(suffix=''):
    return '/assessment/comprehensive-run/comprun_fixture/review-pdf/es-MX' + suffix


def binding():
    i = identity()
    return dict(commit_sha=i.commit_sha, canonical_truth_sha256=i.canonical_truth_sha256)


@pytest.mark.parametrize('method,suffix', [('POST',''),('GET',''),('GET','/pdf'),('POST','/cancel')])
def test_all_endpoints_require_authentication(client, method, suffix):
    http, runtime, _ = client
    assert http.request(method, path(suffix)).status_code == 401
    assert http.request(method, path(suffix), headers={'x-nico-admin-token':'bad'}).status_code == 403
    assert runtime.mock_calls == []


def test_signed_session_and_explicit_idempotent_request(client):
    http, runtime, _ = client
    token, _ = issue_specialist_session({'authority': 'nico_admin'})
    headers = {'x-nico-operator-session': token}
    for _ in range(2):
        response = http.post(path(), headers=headers, json={'prepare': True, **binding()})
        assert response.status_code == 202
        assert response.headers['cache-control'].startswith('no-store')
    assert runtime.prepare.call_count == 2  # Durable ledger, not HTTP memory, deduplicates.
    assert http.post(path(), headers=headers, json={'prepare': False, **binding()}).status_code == 422
    assert http.post(path(), headers=headers, json={'prepare': True, 'customer_id':'other', **binding()}).status_code == 422


def test_proof_scope_not_expanded(client):
    http, runtime, _ = client
    token, _ = issue_specialist_session({'authority':'nico_admin'}, scope='nico_production_proof',
        retained_claims={k:'synthetic' for k in ('repository','ref','sha','workflow_ref','run_id','run_attempt')})
    assert http.post(path(), json={'prepare':True, **binding()},
                     headers={'x-nico-operator-session':token}).status_code == 403
    assert runtime.mock_calls == []


def test_rollout_unavailable_and_scope_failures(client):
    http, runtime, app = client
    headers = {'x-nico-admin-token':'synthetic-admin-token'}
    runtime.status.side_effect = PreparationConflict('changed')
    params = {'job_id':identity().job_id, **binding()}
    assert http.get(path(), headers=headers, params=params).status_code == 409
    runtime.status.side_effect = KeyError('unknown')
    assert http.get(path(), headers=headers, params=params).status_code == 404
    app.state.review_pdf_runtime = None
    assert http.post(path(), headers=headers, json={'prepare':True, **binding()}).status_code == 503


def test_defaults_and_sqlite_never_activate(monkeypatch):
    monkeypatch.delenv('NICO_ENABLE_REVIEW_PDF_PREPARATION', raising=False)
    app = FastAPI()
    assert api._configured_runtime(app) is None
    monkeypatch.setenv('NICO_ENABLE_REVIEW_PDF_PREPARATION','true')
    monkeypatch.setenv('NICO_REVIEW_PDF_PG_QUALIFIED','true')
    app.state.comprehensive_api_controller = Mock()
    app.state.comprehensive_api_controller._service._store._dialect = 'sqlite'
    with pytest.raises(RuntimeError, match='verified_postgres_required'):
        api._configured_runtime(app)


@pytest.mark.parametrize('change', ['customer_id','project_id','revision','integrity_sha256','language','run_id'])
def test_job_lookup_fences_cross_scope_source_and_locale(change):
    i = identity()
    payload = dict(job_id=i.job_id, identity=asdict(i), status='queued')
    row = dict(payload=payload, customer_id=i.customer_id, project_id=i.project_id,
        repository=i.repository, commit_sha=i.commit_sha, revision=i.source_revision,
        integrity_sha256=i.source_integrity_sha256)
    jobs, source = MagicMock(), Mock()
    con = MagicMock(); con.execute.return_value.fetchone.return_value = row
    jobs.adapter._connect.return_value.__enter__.return_value = con
    runtime = api.PreparationRuntime(Mock(jobs=jobs, source=source))
    language, run_id = i.language, i.run_id
    if change == 'language': language = 'en'
    elif change == 'run_id': run_id = 'comprun_other'
    else: row[change] = 'changed'
    with pytest.raises(PreparationConflict):
        runtime._job(run_id, language, i.job_id, binding())
    assert "payload - 'pdf_base64'" in con.execute.call_args.args[0]


@pytest.mark.parametrize('change', ['none','bytes','approval','source','not_ready'])
def test_verified_retrieval_checks_retained_bytes_and_draft_gate(seam, monkeypatch, change):
    service, jobs, source, _, _, _, status = seam
    service.run_once(identity())
    runtime = api.PreparationRuntime(service)
    monkeypatch.setattr(runtime, '_job', lambda *a, **kw: (identity(), jobs.get(identity())))
    if change == 'source': status['scores'] = [100, 100]
    else:
        with jobs._transaction(identity()) as con:
            job = jobs._read(con, identity())
            if change == 'bytes': job['pdf_base64'] = 'AAAA'
            if change == 'approval': job['result_headers']['x-nico-accepted-pdf-sha256'] = 'a' * 64
            if change == 'not_ready': job['status'] = 'rendered_unverified'
            jobs._write(con, identity(), job)
    if change == 'none':
        response = runtime.retrieve(identity().run_id, identity().language, identity().job_id, binding())
        assert response.body.startswith(b'%PDF')
        assert response.headers['x-nico-client-delivery-allowed'] == 'false'
    else:
        with pytest.raises((PreparationConflict, ValueError)):
            runtime.retrieve(identity().run_id, identity().language, identity().job_id, binding())


def test_cancel_fences_old_worker_and_recovery_isolates_bad_rows(seam, monkeypatch):
    service, jobs, source, _, _, _, _ = seam
    lease = jobs.claim(identity())
    runtime = api.PreparationRuntime(service)
    monkeypatch.setattr(runtime, '_job', lambda *a, **kw: (identity(), jobs.get(identity())))
    assert runtime.cancel(identity().run_id, identity().language, identity().job_id, binding())['state'] == 'cancelled'
    with pytest.raises(PreparationConflict): jobs.heartbeat(identity(), lease['lease_id'])
    fake_service = MagicMock()
    con = MagicMock()
    con.execute.return_value.fetchall.return_value = [dict(job_id='bad',identity={}),
        dict(job_id='good',identity=asdict(identity()))]
    fake_service.jobs.adapter._connect.return_value.__enter__.return_value = con
    recovering = api.PreparationRuntime(fake_service)
    recovering.stop.wait = lambda seconds: recovering.stop.set()
    recovering._recover()
    fake_service.run_once.assert_called_once()
    assert "jsonb_typeof" in con.execute.call_args.args[0]


def test_original_lifespan_state_and_cleanup_preserved(monkeypatch):
    from contextlib import asynccontextmanager
    events = []
    @asynccontextmanager
    async def original(app):
        events.append('original-start')
        yield {'existing_state': 'preserved'}
        events.append('original-stop')
    app = FastAPI(lifespan=original)
    runtime = Mock()
    runtime.start.side_effect = lambda: events.append('worker-start')
    runtime.close.side_effect = lambda: events.append('worker-stop')
    monkeypatch.setattr(api, '_configured_runtime', lambda app: runtime)
    api.install_review_pdf_preparation_api(app)
    with TestClient(app) as client:
        assert client.app_state['existing_state'] == 'preserved'
        assert app.state.review_pdf_runtime is runtime
    assert events == ['original-start', 'worker-start', 'worker-stop', 'original-stop']


def test_start_failure_closes_partial_runtime_and_stays_unavailable(monkeypatch):
    app = FastAPI()
    runtime = Mock()
    runtime.start.side_effect = RuntimeError('synthetic failure')
    monkeypatch.setattr(api, '_configured_runtime', lambda app: runtime)
    api.install_review_pdf_preparation_api(app)
    with TestClient(app):
        assert app.state.review_pdf_runtime is None
    runtime.close.assert_called_once()


def test_activation_reuses_canonical_factory_without_schema_initialization(monkeypatch):
    from nico.storage import PostgresAdapter
    from nico.comprehensive_final_report_background_v1 import _PUBLICATION_SLOT
    monkeypatch.setenv('NICO_ENABLE_REVIEW_PDF_PREPARATION', 'true')
    monkeypatch.setenv('NICO_REVIEW_PDF_PG_QUALIFIED', 'true')
    monkeypatch.setattr(PostgresAdapter, '__init__', Mock(side_effect=AssertionError('no schema init')))
    monkeypatch.setattr(api, 'runtime_policy', lambda: ('e' * 40, 'f' * 64))
    app = FastAPI()
    controller = MagicMock()
    controller._service._store._dialect = 'postgres'
    connection = controller._service._store._connection_factory.return_value
    app.state.comprehensive_api_controller = controller
    app.state.comprehensive_runtime = dict(persistence_adapter='postgres', survives_container_replacement_verified=True)
    runtime = api._configured_runtime(app)
    assert runtime.source.store is controller._service._store
    assert runtime.service.capacity is _PUBLICATION_SLOT
    assert runtime.thread is None
    statements = [call.args[0] for call in connection.__enter__.return_value.execute.call_args_list]
    assert len(statements) == 3
    assert all(statement.startswith('SELECT ') and statement.endswith(' LIMIT 0') for statement in statements)
    PostgresAdapter.__init__.assert_not_called()


@pytest.mark.parametrize('invalid', ['none', 'commitment', 'approval', 'delivery', 'binding'])
def test_prepare_consumes_validated_snapshot_and_deduplicates(seam, monkeypatch, invalid):
    service, jobs, source, _, worker, _, _ = seam
    i = identity()
    record = dict(identity={key: getattr(i, key) for key in ('customer_id','project_id','repository','commit_sha')},
        terminal=True, revision=i.source_revision, integrity_sha256=i.source_integrity_sha256)
    status = {'reports': {'canonical_truth_sha256':i.canonical_truth_sha256, 'pdf_sha256':i.source_artifact_sha256}}
    source.policy.return_value = (i.renderer_revision, i.policy_sha256)
    source.controller._status_artifact_from_record.return_value = status
    restore = Mock(return_value=record)
    source.store._consume_read_snapshot.side_effect = lambda run, consume: consume(
        [None, None if invalid == 'commitment' else 1, 'chain'], restore)
    from nico import comprehensive_same_run_locale_report_v1 as locale
    monkeypatch.setattr(locale, '_source_lifecycle_projection', lambda *args: {
        'approval_status':'approved' if invalid == 'approval' else 'pending_human_approval',
        'client_delivery_allowed':invalid == 'delivery'})
    runtime = api.PreparationRuntime(service)
    context = binding() if invalid != 'binding' else {**binding(), 'commit_sha':'0'*40}
    if invalid == 'none':
        first = runtime.prepare(i.run_id, i.language, context)
        assert first == runtime.prepare(i.run_id, i.language, context)
        assert first['state'] == 'queued' and first['client_delivery_allowed'] is False
        assert jobs.get(i)['attempts'] == 0
    else:
        with pytest.raises(PreparationConflict): runtime.prepare(i.run_id, i.language, context)
    if invalid == 'commitment': restore.assert_not_called()
    worker.assert_not_called()
