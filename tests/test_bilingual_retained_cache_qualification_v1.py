"""Real localized cache on disposable synthetic SQLite; no live assessment."""
import hashlib
import re
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI


@pytest.mark.parametrize('source_language,target_language', [('en','es-MX'),('es-MX','en')])
def test_bilingual_installed_cache_keeps_source_and_approval_within_request_budget(
    tmp_path, monkeypatch, record_property, source_language, target_language,
):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico.comprehensive_run_record import create_comprehensive_run_record, apply_comprehensive_stage_result, _record_hash
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico import comprehensive_same_run_locale_report_v1 as locale
    from nico import retained_pdf_exact_input_cache_v1 as cache
    status = _fixed_status(source_language)
    identity = status['reports']['json']['identity']
    record = create_comprehensive_run_record(**{k:identity[k] for k in
        ('run_id','repository','commit_sha','evidence_ledger_id','customer_id','project_id')},
        authorized=True,report_language=source_language)
    for stage in COMPREHENSIVE_STAGES:
        result = {'status':'complete','synthetic_fixture':True}
        if stage == 'final_comprehensive_report_generation': result['report_package'] = status['reports']
        record = apply_comprehensive_stage_result(record,stage_id=stage,result=result)
    from nico.comprehensive_run_storage_codec_v1 import COMPRESSION_THRESHOLD_BYTES
    # Exercise the real encoded-record cache predicate, without changing its threshold.
    record['stage_results']['owned_unrelated_evidence'] = {'text': 'x' * (COMPRESSION_THRESHOLD_BYTES + 1)}
    record['integrity_sha256'] = _record_hash(record)
    assert record['human_review_required'] is True
    database=tmp_path/'synthetic.sqlite'
    store=ComprehensiveRunStore(lambda:sqlite3.connect(database));store.ensure_schema();store.create(record)
    app=FastAPI()
    app.state.comprehensive_api_controller=ComprehensiveApiController(ComprehensiveRunService(store,{}))
    locale.install_same_run_locale_report(app)
    endpoint=next(r.endpoint for r in app.routes if getattr(r,'path','')==locale.PDF_ROUTE)
    # Explicit local test-only release admission. Integrity/cache/authorization unchanged.
    monkeypatch.setattr(locale,'require_new_report_language',lambda language: None)
    monkeypatch.setattr(locale,'require_available_projection',lambda status,language: None)
    renders=[];tickets=[]
    original_render=locale._render_target
    def render(*args,**kwargs):
        renders.append(True)
        return original_render(*args,**kwargs)
    monkeypatch.setattr(locale,'_render_target',render)
    original_finish=cache.finish_retained_pdf
    def finish(prepared,builder):
        tickets.append(prepared.cached is not None)
        return original_finish(prepared,builder)
    monkeypatch.setattr(cache,'finish_retained_pdf',finish)
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    proxy=(Path(__file__).resolve().parents[1]/'apps/web/app/api/nico/[...path]/route.ts').read_text()
    budget=int(re.search(r'const ARTIFACT_READ_TIMEOUT_MS = ([0-9_]+);',proxy)[1].replace('_',''))/1000
    observations=[];responses=[]
    # First render may legitimately rebind a live policy; next stable render must cache.
    for _ in range(3):
        start=time.monotonic()
        responses.append(endpoint(identity['run_id'],target_language))
        observations.append(round(time.monotonic()-start,4))
        assert observations[-1] < budget
    assert renders and len(renders)<=2
    assert tickets[-1] is True, 'third request must reuse the validated stable-policy artifact'
    assert all(r.body==responses[0].body and dict(r.headers)==dict(responses[0].headers) for r in responses)
    headers=responses[0].headers
    assert headers['x-nico-localized-artifact-requires-new-approval']=='true'
    assert headers['x-nico-localized-artifact-approval-invalidated']=='true'
    assert headers['x-nico-approval-status']=='pending_human_approval'
    assert headers['x-nico-delivery-status']=='blocked_pending_human_approval'
    assert headers['x-nico-client-delivery-allowed']=='false'
    assert headers['x-nico-canonical-truth-sha256']==status['reports']['canonical_truth_sha256']
    assert headers['x-nico-run-id']==identity['run_id']
    assert headers['x-nico-report-language']==target_language
    assert headers['x-nico-pdf-sha256']==hashlib.sha256(responses[0].body).hexdigest()
    assert hashlib.sha256(database.read_bytes()).hexdigest()==before
    record_property('request_elapsed_seconds',str(observations))
    record_property('existing_artifact_request_budget_seconds',budget)
