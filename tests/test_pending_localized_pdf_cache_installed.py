"""Actual installed assembler/renderer/finalizer; no fake artifact or validator."""
import hashlib
import sqlite3

import pytest
from fastapi import FastAPI


@pytest.mark.parametrize('source_language,target_language', [('en','es-MX'),('es-MX','en')])
def test_installed_render_cache_requires_stable_live_policy(tmp_path,monkeypatch,source_language,target_language):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico.comprehensive_run_record import create_comprehensive_run_record, apply_comprehensive_stage_result, _record_hash
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico import comprehensive_same_run_locale_report_v1 as locale
    from nico import comprehensive_run_store as storage
    from nico import retained_pdf_exact_input_cache_v1 as cache
    status = _fixed_status(source_language)
    identity = status['reports']['json']['identity']
    record = create_comprehensive_run_record(**{k:identity[k] for k in
        ('run_id','repository','commit_sha','evidence_ledger_id','customer_id','project_id')},authorized=True,report_language=source_language)
    for stage in COMPREHENSIVE_STAGES:
        result = {'status':'complete','synthetic_fixture':True}
        if stage == 'final_comprehensive_report_generation': result['report_package'] = status['reports']
        record = apply_comprehensive_stage_result(record,stage_id=stage,result=result)
    record['stage_results']['owned_unrelated_evidence'] = {'text': 'owned retained fixture ' * 500_000}
    record['integrity_sha256'] = _record_hash(record)
    database=tmp_path/'installed.sqlite'
    store=ComprehensiveRunStore(lambda:sqlite3.connect(database));store.ensure_schema();store.create(record)
    controller=ComprehensiveApiController(ComprehensiveRunService(store,{}))
    app=FastAPI();app.state.comprehensive_api_controller=controller;locale.install_same_run_locale_report(app)
    endpoint=next(r.endpoint for r in app.routes if getattr(r,'path','')==locale.PDF_ROUTE)
    restores=[];renders=[]
    decoder=storage._decode_run_payload;builder=locale.build_same_run_locale_pdf_response
    def decode(payload):
        restores.append(True)
        return decoder(payload)
    def build(status,language):
        renders.append(True)
        return builder(status,language)
    monkeypatch.setattr(storage,'_decode_run_payload',decode)
    monkeypatch.setattr(locale,'build_same_run_locale_pdf_response',build)
    tickets=[]
    finish=cache.finish_retained_pdf
    def observe_finish(prepared, build):
        old=cache._live_policy(prepared.builder)
        result=finish(prepared,build)
        new=cache._live_policy(prepared.builder)
        differences=[(repr(a)[:150],repr(b)[:150]) for a,b in zip(old,new) if a!=b]
        tickets.append({'metadata':prepared.metadata is not None,'cached':prepared.cached is not None,
                        'stable':old==new,'differences':differences[:12]})
        return result
    monkeypatch.setattr(cache,'finish_retained_pdf',observe_finish)
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    first=endpoint(identity['run_id'],target_language)
    assert first.headers['x-nico-localized-artifact-requires-new-approval']=='true'
    assert first.headers['x-nico-localized-artifact-approval-invalidated']=='true'
    assert first.headers['x-nico-client-delivery-allowed']=='false'
    second=endpoint(identity['run_id'],target_language)
    assert first is not second
    assert second.body==first.body and dict(second.headers)==dict(first.headers)
    assert all(ticket['metadata'] for ticket in tickets)
    if tickets[0]['stable']:
        assert len(restores)==len(renders)==1
        assert tickets[1]['cached']
    else:
        # Installed startup rendering rebinds the live companion renderer. The
        # obsolete first policy cannot authorize reuse; the next stable render can.
        assert tickets[0]['differences']
        assert not tickets[1]['cached'] and tickets[1]['stable']
        assert len(restores)==len(renders)==2
        third=endpoint(identity['run_id'],target_language)
        assert third.body==second.body and dict(third.headers)==dict(second.headers)
        assert tickets[2]['cached'] and len(restores)==len(renders)==2
    print('INSTALLED_CACHE_DIAGNOSTIC', source_language, target_language, tickets, flush=True)
    assert len(first.body)<cache.MAX_RETAINED_BYTES
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
