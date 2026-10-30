"""Synthetic metadata projection: no production database or activation."""
from copy import deepcopy
from dataclasses import asdict
import json
import sqlite3
from threading import BoundedSemaphore, Event
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest

from nico import review_pdf_retained_binding_v1 as view
from nico.review_pdf_canary_scope_v1 import FIELDS, CanaryScope
from nico.specialist_access_v1 import issue_specialist_session
from tests.test_review_pdf_preparation_api_v1 import client, path
from tests.test_review_pdf_preparation_jobs_v1 import identity


def fixture():
    i = identity()
    record = dict(identity={k:getattr(i,k) for k in
        ('run_id','customer_id','project_id','repository','commit_sha')}, terminal=True,
        revision=i.source_revision, integrity_sha256=i.source_integrity_sha256,
        status='review_required')
    status = dict(record['identity'], terminal=True, revision=record['revision'],
        integrity_sha256=record['integrity_sha256'], report_language='en', status='review_required',
        reports=dict(canonical_truth_sha256=i.canonical_truth_sha256,
                     pdf_sha256=i.source_artifact_sha256, json={}))
    store = SimpleNamespace(load_without_maintenance=Mock(return_value=record))
    controller = SimpleNamespace(_service=SimpleNamespace(_store=store),
        _status_artifact_from_record=Mock(return_value=status))
    app = SimpleNamespace(state=SimpleNamespace(comprehensive_api_controller=controller))
    return app, store, record, status


def read(app):
    return view.retained_binding(app, identity().run_id, 'es-MX')


def test_exact_allowlisted_binding_and_no_body_or_model_flags():
    app, store, record, status = fixture()
    status['reports']['private_report_body']='NEVER_EXPOSE_THIS'
    status['raw_error']='NEVER_EXPOSE_THIS'
    before=deepcopy(record)
    result=read(app)
    assert result['status']=='available'
    assert set(result['binding'])==FIELDS
    assert result['binding']=={k:v for k,v in asdict(identity()).items() if k in FIELDS}
    CanaryScope(result['binding'])
    assert result['source_report_language']=='en'  # Source PDF, despite requested es-MX.
    assert result['binding']['source_artifact_sha256']==status['reports']['pdf_sha256']
    assert result['lifecycle_qualified'] is result['activation_authorized'] is False
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True
    assert 'NEVER_EXPOSE_THIS' not in json.dumps(result)
    assert len(json.dumps(result).encode())<view.MAX_RESPONSE_BYTES
    assert record==before
    store.load_without_maintenance.assert_called_once_with(identity().run_id)


@pytest.mark.parametrize('field', ['run_id','customer_id','project_id','repository','commit_sha','revision','integrity_sha256'])
def test_projected_identity_mismatch_is_not_exported(field):
    app, _, _, status=fixture();status[field]='foreign'
    assert read(app)==view.unavailable()


@pytest.mark.parametrize('change', ['missing_report','bad_hash','not_terminal','approved','delivery','invalid_locale','bad_revision','foreign_record','oversize'])
def test_missing_malformed_and_unsupported_evidence_is_fail_closed(change):
    app, _, record, status=fixture()
    if change=='missing_report':status['reports']={}
    if change=='bad_hash':status['reports']['pdf_sha256']='bad'
    if change=='not_terminal':record['terminal']=False
    if change=='approved':record['status']=status['status']='approved'
    if change=='delivery':status['client_delivery_allowed']=True
    if change=='invalid_locale':status['report_language']='fr'
    if change=='bad_revision':record['revision']=status['revision']=True
    if change=='foreign_record':record['identity']['run_id']='comprun_foreign'
    if change=='oversize':record['identity']['customer_id']=status['customer_id']='界'*2048;record['identity']['project_id']=status['project_id']='界'*2048;record['identity']['repository']=status['repository']='界'*2048
    assert read(app)==view.unavailable()


def test_storage_exception_never_leaks_text_or_partial_binding():
    app, store, _, _=fixture()
    store.load_without_maintenance.side_effect=ValueError('postgres://password/private-customer')
    assert read(app)==view.unavailable()


@pytest.mark.parametrize('authority', ['none','invalid','proof'])
def test_route_requires_existing_operator_authority(client,monkeypatch,authority):
    http,runtime,app=client
    reader=Mock();monkeypatch.setattr(view,'retained_binding',reader)
    headers={}
    if authority=='invalid':headers={'x-nico-admin-token':'invalid'}
    if authority=='proof':
        token,_=issue_specialist_session({'authority':'nico_admin'},scope='nico_production_proof',
            retained_claims={k:'synthetic' for k in ('repository','ref','sha','workflow_ref','run_id','run_attempt')})
        headers={'x-nico-operator-session':token}
    assert http.get(path()+'?retained_binding=true',headers=headers).status_code in {401,403}
    reader.assert_not_called();assert runtime.mock_calls==[]


