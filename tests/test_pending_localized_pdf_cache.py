"""Bounded cache contracts; installed render fixtures are exercised separately."""
from threading import Event, Thread

import pytest
from fastapi import Response, HTTPException

from tests.test_retained_pdf_exact_input_cache_v1 import retained, _replace_payload
from nico import retained_pdf_exact_input_cache_v1 as cache
from nico import comprehensive_same_run_locale_report_v1 as locale


@pytest.fixture
def draft(retained, monkeypatch):
    database, run_id, endpoint, body, calls, controller = retained
    original = locale.build_same_run_locale_pdf_response
    renders = []
    def build(status, language):
        response = original(status, language)
        headers = dict(response.headers)
        headers.pop('x-nico-frozen-source-artifact')
        headers.update({'x-nico-localized-artifact-requires-new-approval':'true',
            'x-nico-localized-artifact-approval-invalidated':'true',
            'x-nico-artifact-finality':'automated_draft'})
        renders.append(True)
        return Response(response.body, media_type='application/pdf', headers=headers)
    build.frozen_builder = original
    monkeypatch.setattr(locale, 'build_same_run_locale_pdf_response', build)
    return retained, renders


def test_distinct_draft_entry_reuses_exact_bytes_and_headers(draft):
    (database, run_id, endpoint, body, calls, controller), renders = draft
    first = endpoint(run_id,'en')
    second = endpoint(run_id,'en')
    assert second.body == first.body and dict(second.headers) == dict(first.headers)
    assert first is not second
    assert second.headers['x-nico-localized-artifact-requires-new-approval'] == 'true'
    assert second.headers['x-nico-localized-artifact-approval-invalidated'] == 'true'
    assert len(renders) == len(calls) == 1


def test_finalizer_rebinding_invalidates_policy():
    from nico import client_report_completion_v2 as completion
    before = cache._live_policy(locale.build_same_run_locale_pdf_response)
    old = completion.finalize_client_report_package
    try:
        completion.finalize_client_report_package = lambda package: old(package)
        assert cache._live_policy(locale.build_same_run_locale_pdf_response) != before
    finally:
        completion.finalize_client_report_package = old


@pytest.mark.parametrize('header,value', [
    ('x-nico-run-id','wrong'), ('x-nico-commit-sha','a'*40),
    ('x-nico-report-language','es-MX'), ('x-nico-pdf-sha256','0'*64),
    ('x-nico-artifact-sha256','0'*64), ('x-nico-canonical-truth-sha256','invalid'),
    ('x-nico-client-delivery-allowed','true'), ('x-nico-approval-status','approved'),
    ('x-nico-delivery-status','ready'), ('x-nico-assessment-rerun','true'),
    ('x-nico-localized-artifact-requires-new-approval','false'),
    ('x-nico-localized-artifact-approval-invalidated',None),
    ('x-nico-artifact-finality','accepted'), ('x-nico-frozen-source-artifact','true'),
    ('set-cookie','session=bad'), ('x-custom-authority','approved')])
def test_draft_authority_rejects_changed_headers(draft,header,value):
    (_,run_id,endpoint,_,_,_),_ = draft
    response=endpoint(run_id,'en')
    row=[None]*14;row[7]='b'*40
    assert cache._pending_localized_pdf(response,run_id,'en',row) is not None
    if value is None: del response.headers[header]
    else: response.headers[header]=value
    row=[None]*14;row[7]='b'*40
    assert cache._pending_localized_pdf(response,run_id,'en',row) is None


def test_draft_rejects_duplicate_headers(draft):
    (_,run_id,endpoint,_,_,_),_=draft
    response=endpoint(run_id,'en')
    row=[None]*14;row[7]='b'*40
    assert cache._pending_localized_pdf(response,run_id,'en',row) is not None
    response.raw_headers.append((b'x-nico-client-delivery-allowed',b'true'))
    row=[None]*14;row[7]='b'*40
    assert cache._pending_localized_pdf(response,run_id,'en',row) is None


@pytest.mark.parametrize('module,attribute', [
    ('comprehensive_spanish_canonical_report_v87','_translate_presentation'),
    ('phase17_canonical_artifact_rebuild_v1','rebuild_client_artifacts'),
    ('client_report_completion_v2','finalize_client_report_package')])
def test_live_renderer_rebinding_invalidates_draft(draft,monkeypatch,module,attribute):
    import importlib
    target=importlib.import_module('nico.'+module)
    (_,run_id,endpoint,_,calls,_),renders=draft
    endpoint(run_id,'en')
    old=getattr(target,attribute)
    monkeypatch.setattr(target,attribute,lambda *args,**kwargs:old(*args,**kwargs))
    endpoint(run_id,'en')
    assert len(calls)==len(renders)==2


def test_pending_draft_tampering_still_restores_and_rejects(draft):
    (database,run_id,endpoint,_,calls,_),_=draft
    endpoint(run_id,'en')
    _replace_payload(database,run_id,lambda record:record.update(progress_percent=1))
    with pytest.raises(HTTPException) as failure: endpoint(run_id,'en')
    assert failure.value.status_code==409
    assert len(calls)==2


