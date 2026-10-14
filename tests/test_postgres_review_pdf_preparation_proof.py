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
