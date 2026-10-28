"""Qualification-only, synthetic storage. Never enables the runtime queue."""
from dataclasses import replace
import pytest
from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
from tests.test_review_pdf_preparation_jobs_v1 import identity


def test_distinct_identity_is_rejected_after_one_admission(tmp_path):
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlySQLiteJobs
    jobs = QualificationOnlySQLiteJobs(SQLiteRuntimeAdapter(tmp_path/'owned.sqlite'))
    first = jobs.enqueue(identity(), preparation_authorized=True)
    assert jobs.enqueue(identity(), preparation_authorized=True) == first
    with pytest.raises(PreparationConflict):
        jobs.enqueue(replace(identity(), language='en'), preparation_authorized=True)

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore, Event, Thread
from unittest.mock import Mock

from nico.review_pdf_single_artifact_qualification_v1 import (
    QualificationOnlySQLiteJobs, QualificationOnlyPostgresJobs,
    MAX_SERIALIZED_BYTES, GLOBAL_LOCK_KEY, serialized_size,
)
from nico.review_pdf_preparation_jobs_v1 import ReviewPdfPreparationJobs
from nico.review_pdf_preparation_service_v1 import ReviewPdfPreparationService, CapturedSource
from nico.review_pdf_preparation_api_v1 import PreparationRuntime
from tests.test_review_pdf_preparation_service_v1 import artifact


@pytest.fixture
def ledger(tmp_path):
    jobs = QualificationOnlySQLiteJobs(SQLiteRuntimeAdapter(tmp_path/'owned.sqlite'))
    return jobs



CHILD = '''
import sys,json
from pathlib import Path
from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity,PreparationConflict
from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlySQLiteJobs
p=json.loads(sys.stdin.readline())
a=SQLiteRuntimeAdapter.__new__(SQLiteRuntimeAdapter); a.database_path=Path(p['path'])
jobs=QualificationOnlySQLiteJobs(a); i=PreparationIdentity(**p['identity'])
try:
 value=jobs.enqueue(i,preparation_authorized=True) if p['action']=='enqueue' else jobs.claim(i) if p['action']=='claim' else jobs.get(i)
 print(json.dumps({'value':value}))
except PreparationConflict:
 print(json.dumps({'rejected':True}))
'''


def independent_processes(ledger, identities, action):
    # No inherited database credentials, installed services, or network access needed.
    env = {'PATH': os.environ['PATH'], 'PYTHONPATH': str(Path.cwd()),
           'NICO_DISABLE_POSTGRES': 'true', 'NICO_ENABLE_SQLITE_DURABLE_STORAGE': 'false'}
    children = [subprocess.Popen([sys.executable, '-c', CHILD], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) for _ in identities]
    try:
        for child, ident in zip(children, identities):
            child.stdin.write(json.dumps({'path': str(ledger.adapter.database_path),
                                         'identity': asdict(ident), 'action': action})+'\n')
            child.stdin.close(); child.stdin = None
        results = []
        for child in children:
            out, err = child.communicate(timeout=15)
            assert child.returncode == 0, err[-1000:]
            results.append(json.loads(out))
        return results
    finally:
        for child in children:
            if child.poll() is None:
                child.kill(); child.wait(timeout=3)


def test_independent_process_distinct_admissions_and_same_identity_dedup(ledger):
    identities = [replace(identity(), project_id='fixture-'+str(n)) for n in range(4)]
    results = independent_processes(ledger, identities, 'enqueue')
    assert sum('value' in r for r in results) == 1
    winner = identities[next(n for n, r in enumerate(results) if 'value' in r)]
    original = ledger.get(winner)
    repeated = independent_processes(ledger, [winner]*4, 'enqueue')
    assert all(r['value'] == original for r in repeated)
    claims = independent_processes(ledger, [winner]*4, 'claim')
    assert sum(r.get('value') is not None for r in claims) == 1
    assert ledger.get(winner)['attempts'] == 1


@pytest.mark.parametrize('status', ['queued','rendering','ready','failed','cancelled','budget_exhausted','legacy_unknown'])
def test_all_legacy_statuses_consume_the_only_identity_without_modification(ledger, status):
    ordinary = ReviewPdfPreparationJobs(ledger.adapter)
    i = identity()
    ordinary.enqueue(i, preparation_authorized=True)
    with ordinary._transaction(i) as con:
        job = ordinary._read(con, i); job['status'] = status; ordinary._write(con, i, job)
    before = ordinary.get(i)
    assert ledger.enqueue(i, preparation_authorized=True) == before
    with pytest.raises(PreparationConflict):
        ledger.enqueue(replace(i, project_id='other'), preparation_authorized=True)
    with pytest.raises(PreparationConflict):
        ledger.claim(i)
    assert ordinary.get(i) == before


