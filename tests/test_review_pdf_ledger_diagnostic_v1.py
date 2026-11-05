"""Synthetic metadata/transaction seams; not real PostgreSQL qualification."""
from dataclasses import asdict
import json
import re
from threading import BoundedSemaphore, Event
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest

from nico import review_pdf_ledger_diagnostic_v1 as diagnostic
from nico.review_pdf_canary_scope_v1 import FIELDS
from nico.specialist_access_v1 import issue_specialist_session
from tests.test_review_pdf_preparation_api_v1 import client, path
from tests.test_review_pdf_preparation_jobs_v1 import identity


@pytest.fixture(autouse=True)
def disabled_scope(monkeypatch):
    monkeypatch.setenv('NICO_ENABLE_REVIEW_PDF_PREPARATION','false')
    monkeypatch.setenv('NICO_REVIEW_PDF_PG_QUALIFIED','false')
    monkeypatch.setenv('NICO_REVIEW_PDF_CANARY_SCOPE',json.dumps({k:v for k,v in asdict(identity()).items() if k in FIELDS}))


def row(**changes):
    value=dict(job_id=identity().job_id,state='queued',payload_matches=True,mismatches=[],
               renderer='e'*40,policy='f'*64,attempts=0,lease=False,expired=False)
    value.update(changes)
    return tuple(value.values())