def test_signed_operator_can_read_while_preparation_disabled(client,monkeypatch):
    http,runtime,app=client;app.state.review_pdf_runtime=None
    reader=Mock(return_value=view.unavailable());monkeypatch.setattr(view,'retained_binding',reader)
    token,_=issue_specialist_session({'authority':'nico_admin'})
    result=http.get(path()+'?retained_binding=true',headers={'x-nico-operator-session':token})
    assert result.status_code==200 and result.json()==view.unavailable()
    assert result.headers['cache-control']=='no-store, private, max-age=0'
    reader.assert_called_once_with(app,'comprun_fixture','es-MX')
    assert runtime.mock_calls==[]


@pytest.mark.parametrize('suffix', ['/pdf?retained_binding=true','/cancel?retained_binding=true',
    '?retained_binding=false','?retained_binding=true&extra=x',
    '?retained_binding=true&retained_binding=true'])
def test_strict_route_query_and_no_artifact_side_effects(client,monkeypatch,suffix):
    http,runtime,_=client;reader=Mock();monkeypatch.setattr(view,'retained_binding',reader)
    expected = 405 if suffix.startswith('/cancel?') else 422
    assert http.get(path(suffix),headers={'x-nico-admin-token':'synthetic-admin-token'}).status_code==expected
    reader.assert_not_called();assert runtime.mock_calls==[]


def test_timeout_quarantines_capacity_until_physical_completion(monkeypatch):
    from nico import comprehensive_final_report_background_v1 as capacity
    slot=BoundedSemaphore(1);publication=BoundedSemaphore(1)
    monkeypatch.setattr(view,'_SLOT',slot);monkeypatch.setattr(capacity,'_PUBLICATION_SLOT',publication)
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    monkeypatch.setattr(view,'DeadlineGuard',lambda seconds,stop:DeadlineGuard(.02,stop))
    entered,release,finished=Event(),Event(),Event()
    def blocked(*args):
        entered.set();release.wait(2);finished.set();return {'secret':'late result'}
    monkeypatch.setattr(view,'inspect_binding',blocked)
    assert read(object())==view.unavailable();assert entered.is_set()
    assert read(object())==view.unavailable('busy')
    assert not publication.acquire(blocking=False)
    release.set();assert finished.wait(1)
    until=time.monotonic()+1
    while time.monotonic()<until:
        if slot.acquire(blocking=False):break
        time.sleep(.01)
    else:pytest.fail('metadata capacity not released')
    assert publication.acquire(blocking=False)


def test_existing_publication_busy_skips_all_reads(monkeypatch):
    from nico import comprehensive_final_report_background_v1 as capacity
    publication=BoundedSemaphore(1);publication.acquire()
    monkeypatch.setattr(capacity,'_PUBLICATION_SLOT',publication)
    app,store,_,_=fixture()
    assert read(app)==view.unavailable('busy')
    store.load_without_maintenance.assert_not_called()


@pytest.fixture(scope='module')
def owned_record():
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record
    return build_owned_record('en')