def test_malformed_reserved_namespace_and_legacy_workflow_ids_count(ledger):
    for key, payload in [('reviewpdfprep_legacy', 'not JSON'),
                         ('old-queue-identity', json.dumps({'workflow':'review_pdf_preparation.v0'}))]:
        # Separate disposable fixture stores; never clean up or evict rows to admit work.
        path = ledger.adapter.database_path.with_name(key+'.sqlite')
        other = QualificationOnlySQLiteJobs(SQLiteRuntimeAdapter(path))
        with other.adapter._connect() as con:
            con.execute("INSERT INTO nico_records VALUES('client_jobs',?,'fixture','fixture','0','0',?)", (key,payload))
        with pytest.raises(PreparationConflict, match='one_artifact_full'):
            other.enqueue(identity(), preparation_authorized=True)


def test_exact_66mib_logical_serialization_ceiling_and_rollback(ledger):
    i = identity(); ledger.enqueue(i, preparation_authorized=True)
    with ledger._transaction(i) as con:
        job = ledger._read(con, i)
        job['fixture_padding'] = ''
        # Use ASCII so one appended character means one serialized byte.
        job['fixture_padding'] = 'x'*(MAX_SERIALIZED_BYTES-serialized_size(job))
        assert serialized_size(job) == MAX_SERIALIZED_BYTES
        ledger._write(con, i, job)
    with pytest.raises(PreparationConflict, match='serialized_limit'):
        with ledger._transaction(i) as con:
            job = ledger._read(con, i); job['fixture_padding'] += 'x'
            ledger._write(con, i, job)
    retained = ledger.get(i)
    assert serialized_size(retained) == MAX_SERIALIZED_BYTES
    assert ledger.enqueue(i, preparation_authorized=True) == retained
    assert serialized_size({'text':'é'}) == len(json.dumps({'text':'é'},sort_keys=True).encode())


def test_expired_dead_owner_is_not_reclaimed_by_fresh_process(ledger):
    i=identity(); ledger.enqueue(i, preparation_authorized=True)
    claimed=independent_processes(ledger,[i],'claim')[0]['value']
    # Owner interpreter has exited; no cleanup receipt exists. Expiry is NOT exit proof.
    with ledger.adapter._connect() as con:
        job=ledger.get(i); job['lease_until_epoch']=0
        con.execute("UPDATE nico_records SET payload=? WHERE item_id=?",(json.dumps(job),i.job_id))
    assert independent_processes(ledger,[i],'claim') == [{'value':None}]
    assert ledger.get(i)['qualification']['execution_state']=='held'
    with pytest.raises(PreparationConflict,match='lease_not_owned'):
        ledger.record_rendered(i,claimed['lease_id'],observed_source=i,pdf_sha256='a'*64)
    assert ledger.get(i)['attempts']==1


def completed_state():
    return {'physical_worker_exit_confirmed':True,'temporary_files_cleanup_confirmed':True,
            'pending_guards':[]}


@pytest.mark.parametrize('missing', ['child','files','call','supervisor','owner'])
def test_cleanup_requires_physical_completion_and_same_owner(ledger, missing):
    i=identity(); ledger.enqueue(i,preparation_authorized=True); lease=ledger.claim(i)
    state=completed_state(); supervisor=None; owner=lease['lease_id']
    if missing=='child': state['physical_worker_exit_confirmed']=False
    if missing=='files': state['temporary_files_cleanup_confirmed']=False
    if missing=='call': state['pending_guards']=[Mock(idle=Mock(return_value=False))]
    if missing=='supervisor': supervisor=Mock(is_alive=Mock(return_value=True))
    if missing=='owner': owner='0'*32
    with pytest.raises(PreparationConflict):
        ledger.confirm_execution_exit(i,owner,state=state,supervisor=supervisor)
    assert ledger.get(i)['qualification']['execution_state']=='held'


