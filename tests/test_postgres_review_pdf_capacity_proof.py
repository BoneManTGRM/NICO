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
    assert 'assert set(capacity["checks"]) == set(REQUIRED_CHECKS)' in text
    assert 'review_pdf["commit_sha"] == capacity["commit_sha"]' in text
    assert 'if: always()' in text
    for word in ('CREATE TABLE','CREATE DATABASE','DELETE FROM','TRUNCATE'):
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