def test_busy_miss_does_not_restore_and_owner_releases_after_real_exit(draft,monkeypatch):
    (_,run_id,endpoint,_,calls,_),_=draft
    original=locale.build_same_run_locale_pdf_response
    entered=Event();release=Event();results=[]
    def slow(*args,**kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(locale,'build_same_run_locale_pdf_response',slow)
    worker=Thread(target=lambda:results.append(endpoint(run_id,'en')))
    worker.start()
    try:
        assert entered.wait(10)
        worker.join(.01)  # A caller ceasing to wait must not release the owner.
        assert worker.is_alive()
        with pytest.raises(HTTPException) as failure: endpoint(run_id,'en')
        assert failure.value.status_code==503
        assert failure.value.headers=={'Retry-After':'5','Cache-Control':'no-store'}
        assert len(calls)==1
        assert cache._active_computation is not None
    finally:
        release.set();worker.join(10)
    assert not worker.is_alive() and len(results)==1
    assert cache._active_computation is None
    assert endpoint(run_id,'en').body==results[0].body
    assert len(calls)==1


def test_builder_failure_releases_owner(draft,monkeypatch):
    (_,run_id,endpoint,_,_,_),_=draft
    original=locale.build_same_run_locale_pdf_response
    def fail(*args,**kwargs): raise ValueError('owned failure')
    monkeypatch.setattr(locale,'build_same_run_locale_pdf_response',fail)
    with pytest.raises(HTTPException): endpoint(run_id,'en')
    assert cache._active_computation is None
    monkeypatch.setattr(locale,'build_same_run_locale_pdf_response',original)
    assert endpoint(run_id,'en').status_code==200


def test_warm_hit_can_complete_while_other_computation_owns_slot(draft):
    (_,run_id,endpoint,_,calls,_),_=draft
    first=endpoint(run_id,'en')
    with cache.RetainedPdfComputation() as owner:
        owner.acquire()
        assert endpoint(run_id,'en').body==first.body
        with cache.RetainedPdfComputation() as competitor:
            with pytest.raises(cache.RetainedPdfBusy): competitor.acquire()
        assert cache._active_computation is owner.token
    assert len(calls)==1 and cache._active_computation is None


def test_render_time_policy_change_never_mints_old_entry(draft,monkeypatch):
    from nico import client_report_completion_v2 as completion
    (_,run_id,endpoint,_,calls,controller),renders=draft
    original=locale.build_same_run_locale_pdf_response
    old=completion.finalize_client_report_package
    def changing(*args,**kwargs):
        result=original(*args,**kwargs)
        monkeypatch.setattr(completion,'finalize_client_report_package',lambda *a,**k:old(*a,**k))
        return result
    monkeypatch.setattr(locale,'build_same_run_locale_pdf_response',changing)
    endpoint(run_id,'en');endpoint(run_id,'en')
    assert len(calls)==len(renders)==2
    assert not any(key[0][0] is controller._retained_pdf_cache_namespace for key in cache._entries)


def test_shared_budget_and_oversized_draft_not_admitted(draft,monkeypatch):
    (_,run_id,endpoint,_,calls,_),renders=draft
    monkeypatch.setattr(cache,'MAX_RETAINED_BYTES',1000)
    endpoint(run_id,'en');endpoint(run_id,'en')
    assert len(calls)==len(renders)==2


def test_frozen_and_draft_share_population_and_accounting(draft,monkeypatch):
    (_,run_id,endpoint,_,_,controller),_=draft
    from nico.comprehensive_api_controller import ComprehensiveApiController
    monkeypatch.setattr(cache,'MAX_ENTRIES',2)
    endpoint(run_id,'en')
    for index in range(3):
        other=ComprehensiveApiController(controller._service)
        builder=locale.build_same_run_locale_pdf_response
        if index % 2 == 0: builder=builder.frozen_builder
        other.retained_pdf_read_only(run_id,'en',builder)
    assert {type(entry) for entry,_ in cache._entries.values()} == {cache._PendingPdf,cache._PendingLocalizedPdf}
    assert len(cache._entries)==2
    assert cache._retained_bytes==sum(size for _,size in cache._entries.values())
    assert cache._retained_bytes<=cache.MAX_RETAINED_BYTES


def test_warm_draft_still_authenticates_every_http_request(draft,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nico.specialist_access_v1 import install_specialist_access
    (_,run_id,_,_,calls,controller),renders=draft
    monkeypatch.setenv('NICO_COMPREHENSIVE_OPERATOR_PASSWORD','owned-cache-test-password')
    monkeypatch.setenv('NICO_OPERATOR_SESSION_SIGNING_SECRET','owned-cache-test-secret-long-enough')
    app=FastAPI();app.state.comprehensive_api_controller=controller
    locale.install_same_run_locale_report(app);install_specialist_access(app)
    client=TestClient(app)
    path=locale.PDF_ROUTE.replace('{run_id}',run_id).replace('{report_language}','en')
    headers={'X-NICO-Admin-Token':'owned-cache-test-password'}
    first=client.get(path,headers=headers)
    assert first.status_code==200
    assert client.get(path).status_code==401
    assert client.get(path,headers={'X-NICO-Admin-Token':'wrong'}).status_code==403
    second=client.get(path,headers=headers)
    assert second.status_code==200 and second.content==first.content
    assert len(calls)==len(renders)==1


def test_draft_changed_history_commitment_rejects_warm_entry(draft):
    import sqlite3
    (database,run_id,endpoint,_,calls,_),_=draft
    endpoint(run_id,'en')
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE nico_comprehensive_review_history_commitments SET chain_sha256=? WHERE run_id=?',('f'*64,run_id))
    with pytest.raises(HTTPException) as failure: endpoint(run_id,'en')
    assert failure.value.status_code==409 and len(calls)==2
    assert cache._active_computation is None