def test_cancellation_fences_publication_but_never_frees_identity_or_occupancy(ledger,monkeypatch):
    i=identity(); ledger.enqueue(i,preparation_authorized=True); lease=ledger.claim(i)
    runtime=PreparationRuntime(Mock(jobs=ledger,source=Mock()))
    monkeypatch.setattr(runtime,'_job',lambda *a,**kw:(i,ledger.get(i)))
    runtime.cancel(i.run_id,i.language,i.job_id,{})
    assert ledger.get(i)['qualification']['execution_state']=='held'
    with pytest.raises(PreparationConflict): ledger.heartbeat(i,lease['lease_id'])
    with pytest.raises(PreparationConflict):
        ledger.record_rendered(i,lease['lease_id'],observed_source=i,pdf_sha256='a'*64)
    ledger.confirm_execution_exit(i,lease['lease_id'],state=completed_state(),supervisor=None)
    assert ledger.get(i)['status']=='cancelled'
    assert ledger.get(i)['qualification']['execution_state']=='released'
    assert ledger.claim(i) is None
    with pytest.raises(PreparationConflict): ledger.enqueue(replace(i,language='en'),preparation_authorized=True)


def make_service(ledger, worker=None):
    source=Mock()
    source.capture.side_effect=lambda _: CapturedSource({'synthetic':'unchanged'},'storage-proof')
    source.lock_and_recheck.return_value=None
    capacity=BoundedSemaphore(1)
    service=ReviewPdfPreparationService(ledger,source,capacity=capacity,
                                      worker=worker or Mock(return_value=artifact()))
    ledger.enqueue(identity(),preparation_authorized=True)
    return service,capacity


def test_service_ready_receipt_then_fresh_reader_preserves_exact_bytes(ledger,monkeypatch):
    i=identity(); service,capacity=make_service(ledger)
    ready=service.run_once(i)
    stored=ledger.get(i)
    assert ready['status']==stored['status']=='ready'
    assert stored['qualification']['execution_state']=='released'
    assert capacity.acquire(blocking=False)
    assert independent_processes(ledger,[i],'read')[0]['value']==stored
    runtime=PreparationRuntime(service)
    monkeypatch.setattr(runtime,'_job',lambda *a,**kw:(i,ledger.get(i)))
    # Use internal retrieval after capacity observation; authority/validation stays real.
    capacity.release()
    response=runtime.retrieve(i.run_id,i.language,i.job_id,{})
    assert response.headers['x-nico-pdf-sha256']==stored['pdf_sha256']
    assert response.headers['x-nico-client-delivery-allowed']=='false'
    assert ledger.enqueue(i,preparation_authorized=True)==stored
    assert service.run_once(i) is None
    with pytest.raises(PreparationConflict):
        ledger.enqueue(replace(i,project_id='other'),preparation_authorized=True)


@pytest.mark.parametrize('problem',['child_unconfirmed','receipt_failed'])
def test_service_cannot_release_capacity_on_unconfirmed_cleanup(ledger,monkeypatch,problem):
    def worker(status,i,**kwargs):
        if problem=='child_unconfirmed': kwargs['state']['physical_worker_exit_confirmed']=False
        return artifact()
    service,capacity=make_service(ledger,worker)
    if problem=='receipt_failed':
        monkeypatch.setattr(ledger,'confirm_execution_exit',Mock(side_effect=RuntimeError('synthetic storage outage')))
        service.run_once(identity())
    else:
        with pytest.raises(PreparationConflict): service.run_once(identity())
    assert ledger.get(identity())['qualification']['execution_state']=='held'
    assert not capacity.acquire(blocking=False)


def test_cancel_waits_for_actual_outstanding_call_and_private_cleanup(ledger,monkeypatch):
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    monkeypatch.setattr(DeadlineGuard,'HEARTBEAT_INTERVAL',.01)
    entered,finish_worker=Event(),Event(); observed={}; errors=[]
    def worker(status,i,**kwargs):
        state=kwargs['state']; observed['state']=state
        state['physical_worker_exit_confirmed']=False
        state['temporary_files_cleanup_confirmed']=False
        entered.set()
        assert finish_worker.wait(3)
        state['physical_worker_exit_confirmed']=True
        return artifact()
    service,capacity=make_service(ledger,worker)
    def invoke():
        try: service.run_once(identity())
        except BaseException as error: errors.append(error)
    thread=Thread(target=invoke,daemon=True);thread.start()
    try:
        assert entered.wait(1)
        runtime=PreparationRuntime(service)
        monkeypatch.setattr(runtime,'_job',lambda *a,**kw:(identity(),ledger.get(identity())))
        runtime.cancel(identity().run_id,identity().language,identity().job_id,{})
        thread.join(1)
        assert errors and not thread.is_alive()
        assert ledger.get(identity())['qualification']['execution_state']=='held'
        assert not capacity.acquire(blocking=False)
        assert independent_processes(ledger,[identity()],'claim')==[{'value':None}]
        finish_worker.set()
        # Temporary files remain unconfirmed even after the guarded call can exit.
        assert ledger.get(identity())['qualification']['execution_state']=='held'
        observed['state']['temporary_files_cleanup_confirmed']=True
        assert capacity.acquire(timeout=2)
        assert ledger.get(identity())['qualification']['execution_state']=='released'
        assert ledger.get(identity())['status']=='cancelled'
    finally:
        finish_worker.set()
        if 'state' in observed: observed['state']['temporary_files_cleanup_confirmed']=True
        thread.join(2)


