"""Proof safety/structure tests only; real database execution belongs to CI."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('proof_script', ['postgres_review_pdf_preparation_proof.py', 'postgres_review_pdf_lifecycle_proof.py'])
@pytest.mark.parametrize('url', ['', 'postgresql://nico:nico@remote:5432/nico',
    'postgresql://nico:nico@127.0.0.1:5432/nico?host=remote',
    'postgresql://nico:nico@127.0.0.1:5432/nico?hostaddr=10.0.0.1',
    'postgresql://nico:nico@127.0.0.1:5432/nico#fragment'])
def test_proof_rejects_non_fixture_targets_without_connections(url, proof_script):
    script = '''
import runpy, sqlite3, psycopg
attempts = []
def deny(*args, **kwargs):
    attempts.append('connection')
    raise AssertionError('connection forbidden')
sqlite3.connect = psycopg.connect = deny
module = runpy.run_path(PROOF_SCRIPT)
try:
    module['existing_adapter']()
except ValueError as exc:
    assert str(exc) == 'explicit_loopback_ci_database_required'
else:
    raise AssertionError('unsafe target accepted')
assert not attempts
'''
    script = 'PROOF_SCRIPT=' + repr('scripts/'+proof_script) + '\n' + script
    env = dict(os.environ, NICO_TEST_DATABASE_URL=url, DATABASE_URL='synthetic-inherited-production-url')
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr[-1000:]


def test_existing_workflow_retains_proofs_and_uploads_new_evidence():
    workflow = Path('.github/workflows/postgres-restart-proof.yml').read_text()
    for script in ('postgres_restart_proof.py', 'postgres_intake_reservation_proof.py',
                   'postgres_scanner_artifact_proof.py', 'postgres_worker_job_proof.py',
                   'postgres_worker_protocol_proof.py', 'postgres_run_storage_capacity_proof.py',
                   'postgres_review_pdf_preparation_proof.py', 'postgres_review_pdf_lifecycle_proof.py'):
        assert script in workflow
    assert 'image: postgres:16-alpine' in workflow
    assert 'audit-results/postgres-review-pdf-preparation-proof.json' in workflow.split('path: |')[1]
    assert 'assert "postgresql://" not in json.dumps(review_pdf)' in workflow


def test_lifecycle_failure_writes_bounded_evidence_and_still_fails(tmp_path, monkeypatch):
    import json
    from scripts import postgres_review_pdf_lifecycle_proof as lifecycle
    def fail(progress):
        progress['phase'] = 'fresh_process_retrieve'
        progress['checks']['real_child_render'] = True
        raise RuntimeError('private payload or connection URL must not appear')
    monkeypatch.setattr(lifecycle, 'proof', fail)
    output = tmp_path/'failure.json'
    with pytest.raises(RuntimeError):
        lifecycle.write_proof(output)
    result = json.loads(output.read_text())
    assert result['status'] == 'failed'
    assert result['phase'] == 'fresh_process_retrieve'
    assert result['checks'] == {'real_child_render': True}
    assert result['error_type'] == 'RuntimeError'
    assert result['assessment_executed'] is False
    assert result['live_production_claim'] is False
    assert result['client_delivery_allowed'] is False
    assert 'private payload' not in output.read_text()


def test_lifecycle_fixture_renders_english_in_actual_isolated_child():
    """Exercise the CI fixture/child boundary without a database or assessment."""
    script = '''
from copy import deepcopy
from dataclasses import replace
from threading import Event
from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record, controller_for, SOURCE_LANGUAGE, TARGET_LANGUAGE
from tests.test_review_pdf_preparation_jobs_v1 import identity
from nico.review_pdf_preparation_worker_v1 import run_worker, validate_result
from nico.review_pdf_artifact_policy_v1 import artifact_mode, LOCALIZED
record = build_owned_record()
status = controller_for(None)._status_artifact_from_record(record)
assert status['report_language'] == SOURCE_LANGUAGE == 'es-MX'
assert TARGET_LANGUAGE == 'en'
assert artifact_mode(status, TARGET_LANGUAGE) == LOCALIZED
canonical = status['reports']['json']
i = replace(identity(), run_id=status['run_id'], repository=status['repository'],
    commit_sha=status['commit_sha'], customer_id=canonical['identity']['customer_id'],
    project_id=canonical['identity']['project_id'], source_revision=record['revision'],
    source_integrity_sha256=record['integrity_sha256'],
    canonical_truth_sha256=status['reports']['canonical_truth_sha256'],
    source_artifact_sha256=status['reports']['pdf_sha256'], language=TARGET_LANGUAGE)
before = deepcopy(status)
state = {}
result = run_worker(status, i, stop=Event(), heartbeat=lambda **kwargs: None, state=state, max_seconds=60)
pdf, digest = validate_result(result, i)
assert pdf.startswith(b'%PDF') and digest
assert result['validated_page_count'] > 0
assert result['headers']['x-nico-report-language'] == 'en'
assert result['headers']['x-nico-localized-artifact-requires-new-approval'] == 'true'
assert result['headers']['x-nico-client-delivery-allowed'] == 'false'
assert status == before
assert state['physical_worker_exit_confirmed'] is True
assert replace(i, language=SOURCE_LANGUAGE).job_id != i.job_id
print('real isolated English cross-locale child passed; source unchanged; approval/delivery blocked')
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr[-3000:]
    assert 'real isolated English cross-locale child passed' in result.stdout
