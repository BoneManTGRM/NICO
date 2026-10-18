"""Fail-closed proof harness checks. These do not execute real PostgreSQL."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import postgres_review_pdf_capacity_proof as proof
from tests.test_review_pdf_single_artifact_qualification import ledger
from tests.test_review_pdf_preparation_jobs_v1 import identity
from nico.review_pdf_preparation_jobs_v1 import PreparationConflict


@pytest.fixture
def ci_context(monkeypatch):
    values = {'GITHUB_ACTIONS':'true','CI':'true','GITHUB_WORKFLOW':'Postgres Restart Proof',
              'GITHUB_REPOSITORY':'BoneManTGRM/NICO','GITHUB_EVENT_NAME':'pull_request',
              'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
              'NICO_TEST_DATABASE_URL':proof.EXPECTED_TARGET}
    for key,value in values.items(): monkeypatch.setenv(key,value)
    return values


@pytest.mark.parametrize('event', ['pull_request', 'push', 'workflow_dispatch'])
def test_all_supported_workflow_events_preserve_explicit_context_guards(ci_context, monkeypatch, event):
    monkeypatch.setenv('GITHUB_EVENT_NAME', event)
    proof.require_context(True)
    with pytest.raises(ValueError, match='explicit_synthetic_ci_context_required'):
        proof.require_context(False)
    monkeypatch.setenv('NICO_TEST_DATABASE_URL', proof.EXPECTED_TARGET+'?hostaddr=10.0.0.1')
    with pytest.raises(ValueError, match='explicit_synthetic_ci_context_required'):
        proof.require_context(True)


@pytest.mark.parametrize('change', ['explicit','GITHUB_ACTIONS','CI','GITHUB_WORKFLOW',
    'GITHUB_REPOSITORY','GITHUB_EVENT_NAME','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT',
    'NICO_TEST_DATABASE_URL'])
def test_unsupported_context_rejected_before_connector_import_or_connection(ci_context,monkeypatch,change):
    import psycopg
    connect=Mock(side_effect=AssertionError('unexpected connection'))
    monkeypatch.setattr(psycopg,'connect',connect)
    if change!='explicit': monkeypatch.setenv(change,'unsupported-synthetic-value')
    with pytest.raises(ValueError,match='explicit_synthetic_ci_context_required'):
        proof.existing_jobs(change!='explicit')
    connect.assert_not_called()


@pytest.mark.parametrize('target', [
    '', 'postgresql://nico:nico@remote:5432/nico',
    proof.EXPECTED_TARGET+'?hostaddr=10.0.0.1', proof.EXPECTED_TARGET+'#fragment',
    proof.EXPECTED_TARGET.replace('nico:nico','other:other'),
    proof.EXPECTED_TARGET.replace('/nico','/production'),
])
def test_only_fixed_existing_ci_fixture_target_is_accepted(ci_context,monkeypatch,target):
    monkeypatch.setenv('NICO_TEST_DATABASE_URL',target)
    with pytest.raises(ValueError): proof.require_context(True)


def test_explicit_context_and_fixture_scope_are_required(ci_context):
    proof.require_context(True)
    with pytest.raises(ValueError): proof.validate_fixture(identity())
    synthetic=replace(identity(), customer_id='capacity-proof-unit',
        run_id='comprun_capacity_unit', repository='synthetic/capacity-proof',commit_sha='7'*40)
    proof.validate_fixture(synthetic)


def test_failure_preserves_completed_checks_without_sensitive_error_text(tmp_path,monkeypatch):
    def fail(progress,**kwargs):
        progress['phase']='negative_controls'
        progress['checks']['duplicate_admission_idempotent']=True
        progress['observations'].append({'synthetic_results':[{'rejected':True}]})
        raise RuntimeError('private connection URL must not appear')
    monkeypatch.setattr(proof,'proof',fail)
    output=tmp_path/'proof.json'
    with pytest.raises(RuntimeError,match='synthetic_capacity_proof_failed'):
        proof.write_proof(output,explicit=True)
    value=json.loads(output.read_text())
    assert value['status']=='failed' and value['phase']=='negative_controls'
    assert value['checks']=={'duplicate_admission_idempotent':True}
    assert value['observations']==[{'synthetic_results':[{'rejected':True}]}]
    assert value['assessment_executed'] is False
    assert value['live_production_claim'] is False
    assert 'private connection' not in output.read_text()


def test_rollback_controls_preserve_owned_fixture_without_deleting(ledger):
    i=identity();before=ledger.enqueue(i,preparation_authorized=True)
    with proof.rollback_fixture(ledger,i) as con:
        job=ledger._read(con,i);job['status']='cancelled';ledger._write(con,i,job)
        assert ledger._read(con,i)['status']=='cancelled'
    assert ledger.get(i)==before


@pytest.mark.parametrize('reason',['wrong_owner','expired','cancelled'])
def test_valid_pdf_late_publication_helper_uses_real_lease_fence(ledger,reason):
    i=identity();ledger.enqueue(i,preparation_authorized=True);lease=ledger.claim(i)
    with ledger._transaction(i) as con:
        job=ledger._read(con,i)
        if reason=='expired': job['lease_until_epoch']=0
        if reason=='cancelled': job['status']='cancelled';job['lease_id']=''
        ledger._write(con,i,job)
    before=ledger.get(i)
    with pytest.raises(PreparationConflict):
        proof.publish_candidate(ledger,i,'0'*32 if reason=='wrong_owner' else lease['lease_id'])
    assert ledger.get(i)==before and 'pdf_base64' not in before


def test_workflow_orders_capacity_before_queue_population_and_requires_evidence():
    text=Path('.github/workflows/postgres-restart-proof.yml').read_text()
    assert text.index('postgres_review_pdf_capacity_proof.py --synthetic-ci-proof') < text.index('run: python scripts/postgres_review_pdf_preparation_proof.py')
    assert text.count('image: postgres:16-alpine')==1
    assert 'audit-results/postgres-review-pdf-capacity-proof.json' in text.split('path: |')[1]
    assert 'assert set(capacity["checks"]) == set(REQUIRED_CHECKS) | set(POSITIVE_CHECKS)' in text
    assert 'assert capacity["successful_ready_publication_proven"] is True' in text
    assert 'review_pdf["commit_sha"] == capacity["commit_sha"]' in text
    assert 'if: always()' in text
    for word in ('CREATE DATABASE','DELETE FROM','TRUNCATE','DROP SCHEMA'):
        assert word not in Path('scripts/postgres_review_pdf_capacity_proof.py').read_text()


def test_count_control_does_not_confuse_unrelated_rejection_with_capacity(monkeypatch):
    from contextlib import contextmanager
    from dataclasses import asdict
    i=identity()
    fake=Mock()
    fake.get.return_value=dict(job_id=i.job_id,identity=asdict(i),status='queued',attempts=0,
                              qualification={'synthetic':'existing'})
    fake.adapter._jsonb=lambda value:value
    fake._write.side_effect=PreparationConflict('qualification_initial_reservation_required')
    @contextmanager
    def rollback(*args): yield Mock()
    monkeypatch.setattr(proof,'rollback_fixture',rollback)
    with pytest.raises(AssertionError): proof.check_storage_boundaries(fake,i,{})
    submitted=fake._write.call_args.args[2]
    assert 'qualification' not in submitted and submitted['attempts']==0


def test_workflow_embedded_verifier_is_syntactically_valid_and_capacity_is_not_skipped():
    import ast
    import yaml
    workflow=yaml.safe_load(Path('.github/workflows/postgres-restart-proof.yml').read_text())
    steps=workflow['jobs']['restart-proof']['steps']
    capacity=next(step for step in steps if step.get('name','').startswith('Prove one-artifact'))
    assert 'if' not in capacity and capacity['timeout-minutes']==4
    verification=next(step['run'] for step in steps if step.get('name')=='Verify evidence is bounded and passing')
    python=verification.split("python - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    ast.parse(python)


def test_occupied_namespace_fails_before_spawning_or_resetting(monkeypatch):
    from contextlib import contextmanager
    jobs=Mock()
    con=Mock();con.execute.return_value.fetchone.return_value={'db':'nico','owner':'nico','recovery':False}
    @contextmanager
    def transaction(*args): yield con
    jobs._transaction=transaction
    jobs._queue_ids.return_value=['reviewpdfprep_existing']
    monkeypatch.setattr(proof,'existing_jobs',lambda explicit:jobs)
    spawn=Mock(side_effect=AssertionError('must not spawn'))
    monkeypatch.setattr(proof,'spawn',spawn)
    with pytest.raises(AssertionError):
        proof.proof({'phase':'context','checks':{},'observations':[]},explicit=True)
    spawn.assert_not_called()
    jobs._write.assert_not_called()
    assert con.execute.call_count==1


@pytest.mark.parametrize('schema', ['public', 'capacity_positive_bad',
    'capacity_positive_'+'a'*32+',public', 'capacity_positive_'+'a'*32+';DROP SCHEMA public'])
def test_schema_rejected_before_adapter_or_ddl(ci_context, monkeypatch, schema):
    adapter = Mock(side_effect=AssertionError('must not access adapter'))
    monkeypatch.setattr(proof, 'existing_jobs', adapter)
    with pytest.raises(ValueError, match='owned_synthetic_schema_required'):
        proof.isolated_adapter(True, schema, create=True)
    adapter.assert_not_called()


@pytest.mark.parametrize('missing', ['explicit', 'GITHUB_ACTIONS', 'GITHUB_REPOSITORY', 'NICO_TEST_DATABASE_URL'])
def test_schema_creation_requires_full_ci_guards(ci_context, monkeypatch, missing):
    adapter = Mock(side_effect=AssertionError('must not access adapter'))
    monkeypatch.setattr(proof, 'existing_jobs', adapter)
    if missing != 'explicit': monkeypatch.setenv(missing, 'invalid')
    with pytest.raises(ValueError, match='explicit_synthetic_ci_context_required'):
        proof.isolated_adapter(missing != 'explicit', 'capacity_positive_'+'a'*32, create=True)
    adapter.assert_not_called()


def test_schema_adapter_keeps_actual_driver_and_pins_all_connections(ci_context, monkeypatch):
    from unittest.mock import MagicMock
    from nico.storage import PostgresAdapter
    from nico.postgres_timeout_patch import postgres_connect_kwargs
    from psycopg.rows import dict_row
    from types import SimpleNamespace
    schema = 'capacity_positive_'+'a'*32
    con = MagicMock()
    con.__enter__.return_value = con
    def execute(statement, parameters=None):
        text = statement if isinstance(statement,str) else statement.as_string()
        cursor = Mock()
        if text.startswith('SELECT current_database'):
            cursor.fetchone.return_value = {'db':'nico','owner':'nico','recovery':False}
        elif text.startswith('SELECT current_schema'):
            cursor.fetchone.return_value = {'name':schema}
        else: cursor.fetchone.return_value = {'name':parameters[0]} if parameters else {}
        return cursor
    con.execute.side_effect = execute
    driver = Mock();driver.connect.return_value = con
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter.database_url = proof.EXPECTED_TARGET
    adapter._psycopg = driver;adapter._dict_row = dict_row
    monkeypatch.setattr(proof, 'existing_jobs', lambda explicit:SimpleNamespace(adapter=adapter))
    isolated = proof.isolated_adapter(True, schema, create=True)
    statements = [args.args[0] for args in con.execute.call_args_list]
    ddl = [s.as_string() for s in statements if not isinstance(s,str)]
    assert ddl == ['CREATE SCHEMA "'+schema+'"'] + [
        f'CREATE TABLE "{schema}"."{table}" (LIKE public."{table}" INCLUDING ALL)'
        for table in proof.FIXTURE_TABLES]
    # Ledger dict-row and source-store tuple-row paths both use schema-pinned driver.
    isolated._connect()
    isolated._psycopg.connect(proof.EXPECTED_TARGET)
    calls = driver.connect.call_args_list
    assert calls[-2].kwargs['row_factory'] is dict_row
    assert 'row_factory' not in calls[-1].kwargs
    assert calls[-2].kwargs['options'] == postgres_connect_kwargs()['options']+' -csearch_path='+schema+',pg_catalog'
    assert calls[-1].kwargs['options'] == ' -csearch_path='+schema+',pg_catalog'
    count = driver.connect.call_count
    for kwargs in ({'options':'-csearch_path=public'},):
        with pytest.raises(ValueError): isolated._psycopg.connect(proof.EXPECTED_TARGET, **kwargs)
    with pytest.raises(ValueError): isolated._psycopg.connect('postgresql://other')
    assert driver.connect.call_count == count


def test_positive_reader_requires_context_before_import_or_adapter(monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS','false')
    adapter = Mock(side_effect=AssertionError('must not connect'))
    monkeypatch.setattr(proof,'isolated_adapter',adapter)
    with pytest.raises(ValueError): proof.positive_read({},explicit=True)
    adapter.assert_not_called()


def test_real_child_with_positive_proof_observers_releases_reservation_only_after_cleanup(tmp_path, monkeypatch):
    import sqlite3
    from threading import BoundedSemaphore
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record, controller_for
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.durable_runtime_storage import SQLiteRuntimeAdapter
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime, runtime_policy
    from nico.review_pdf_preparation_service_v1 import RetainedSourceAuthority, ReviewPdfPreparationService
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlySQLiteJobs, MAX_SERIALIZED_BYTES
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA','e'*40)
    path = tmp_path/'real-child.sqlite'
    store = ComprehensiveRunStore(lambda:sqlite3.connect(path))
    store.ensure_schema()
    persisted = store.create(build_owned_record())
    source = RetainedSourceAuthority(store, controller_for(store), runtime_policy)
    checks = {}
    jobs = proof.observed_jobs_class(QualificationOnlySQLiteJobs, checks)(SQLiteRuntimeAdapter(path))
    runtime = proof.observe_worker(PreparationRuntime(ReviewPdfPreparationService(
        jobs, source, capacity=BoundedSemaphore(1))), checks)
    try:
        status = source.controller._status_artifact_from_record(persisted)
        binding = dict(commit_sha=status['commit_sha'], canonical_truth_sha256=status['reports']['canonical_truth_sha256'])
        queued = runtime.prepare(status['run_id'],'es-MX',binding)
        from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
        renderer, policy = runtime_policy()
        ident = persisted['identity']
        i = PreparationIdentity(ident['customer_id'],ident['project_id'],ident['run_id'],ident['repository'],
            ident['commit_sha'],persisted['revision'],persisted['integrity_sha256'],binding['canonical_truth_sha256'],
            status['reports']['pdf_sha256'],renderer,policy,'es-MX','pending-source-localized-draft')
        assert queued['job_id'] == i.job_id
        before = source.capture(i)
        assert runtime.service.run_once(i)['status'] == 'ready'
        assert checks == {'real_child_rendered_with_occupancy_held':True,
            'occupancy_held_through_physical_cleanup':True,'cleanup_receipt_released_execution_only':True}
        retained = jobs.get(i)
        assert retained['qualification']['execution_state'] == 'released'
        assert retained['qualification']['reserved_bytes'] == MAX_SERIALIZED_BYTES
        from dataclasses import asdict
        from nico.review_pdf_preparation_worker_v1 import validate_result
        def validate_stored():
            stored = jobs.get(i)
            return validate_result(dict(identity=asdict(i),pdf_base64=stored['pdf_base64'],
                headers=stored['result_headers'],validated_page_count=stored['validated_page_count']),i)
        original = validate_stored()
        with pytest.raises(PreparationConflict,match='qualification_one_artifact_full'):
            jobs.enqueue(replace(i,language='en'),preparation_authorized=True)
        assert validate_stored() == original
        assert jobs.get(i) == retained
        assert store.load(i.run_id) == persisted and source.capture(i) == before
    finally:
        runtime.close()


@pytest.mark.parametrize('damage', [None, 'missing_positive_check', 'false_positive_check',
    'failed_publication', 'failed_status', 'private_url'])
def test_workflow_rejects_incomplete_positive_evidence(tmp_path, monkeypatch, damage):
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/postgres-restart-proof.yml').read_text())
    run = next(step['run'] for step in workflow['jobs']['restart-proof']['steps']
               if step.get('name') == 'Verify evidence is bounded and passing')
    block = run[run.index('capacity = json.loads'):run.index('review_pdf = json.loads')]
    value = dict(status='passed', synthetic=True, live_production_claim=False,
        assessment_executed=False, client_delivery_allowed=False, successful_ready_publication_proven=True,
        checks={name:True for name in (*proof.REQUIRED_CHECKS, *proof.POSITIVE_CHECKS)})
    if damage == 'missing_positive_check': value['checks'].pop('fresh_process_retrieved_exact_bytes')
    if damage == 'false_positive_check': value['checks']['cleanup_receipt_released_execution_only'] = False
    if damage == 'failed_publication': value['successful_ready_publication_proven'] = False
    if damage == 'failed_status': value['status'] = 'failed'
    if damage == 'private_url': value['extra'] = 'postgresql://must-not-be-in-evidence'
    (tmp_path/'audit-results').mkdir()
    (tmp_path/'audit-results/postgres-review-pdf-capacity-proof.json').write_text(json.dumps(value))
    monkeypatch.chdir(tmp_path)
    if damage is None:
        exec(compile(block, '<workflow-capacity-verifier>', 'exec'), {'json':json, 'Path':Path})
    else:
        with pytest.raises(AssertionError):
            exec(compile(block, '<workflow-capacity-verifier>', 'exec'), {'json':json, 'Path':Path})


def test_context_failure_evidence_reports_safe_code_location(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS','false')
    output = tmp_path/'failure.json'
    with pytest.raises(RuntimeError, match='synthetic_capacity_proof_failed'):
        proof.write_proof(output, explicit=True)
    value = json.loads(output.read_text())
    assert value['phase'] == 'context' and value['error_type'] == 'ValueError'
    assert value['checks'] == {}
    assert value['failure_site']['file'] == 'postgres_review_pdf_capacity_proof.py'
    assert value['failure_site']['function'] == 'require_context'
    assert type(value['failure_site']['line']) is int
    assert 'explicit_synthetic_ci_context_required' not in output.read_text()