def test_partial_admission_commit_is_recovered_idempotently_without_replacement(ledger):
    i=identity()
    class LostAcknowledgement:
        def begin_commit(self): pass
        def end_commit(self): raise RuntimeError('synthetic lost COMMIT acknowledgement')
    with pytest.raises(RuntimeError):
        ledger.enqueue(i,preparation_authorized=True,commit_guard=LostAcknowledgement())
    recovered=independent_processes(ledger,[i],'enqueue')[0]['value']
    assert recovered==ledger.get(i)
    assert recovered['attempts']==0
    with pytest.raises(PreparationConflict):
        ledger.enqueue(replace(i,language='en'),preparation_authorized=True)


def test_global_postgres_lock_precedes_identity_lock_without_connection_or_schema_setup():
    from nico.storage import PostgresAdapter
    import hashlib
    con=Mock(); con.execute.return_value.fetchall.return_value=[{'job_id':'reviewpdfprep_legacy'}]
    adapter=PostgresAdapter.__new__(PostgresAdapter)
    adapter._connect=Mock(return_value=con)
    jobs=QualificationOnlyPostgresJobs(adapter)
    adapter._connect.assert_not_called()
    with jobs._transaction(identity()):
        assert jobs._queue_ids(con)==['reviewpdfprep_legacy']
    calls=[call.args for call in con.execute.call_args_list]
    expected_identity=int.from_bytes(hashlib.sha256(identity().job_id.encode()).digest()[:8],'big',signed=True)
    assert calls[3]==('SELECT pg_advisory_xact_lock(%s)',(GLOBAL_LOCK_KEY,))
    assert calls[4]==('SELECT pg_advisory_xact_lock(%s)',(expected_identity,))
    assert 'status' not in calls[5][0] and 'LIMIT 2' in calls[5][0]
    assert not any('CREATE ' in call[0] or 'ALTER ' in call[0] or 'DELETE ' in call[0] for call in calls)
    con.commit.assert_called_once();con.close.assert_called_once()


def test_global_lock_failure_never_takes_identity_lock():
    from nico.storage import PostgresAdapter
    con=Mock()
    def execute(sql,*args):
        if sql=='SELECT pg_advisory_xact_lock(%s)': raise TimeoutError('synthetic lock timeout')
    con.execute.side_effect=execute
    adapter=PostgresAdapter.__new__(PostgresAdapter);adapter._connect=lambda:con
    with pytest.raises(TimeoutError):
        with QualificationOnlyPostgresJobs(adapter)._transaction(identity()):
            pytest.fail('lock failure entered transaction body')
    assert con.execute.call_count==4
    con.rollback.assert_called_once();con.close.assert_called_once();con.commit.assert_not_called()


def test_ordinary_classes_remain_without_qualification_limits(tmp_path):
    jobs=ReviewPdfPreparationJobs(SQLiteRuntimeAdapter(tmp_path/'ordinary-fixture.sqlite'))
    for i in (identity(),replace(identity(),language='en')):
        assert 'qualification' not in jobs.enqueue(i,preparation_authorized=True)
    assert not hasattr(jobs,'confirm_execution_exit')
    # Runtime wiring remains the original class, with no environment enablement.
    import inspect
    from nico.review_pdf_preparation_api_v1 import _configured_runtime
    assert 'QualificationOnly' not in inspect.getsource(_configured_runtime)


