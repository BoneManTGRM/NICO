"""Synthetic configuration only: never enables a production worker."""
from dataclasses import asdict, replace
import json
from unittest.mock import MagicMock, Mock

import pytest
from fastapi import FastAPI
from nico.review_pdf_canary_scope_v1 import CanaryScope, FIELDS
from nico import review_pdf_preparation_api_v1 as api
from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
from tests.test_review_pdf_preparation_jobs_v1 import identity


def value():
    return {k:v for k,v in asdict(identity()).items() if k in FIELDS}


@pytest.mark.parametrize('raw', ['', '{}', 'null', '[]', 'true', 'x'*16385,
    '{"run_id":"a","run_id":"b"}'])
def test_invalid_configuration_fails_closed_before_storage(raw, monkeypatch):
    monkeypatch.setenv('NICO_ENABLE_REVIEW_PDF_PREPARATION', 'true')
    monkeypatch.setenv('NICO_REVIEW_PDF_PG_QUALIFIED', 'true')
    monkeypatch.setenv('NICO_REVIEW_PDF_CANARY_SCOPE', raw)
    app = FastAPI()
    with pytest.raises((ValueError, TypeError)):
        api._configured_runtime(app)
    assert not hasattr(app.state, 'comprehensive_api_controller')


@pytest.mark.parametrize('field', sorted(FIELDS))
def test_every_source_field_is_bound_and_configuration_is_copied(field):
    config = value()
    scope = CanaryScope(config)
    config[field] = 'foreign'
    scope.check(identity())
    changed = asdict(identity())
    changed[field] = 2 if field == 'source_revision' else (
        'en' if field == 'language' else 'f'*len(changed[field]))
    with pytest.raises(PreparationConflict):
        scope.check(replace(identity(), **{field:changed[field]}))


@pytest.mark.parametrize('change', [{'extra':'unsupported'}, {'source_revision':True},
    {'language':'fr'}, {'commit_sha':'bad'}, {'run_id':'../bad'}, {'customer_id':''}])
def test_unsupported_scope_rejected(change):
    with pytest.raises((TypeError, ValueError)):
        CanaryScope(value() | change)


def test_missing_field_rejected():
    config = value(); config.pop('source_artifact_sha256')
    with pytest.raises(ValueError): CanaryScope(config)


@pytest.mark.parametrize('operation', ['prepare', 'qualify', 'lookup', 'status', 'retrieve', 'cancel'])
def test_foreign_request_rejected_without_source_or_ledger_read(operation):
    service = MagicMock()
    runtime = api.PreparationRuntime(service, canary_scope=CanaryScope(value()))
    binding = {k:getattr(identity(), k) for k in ('commit_sha','canonical_truth_sha256')}
    args = ('comprun_foreign', identity().language)
    if operation in {'status','retrieve','cancel'}: args += (identity().job_id,)
    with pytest.raises(PreparationConflict): getattr(runtime, operation)(*args, binding)
    service.source.policy.assert_not_called()
    service.source.store._consume_read_snapshot.assert_not_called()
    service.jobs.adapter._connect.assert_not_called()
    service.jobs.enqueue.assert_not_called()


def test_recovery_skips_other_valid_jobs_and_malformed_rows():
    service = MagicMock()
    rows = [dict(job_id='a', identity={}),
        dict(job_id='b', identity=asdict(replace(identity(), run_id='comprun_other'))),
        dict(job_id='c', identity=asdict(identity()))]
    service.jobs.adapter._connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = rows
    runtime = api.PreparationRuntime(service, canary_scope=CanaryScope.parse(json.dumps(value())))
    runtime.stop.wait = lambda seconds: runtime.stop.set()
    runtime._recover()
    service.run_once.assert_called_once_with(identity(), stop=runtime.stop)
    service.source.check_policy.assert_called_once_with(identity())


def test_cancel_projection_never_claims_physical_exit():
    row = dict(job_id=identity().job_id, identity=asdict(identity()), status='cancelled')
    result = api.PreparationRuntime.projection(row)
    assert result['state'] == 'cancelled'
    assert result['physical_worker_exit_confirmed'] is None
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False


def test_full_source_identity_check_runs_before_enqueue(monkeypatch):
    from nico import comprehensive_same_run_locale_report_v1 as locale
    service = MagicMock()
    i = identity()
    source = service.source
    source.policy.return_value = i.renderer_revision, i.policy_sha256
    record = dict(identity={k:getattr(i,k) for k in ('customer_id','project_id','repository','commit_sha')},
                  terminal=True, revision=i.source_revision+1, integrity_sha256=i.source_integrity_sha256)
    source.controller._status_artifact_from_record.return_value = {'reports':{
        'canonical_truth_sha256':i.canonical_truth_sha256,'pdf_sha256':i.source_artifact_sha256}}
    source.store._consume_read_snapshot.side_effect = lambda run, consume: consume([None,1,'chain'],lambda:record)
    monkeypatch.setattr(locale, '_source_lifecycle_projection', lambda *a: {
        'approval_status':'pending_human_approval','client_delivery_allowed':False})
    monkeypatch.setattr(api, 'artifact_mode', lambda *a:i.artifact_mode)
    runtime = api.PreparationRuntime(service, canary_scope=CanaryScope(value()))
    with pytest.raises(PreparationConflict):
        runtime.prepare(i.run_id,i.language,{k:getattr(i,k) for k in ('commit_sha','canonical_truth_sha256')})
    service.jobs.enqueue.assert_not_called()


def test_cancellation_timeout_retains_read_slot_until_late_read_finishes(monkeypatch):
    from threading import Event, Thread, BoundedSemaphore
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    import time
    service = MagicMock()
    runtime = api.PreparationRuntime(service, canary_scope=CanaryScope(value()))
    entered, release = Event(), Event()
    clock = [10.]
    monkeypatch.setattr(api, 'DeadlineGuard', lambda seconds, stop: DeadlineGuard(seconds,stop,clock=lambda:clock[0]))
    def slow(*a,**kw):
        entered.set(); release.wait(3); return identity(), {}
    runtime._job = slow
    errors=[]
    def call():
        try: runtime.cancel(identity().run_id,identity().language,identity().job_id,{})
        except BaseException as error: errors.append(error)
    thread=Thread(target=call);thread.start();assert entered.wait(1)
    clock[0]=16.;thread.join(2)
    assert errors and not thread.is_alive()
    assert not runtime.read_slot.acquire(blocking=False)
    service.jobs._transaction.assert_not_called()
    release.set()
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if runtime.read_slot.acquire(blocking=False): break
        time.sleep(.01)
    else: pytest.fail('read capacity remained quarantined after physical completion')