class Connection:
    def __init__(self,rows=(),readonly=True,fail=None):
        self.info=SimpleNamespace(transaction_status=0)
        self.rows=list(rows);self.readonly=readonly;self.fail=fail
        self.commands=[];self.closed=False;self.rolled_back=False;self.fetch_limits=[]
    def execute(self,sql,params=None):
        self.commands.append((sql,params))
        if self.fail=='execute':raise RuntimeError('postgres://SECRET/customer')
        return self
    def cursor(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def fetchone(self):return (self.readonly,)
    def fetchmany(self,limit):self.fetch_limits.append(limit);return self.rows
    def rollback(self):
        self.rolled_back=True
        if self.fail=='rollback':raise RuntimeError('SECRET')
    def close(self):
        self.closed=True
        if self.fail=='close':raise RuntimeError('SECRET')


def fixture(connection=None):
    connection=connection or Connection()
    factory=Mock(return_value=connection)
    store=SimpleNamespace(_dialect='postgres',_connection_factory=factory)
    app=SimpleNamespace(state=SimpleNamespace(comprehensive_runtime={'configured':True,'persistence_adapter':'postgres'},
        comprehensive_api_controller=SimpleNamespace(_service=SimpleNamespace(_store=store))))
    return app,connection,factory


def read(app,run=None,language=None):
    return diagnostic.diagnose_ledger(app,run or identity().run_id,language or identity().language)


def test_complete_zero_is_only_after_successful_read_and_cleanup():
    app,con,factory=fixture()
    result=read(app)
    assert result['status']=='complete' and result['query_complete']
    assert result['scoped_rows_present'] is result['exact_source_row_present'] is False
    assert result['rows']==[] and result['rows_returned']==0
    assert con.rolled_back and con.closed
    assert con.fetch_limits==[33]
    factory.assert_called_once_with()
    assert [sql for sql,_ in con.commands[:4]]==['BEGIN READ ONLY',"SET LOCAL statement_timeout = '3s'",
        "SET LOCAL lock_timeout = '1s'","SET LOCAL idle_in_transaction_session_timeout = '5s'"]
    assert all(sql.lstrip().startswith(('BEGIN READ ONLY','SET LOCAL','SELECT')) for sql,_ in con.commands)
    sql,params=con.commands[-1]
    assert sql==diagnostic.QUERY
    assert json.loads(params[0])=={k:v for k,v in asdict(identity()).items() if k in FIELDS}
    assert params[1:]==(identity().customer_id,identity().project_id,diagnostic.WORKFLOW,identity().run_id,identity().language,33)
    where=sql.split('FROM client_jobs')[1]
    assert 'revision' not in where and 'policy' not in where and 'integrity' not in where
    assert 'JOIN' not in sql and 'FOR UPDATE' not in sql
    assert not re.search(r'SELECT\s+(?:\*|payload\s*(?:,|FROM))',sql)


def test_exact_and_obsolete_rows_are_distinct_without_current_source_join():
    rows=[row(),row(job_id='reviewpdfprep_'+'a'*64,mismatches=['source_revision','source_integrity_sha256'],
        renderer='b'*40,policy='c'*64,state='failed',attempts=1,expired=True)]
    result=read(fixture(Connection(rows))[0])
    assert result['exact_source_row_present'] is True and result['rows_returned']==2
    assert result['rows'][0]['source_binding_matches'] is True
    assert result['rows'][1]['source_binding_matches'] is False
    assert result['rows'][1]['binding_mismatches']==['source_integrity_sha256','source_revision']
    assert result['physical_worker_exit_confirmed'] is None
    assert result['activation_authorized'] is False


@pytest.mark.parametrize('count',[32,33])
def test_row_limit_never_turns_incomplete_read_into_absence(count):
    result=read(fixture(Connection([row(mismatches=['commit_sha']) for _ in range(count)]))[0])
    assert result['rows_returned']==32
    assert result['query_complete'] is (count==32)
    assert result['exact_source_row_present'] is (False if count==32 else None)
    assert result['status']==('complete' if count==32 else 'partial')
    assert len(json.dumps(result).encode())<=diagnostic.MAX_OUTPUT_BYTES


def test_matching_sentinel_proves_presence_but_not_complete_inventory():
    result=read(fixture(Connection([row(mismatches=['commit_sha'])]*32+[row()]))[0])
    assert result['exact_source_row_present'] is True
    assert result['query_complete'] is False
    assert len(result['rows'])==32


@pytest.mark.parametrize('key',['NICO_ENABLE_REVIEW_PDF_PREPARATION','NICO_REVIEW_PDF_PG_QUALIFIED'])
def test_enabled_preparation_refuses_diagnostic_connection(monkeypatch,key):
    monkeypatch.setenv(key,'true');app,_,factory=fixture()
    assert read(app)==diagnostic.unknown();factory.assert_not_called()


@pytest.mark.parametrize('scope',['','{}','null','{"run_id":"a","run_id":"b"}'])
def test_missing_or_malformed_configuration_never_connects(monkeypatch,scope):
    monkeypatch.setenv('NICO_REVIEW_PDF_CANARY_SCOPE',scope);app,_,factory=fixture()
    assert read(app)==diagnostic.unknown();factory.assert_not_called()


@pytest.mark.parametrize('run,language',[('comprun_foreign','es-MX'),(None,'en')])
def test_foreign_request_never_connects(run,language):
    app,_,factory=fixture()
    assert read(app,run,language)==diagnostic.unknown();factory.assert_not_called()


@pytest.mark.parametrize('change',[{'job_id':'SECRET'}, {'state':'SECRET'}, {'payload_matches':None},
    {'mismatches':['SECRET']},{'mismatches':['run_id','run_id']},{'renderer':'SECRET'},{'policy':'SECRET'},
    {'attempts':True},{'attempts':-1},{'lease':'SECRET'},{'expired':1}])
def test_malformed_metadata_never_returns_raw_values_or_partial_result(change):
    app,con,_=fixture(Connection([row(),row(**change)]))
    assert read(app)==diagnostic.unknown()
    assert con.closed and con.rolled_back


@pytest.mark.parametrize('failure',['execute','rollback','close'])
def test_storage_and_cleanup_failure_cannot_claim_completed_read(failure):
    app,con,_=fixture(Connection([row()],fail=failure))
    assert read(app)==diagnostic.unknown();assert con.closed


def test_non_readonly_or_borrowed_connection_rejected():
    app,con,_=fixture(Connection(readonly=False))
    assert read(app)==diagnostic.unknown();assert con.closed and con.rolled_back
    app,con,_=fixture();con.info.transaction_status=2
    assert read(app)==diagnostic.unknown();assert con.commands==[] and con.closed


def test_excess_rows_or_output_fail_closed(monkeypatch):
    assert read(fixture(Connection([row()]*34))[0])==diagnostic.unknown()
    monkeypatch.setattr(diagnostic,'MAX_OUTPUT_BYTES',1)
    assert read(fixture(Connection([row()]))[0])==diagnostic.unknown()


def test_timeout_holds_slot_until_physical_return(monkeypatch):
    from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
    slot=BoundedSemaphore(1);monkeypatch.setattr(diagnostic,'_SLOT',slot)
    monkeypatch.setattr(diagnostic,'DeadlineGuard',lambda seconds,stop:DeadlineGuard(.02,stop))
    release,done=Event(),Event()
    def blocked(*args):release.wait(2);done.set();return {'private':'SECRET'}
    monkeypatch.setattr(diagnostic,'inspect_ledger',blocked)
    assert read(object())==diagnostic.unknown()
    assert read(object())==diagnostic.unknown('busy')
    release.set();assert done.wait(1)
    until=time.monotonic()+1
    while time.monotonic()<until:
        if slot.acquire(blocking=False):break
        time.sleep(.01)
    else:pytest.fail('slot not released after physical return')


@pytest.mark.parametrize('authority',['missing','invalid','proof'])
def test_route_preserves_authentication(client,monkeypatch,authority):
    http,runtime,app=client;reader=Mock();monkeypatch.setattr(diagnostic,'diagnose_ledger',reader)
    headers={}
    if authority=='invalid':headers={'x-nico-admin-token':'invalid'}
    if authority=='proof':
        token,_=issue_specialist_session({'authority':'nico_admin'},scope='nico_production_proof',
            retained_claims={k:'synthetic' for k in ('repository','ref','sha','workflow_ref','run_id','run_attempt')})
        headers={'x-nico-operator-session':token}
    assert http.get(path()+'?canary_ledger=true',headers=headers).status_code in {401,403}
    reader.assert_not_called();assert runtime.mock_calls==[]


def test_route_works_disabled_with_signed_session(client,monkeypatch):
    http,runtime,app=client;app.state.review_pdf_runtime=None
    reader=Mock(return_value=diagnostic.unknown());monkeypatch.setattr(diagnostic,'diagnose_ledger',reader)
    token,_=issue_specialist_session({'authority':'nico_admin'})
    result=http.get(path()+'?canary_ledger=true',headers={'x-nico-operator-session':token})
    assert result.status_code==200 and result.json()==diagnostic.unknown()
    assert result.headers['cache-control']=='no-store, private, max-age=0'
    reader.assert_called_once_with(app,'comprun_fixture','es-MX');assert runtime.mock_calls==[]


@pytest.mark.parametrize('suffix,expected',[('/pdf?canary_ledger=true',422),('/cancel?canary_ledger=true',405),
    ('?canary_ledger=false',422),('?canary_ledger=true&extra=x',422),
    ('?canary_ledger=true&canary_ledger=true',422),('?canary_ledger=true&retained_binding=true',422)])
def test_route_rejects_ambiguous_or_mutating_forms(client,monkeypatch,suffix,expected):
    http,runtime,_=client;reader=Mock();monkeypatch.setattr(diagnostic,'diagnose_ledger',reader)
    assert http.get(path(suffix),headers={'x-nico-admin-token':'synthetic-admin-token'}).status_code==expected
    reader.assert_not_called();assert runtime.mock_calls==[]


def test_existing_hosted_synthetic_proof_exercises_real_query_without_new_workflow():
    from pathlib import Path
    source=Path('scripts/postgres_review_pdf_lifecycle_proof.py').read_text()
    workflow=Path('.github/workflows/postgres-restart-proof.yml').read_text()
    assert 'prove_readonly_ledger(runtime, identity)' in source
    assert 'readonly_ledger_current_obsolete_and_absent_verified' in source
    assert 'python scripts/postgres_review_pdf_lifecycle_proof.py --output' in workflow
    assert 'assert all(value is True for value in lifecycle["checks"].values())' in workflow


def test_hosted_proof_restores_configuration_on_failure(monkeypatch):
    from scripts.postgres_review_pdf_lifecycle_proof import prove_readonly_ledger
    monkeypatch.setenv('NICO_REVIEW_PDF_CANARY_SCOPE','synthetic-previous-config')
    runtime=Mock();runtime.source.store.load.return_value={};runtime.jobs.get.return_value={}
    monkeypatch.setattr(diagnostic,'diagnose_ledger',Mock(side_effect=RuntimeError('synthetic failure')))
    with pytest.raises(RuntimeError):prove_readonly_ledger(runtime,identity())
    import os
    assert os.environ['NICO_REVIEW_PDF_CANARY_SCOPE']=='synthetic-previous-config'