@pytest.mark.parametrize('missing_commitment',[False,True])
def test_real_query_only_store_validates_binding_without_writes(tmp_path,owned_record,missing_commitment,monkeypatch):
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from scripts.postgres_review_pdf_lifecycle_proof import controller_for
    database=tmp_path/'owned.sqlite'
    store=ComprehensiveRunStore(lambda:sqlite3.connect(database))
    store.ensure_schema() # Disposable synthetic fixture setup only.
    original=store.create(owned_record)
    if missing_commitment:
        with sqlite3.connect(database) as con:con.execute('DELETE FROM nico_comprehensive_review_history_commitments')
    before=database.read_bytes();commands=[]
    def connection():
        con=sqlite3.connect(database);con.execute('PRAGMA query_only=ON');con.set_trace_callback(commands.append);return con
    readonly=ComprehensiveRunStore(connection)
    controller=controller_for(readonly)
    forbidden=Mock(side_effect=AssertionError('no maintenance, render, continuation or cache refresh'))
    monkeypatch.setattr(controller, 'status', forbidden)
    monkeypatch.setattr(controller._service, 'load', forbidden)
    monkeypatch.setattr(controller._service, 'resume', forbidden)
    monkeypatch.setattr(readonly, 'load', forbidden)
    monkeypatch.setattr(readonly, 'ensure_schema', forbidden)
    import nico.comprehensive_same_run_locale_report_v1 as locale
    monkeypatch.setattr(locale, 'build_same_run_locale_pdf_response', forbidden)
    app=SimpleNamespace(state=SimpleNamespace(comprehensive_api_controller=controller))
    result=view.retained_binding(app,original['identity']['run_id'],'es-MX')
    assert database.read_bytes()==before
    assert commands and all(sql.lstrip().startswith('SELECT') for sql in commands)
    if missing_commitment:assert result==view.unavailable()
    else:
        assert result['status']=='available'
        assert result['binding']['source_revision']==original['revision']
        assert result['binding']['source_integrity_sha256']==original['integrity_sha256']
        report=original['stage_results']['final_comprehensive_report_generation']['report_package']
        assert result['binding']['source_artifact_sha256']==report['pdf_sha256']
        assert result['binding']['canonical_truth_sha256']==report['canonical_truth_sha256']
        assert result['binding']==dict(
            {k:original['identity'][k] for k in ('customer_id','project_id','run_id','repository','commit_sha')},
            source_revision=original['revision'], source_integrity_sha256=original['integrity_sha256'],
            canonical_truth_sha256=report['canonical_truth_sha256'], source_artifact_sha256=report['pdf_sha256'], language='es-MX')
        assert readonly.load_without_maintenance(original['identity']['run_id'])==original
    forbidden.assert_not_called()


@pytest.mark.parametrize('corrupt',['pdf','canonical','language'])
def test_real_package_boundary_rejects_corrupt_artifacts(owned_record,corrupt):
    from scripts.postgres_review_pdf_lifecycle_proof import controller_for
    record=deepcopy(owned_record)
    report=record['stage_results']['final_comprehensive_report_generation']['report_package']
    if corrupt=='pdf':report['pdf_sha256']='f'*64
    if corrupt=='canonical':report['canonical_truth_sha256']='f'*64
    if corrupt=='language':report['json']['identity']['report_language']='es-MX'
    store=SimpleNamespace(load_without_maintenance=Mock(return_value=record))
    controller=controller_for(store)
    app=SimpleNamespace(state=SimpleNamespace(comprehensive_api_controller=controller))
    assert view.retained_binding(app,record['identity']['run_id'],'es-MX')==view.unavailable()


@pytest.mark.parametrize('run_id,language',[('foreign','es-MX'),('comprun_fixture','fr')])
def test_invalid_route_scope_is_rejected_before_read(client,monkeypatch,run_id,language):
    http,_,_=client;reader=Mock();monkeypatch.setattr(view,'retained_binding',reader)
    url=f'/assessment/comprehensive-run/{run_id}/review-pdf/{language}?retained_binding=true'
    assert http.get(url,headers={'x-nico-admin-token':'synthetic-admin-token'}).status_code==422
    reader.assert_not_called()


def test_preparation_qualification_uses_exact_same_binding(tmp_path,owned_record):
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from scripts.postgres_review_pdf_lifecycle_proof import controller_for
    from nico.review_pdf_preparation_service_v1 import RetainedSourceAuthority
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
    database=tmp_path/'same.sqlite';store=ComprehensiveRunStore(lambda:sqlite3.connect(database))
    store.ensure_schema();original=store.create(owned_record)
    controller=controller_for(store);app=SimpleNamespace(state=SimpleNamespace(comprehensive_api_controller=controller))
    result=view.retained_binding(app,original['identity']['run_id'],'es-MX')
    binding=result['binding'];before=database.read_bytes()
    source=RetainedSourceAuthority(store,controller,lambda:('e'*40,'f'*64))
    service=SimpleNamespace(source=source,jobs=Mock(),capacity=BoundedSemaphore(1))
    runtime=PreparationRuntime(service,canary_scope=CanaryScope(binding))
    qualified=runtime.qualify(binding['run_id'],binding['language'],
        {key:binding[key] for key in ('commit_sha','canonical_truth_sha256')})
    expected=PreparationIdentity(**binding,renderer_revision='e'*40,policy_sha256='f'*64,artifact_mode=qualified['artifact_mode'])
    assert qualified['job_id']==expected.job_id
    assert qualified['state']=='eligible'
    assert service.jobs.mock_calls==[]
    assert database.read_bytes()==before
