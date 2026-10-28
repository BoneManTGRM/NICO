"""Safety controls for the real-Postgres proof; server execution belongs to CI."""
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys

import pytest

SCRIPT = Path('scripts/postgres_readonly_restore_proof.py')


def _load():
    spec = importlib.util.spec_from_file_location('readonly_proof_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('actions,url', [
    ('', 'postgresql://nico:nico@127.0.0.1:5432/nico'),
    ('true', ''),
    ('true', 'postgresql://user:SYNTHETIC_SECRET@production.example/nico'),
    ('true', 'postgresql://nico:nico@127.0.0.1:5432/other'),
    ('true', 'postgresql://nico:nico@127.0.0.1:5432/nico?host=remote'),
    ('true', 'postgresql://nico:nico@127.0.0.1:5432/nico#fragment'),
])
def test_wrong_fixture_or_non_ci_refused_before_any_connection(actions, url):
    code = '''import runpy, psycopg
calls=[]
def denied(*args, **kwargs):
 calls.append(True)
 raise AssertionError('connection forbidden')
psycopg.connect=denied
module=runpy.run_path('scripts/postgres_readonly_restore_proof.py')
try: module['fixture_connection']()
except ValueError as exc: assert str(exc)=='existing_synthetic_ci_fixture_required'
else: raise AssertionError('unsafe target accepted')
assert not calls
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            env=dict(os.environ, GITHUB_ACTIONS=actions, NICO_TEST_DATABASE_URL=url), timeout=15)
    assert result.returncode == 0, result.stderr
    assert not result.stdout and not result.stderr


def test_exact_fixture_uses_only_fixed_connection_parameters_and_clears_inherited_settings(monkeypatch):
    proof = _load()
    import psycopg
    sentinel = object()
    calls = []
    def connect(**kwargs):
        calls.append(kwargs)
        assert not any(key.startswith('PG') for key in os.environ)
        assert 'DATABASE_URL' not in os.environ
        return sentinel
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('NICO_TEST_DATABASE_URL', proof.FIXTURE_URL)
    monkeypatch.setenv('PGSERVICE', 'unrelated-profile')
    monkeypatch.setenv('PGHOST', 'remote.example')
    monkeypatch.setenv('DATABASE_URL', 'SYNTHETIC_SECRET')
    monkeypatch.setattr(psycopg, 'connect', connect)
    assert proof.fixture_connection() is sentinel
    assert calls == [dict(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
        user='nico', password='nico', dbname='nico', autocommit=True, connect_timeout=5,
        options='-c statement_timeout=3000 -c lock_timeout=1000')]


def test_import_bypasses_application_bootstrap_and_connections():
    code = '''import importlib.abc, runpy, sys, socket
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname == 'nico' or fullname.startswith('nico.') or fullname == 'psycopg':
   raise AssertionError('forbidden import')
sys.meta_path.insert(0, Block())
socket.socket.connect=lambda *a: (_ for _ in ()).throw(AssertionError('network forbidden'))
runpy.run_path('scripts/postgres_readonly_restore_proof.py')
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_failure_evidence_is_sanitized_and_never_claims_provenance(monkeypatch, tmp_path):
    proof = _load()
    def fail():
        raise RuntimeError('postgres://user:SYNTHETIC_SECRET@private/data')
    monkeypatch.setattr(proof, 'proof', fail)
    monkeypatch.setattr(proof, 'ROOT', tmp_path)
    assert proof.main() == 1
    text = (tmp_path/'audit-results/postgres-readonly-restore-proof.json').read_text()
    result = json.loads(text)
    assert result['status'] == 'failed'
    assert result['checks'] == {}
    assert result['restore_provenance_verified'] is False
    assert result['evidence_record_written'] is False
    assert 'SYNTHETIC_SECRET' not in text and 'postgres://' not in text


def test_workflow_reuses_existing_service_and_retains_proof_evidence():
    text = Path('.github/workflows/postgres-restart-proof.yml').read_text()
    assert text.count('image: postgres:16-alpine') == 1
    assert 'run: python scripts/postgres_readonly_restore_proof.py' in text
    assert 'audit-results/postgres-readonly-restore-proof.json' in text.split('path: |')[1]
    assert 'readonly["checks"][key] is True' in text


@pytest.mark.parametrize('value', [None, '', 0, 'a' * 63, 'a' * 65, 'g' * 64, 'A' * 64, 'a' * 63 + '\n'])
def test_success_requires_non_null_exact_hex_digest(value):
    with pytest.raises(AssertionError):
        _load()._assert_digest(value)


def test_valid_digest_is_accepted():
    _load()._assert_digest('0123456789abcdef' * 4)