def test_real_child_prototype_releases_only_after_source_preserving_render(tmp_path,monkeypatch):
    from tests import test_review_pdf_real_source_lifecycle as real
    constructed=[]
    class ObservedFixtureLedger(QualificationOnlySQLiteJobs):
        def __init__(self,adapter):
            super().__init__(adapter);constructed.append(self)
        def confirm_execution_exit(self,*args,**kwargs):
            assert kwargs['state']['physical_worker_exit_confirmed'] is True
            assert kwargs['state']['temporary_files_cleanup_confirmed'] is True
            assert all(guard.idle() for guard in kwargs['state']['pending_guards'])
            return super().confirm_execution_exit(*args,**kwargs)
    monkeypatch.setattr(real,'ReviewPdfPreparationJobs',ObservedFixtureLedger)
    real.test_real_owned_record_restores_and_child_publishes_without_an_assessment(tmp_path,monkeypatch,'es-MX')
    jobs=constructed[0]
    with jobs.adapter._connect() as con:
        rows=con.execute("SELECT payload FROM nico_records WHERE table_name='client_jobs'").fetchall()
    assert len(rows)==1
    job=json.loads(rows[0]['payload'])
    assert job['status']=='ready' and job['qualification']['execution_state']=='released'
    assert job['client_delivery_allowed'] is False


def test_lease_and_absolute_expiry_do_not_release_execution_occupancy(ledger,monkeypatch):
    ticks=[1000.];monkeypatch.setattr(ledger,'_now',lambda _:ticks[0])
    i=identity();ledger.enqueue(i,preparation_authorized=True);lease=ledger.claim(i)
    ticks[0]=2000.
    assert ledger.claim(i) is None
    with pytest.raises(PreparationConflict):ledger.heartbeat(i,lease['lease_id'])
    assert ledger.get(i)['qualification']['execution_state']=='held'
    ledger.confirm_execution_exit(i,lease['lease_id'],state=completed_state(),supervisor=None)
    assert ledger.get(i)['qualification']['execution_state']=='released'
    assert ledger.get(i)['status']=='rendering'  # Receipt is NOT a lifecycle/lease override.
    assert ledger.claim(i) is None
    with pytest.raises(PreparationConflict):
        ledger.record_rendered(i,lease['lease_id'],observed_source=i,pdf_sha256='a'*64)


def test_ready_oversize_cannot_be_committed_and_existing_row_is_unchanged(ledger):
    i=identity();ledger.enqueue(i,preparation_authorized=True);ledger.claim(i)
    before=ledger.get(i)
    with pytest.raises(PreparationConflict,match='serialized_limit'):
        with ledger._transaction(i) as con:
            job=ledger._read(con,i)
            job.update(status='ready',pdf_base64='x'*MAX_SERIALIZED_BYTES)
            ledger._write(con,i,job)
    assert ledger.get(i)==before


def test_execution_marker_cannot_be_replaced_or_reset(ledger):
    i=identity();ledger.enqueue(i,preparation_authorized=True);lease=ledger.claim(i)
    before=ledger.get(i)
    for replacement in ('0'*32,''):
        with pytest.raises(PreparationConflict):
            with ledger._transaction(i) as con:
                job=ledger._read(con,i)
                job['qualification']['execution_owner']=replacement
                ledger._write(con,i,job)
        assert ledger.get(i)==before
    ledger.confirm_execution_exit(i,lease['lease_id'],state=completed_state(),supervisor=None)
    with pytest.raises(PreparationConflict,match='transition_invalid'):
        with ledger._transaction(i) as con:
            job=ledger._read(con,i);job['qualification']['execution_state']='held'
            ledger._write(con,i,job)


def test_postgres_namespace_query_uses_valid_psycopg_parameters():
    from psycopg._queries import PostgresQuery
    from psycopg.adapt import Transformer
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlyPostgresJobs
    con = Mock()
    con.execute.return_value.fetchall.return_value = [{'job_id': 'reviewpdfprep_existing'}]
    from nico.storage import PostgresAdapter
    jobs = QualificationOnlyPostgresJobs(PostgresAdapter.__new__(PostgresAdapter))
    assert jobs._queue_ids(con) == ['reviewpdfprep_existing']
    sql, parameters = con.execute.call_args.args
    query = PostgresQuery(Transformer())
    # Real psycopg parsing/adaptation, without a database or mocked parser.
    query.convert(sql, parameters)
    assert b'LIMIT 2' in query.query
    assert b'review_pdf_preparation.%' in query.params
