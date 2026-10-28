from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restore_verifier_under_test', ROOT / 'scripts/verify_restored_storage_readonly.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class Cursor:
    def __init__(self, rows):
        self.rows = rows
    def fetchmany(self, maximum):
        return self.rows[:maximum]
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class Connection:
    def __init__(self, *, missing_schema=False, missing_table=False, missing_column=False,
                 stale_ledger=False, failure=None, empty=False, bad_payload=False, large=False,
                 readonly='on', isolation='repeatable read', rollback_failure=False):
        self.info = SimpleNamespace(transaction_status=0)
        self.calls = []
        self.missing_schema = missing_schema
        self.missing_table = missing_table
        self.missing_column = missing_column
        self.stale_ledger = stale_ledger
        self.failure = failure
        self.empty = empty
        self.bad_payload = bad_payload
        self.large = large
        self.readonly = readonly
        self.isolation = isolation
        self.rollback_failure = rollback_failure

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if self.failure and self.failure in sql:
            raise RuntimeError('postgres://must-not-appear secret SQL row')
        contract = verifier._contract.storage_schema_contract()
        if sql.startswith('BEGIN'):
            self.info.transaction_status = 2
        elif sql == 'ROLLBACK':
            if self.rollback_failure:
                raise RuntimeError('secret rollback error')
            self.info.transaction_status = 0
        elif sql == 'SHOW transaction_read_only':
            return Cursor([(self.readonly,)])
        elif sql == 'SHOW transaction_isolation':
            return Cursor([(self.isolation,)])
        elif 'pg_namespace' in sql:
            return Cursor([(not self.missing_schema,)])
        elif 'information_schema.columns' in sql:
            rows = [(t, c) for t, columns in contract['tables'].items() for c in columns]
            if self.missing_table:
                rows = [(t,c) for t,c in rows if t != 'reports']
            if self.missing_column:
                rows = [(t,c) for t,c in rows if (t,c) != ('reports','payload')]
            return Cursor(rows)
        elif 'WHERE version' in sql:
            return Cursor([('0'*64 if self.stale_ledger else contract['contract_sha256'],)])
        elif sql.startswith('SELECT pg_catalog.left("'):
            table = sql.split(' FROM "public"."')[1].split('"')[0]
            columns = contract['tables'][table]
            fields = [columns[0], *(name for name in verifier._SAMPLE_FIELDS if name in columns and name != columns[0])]
            row = ['synthetic-private-value-' + field for field in fields]
            if self.large:
                row[0] = 'x' * 257
            if 'payload' in columns:
                row.append('array' if self.bad_payload else 'object')
            return Cursor([] if self.empty else [tuple(row)])
        return Cursor([])


def test_success_is_bounded_read_observation_not_restore_proof():
    connection = Connection()
    result = verifier.verify_connection(connection)
    assert result['status'] == 'verified_read_observation'
    assert result['required_tables_verified']
    assert result['migration_contract_verified']
    assert result['bounded_application_reads_verified']
    assert result['read_only_transaction_verified']
    assert result['transaction_rolled_back']
    assert result['restore_provenance_verified'] is False
    assert result['evidence_record_written'] is False
    assert len(result['record_set_sha256']) == 64
    assert len(result['table_samples']) == 13
    assert 'synthetic-private' not in json.dumps(result)
    sqls = [sql for sql, _ in connection.calls]
    assert sqls[0] == 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY'
    assert sqls[-1] == 'ROLLBACK'
    assert all(sql.startswith(('BEGIN ', 'SET LOCAL ', 'SHOW ', 'SELECT ')) or sql == 'ROLLBACK' for sql in sqls)
    assert not any(word in ' '.join(sqls).upper() for word in ('INSERT ', 'UPDATE ', 'CREATE ', 'DELETE ', 'COMMIT'))
    assert sqls.index('SHOW transaction_read_only') < next(i for i,s in enumerate(sqls) if s.startswith('SELECT'))
    samples = [(sql,params) for sql,params in connection.calls if sql.startswith('SELECT pg_catalog.left("')]
    assert all(' LIMIT %s' in sql and params == (3,) for sql,params in samples)
    assert all('jsonb_typeof("payload")' in sql or 'payload' not in sql for sql,_ in samples)


@pytest.mark.parametrize('kwargs,blocker', [
    ({'missing_schema':True}, 'required_schema_missing'),
    ({'missing_table':True}, 'required_tables_or_columns_missing'),
    ({'missing_column':True}, 'required_tables_or_columns_missing'),
    ({'stale_ledger':True}, 'migration_contract_missing_or_mismatched'),
    ({'readonly':'off'}, 'read_only_transaction_not_established'),
    ({'isolation':'read committed'}, 'repeatable_read_not_established'),
    ({'failure':'pg_namespace'}, 'verification_read_failed'),
    ({'failure':'SELECT pg_catalog.left("'}, 'verification_read_failed'),
    ({'empty':True}, 'application_sample_empty'),
    ({'bad_payload':True}, 'application_payload_not_object'),
    ({'large':True}, 'application_projection_limit_exceeded'),
    ({'rollback_failure':True}, 'transaction_rollback_failed'),
])
def test_negative_controls_fail_closed_without_digest_or_data(kwargs, blocker):
    connection = Connection(**kwargs)
    result = verifier.verify_connection(connection)
    assert result['status'] == 'blocked'
    assert blocker in result['blockers']
    assert result['record_set_sha256'] is None
    assert result['table_samples'] == []
    assert connection.calls[-1][0] == 'ROLLBACK'
    assert 'secret' not in json.dumps(result)
    assert 'postgres://' not in json.dumps(result)


@pytest.mark.parametrize('kwargs', [ {'schema':'public; DROP TABLE reports'}, {'sample_rows':0}, {'sample_rows':26}, {'sample_rows':True} ])
def test_invalid_arguments_do_not_touch_connection(kwargs):
    connection = Connection()
    assert verifier.verify_connection(connection, **kwargs)['status'] == 'blocked'
    assert connection.calls == []


def test_does_not_join_or_rollback_existing_transaction():
    connection = Connection()
    connection.info.transaction_status = 2
    assert verifier.verify_connection(connection)['blockers'] == ['idle_owned_connection_required']
    assert connection.calls == []


def test_sample_digest_stable_and_sensitive_to_projection():
    first = verifier.verify_connection(Connection())
    second = verifier.verify_connection(Connection())
    assert first['record_set_sha256'] == second['record_set_sha256']
    assert first['record_set_sha256'] != verifier.verify_connection(Connection(), sample_rows=4)['record_set_sha256']


def test_import_has_no_application_bootstrap_or_connection():
    code = '''import importlib.abc, runpy, sys, socket
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname == 'nico' or fullname.startswith('nico.') or fullname == 'psycopg':
   raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
socket.socket.connect=lambda *args: (_ for _ in ()).throw(AssertionError('network forbidden'))
runpy.run_path(sys.argv[1],run_name='read_only_import_test')
'''
    result = subprocess.run([sys.executable, '-c', code, str(ROOT/'scripts/verify_restored_storage_readonly.py')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_cli_uses_only_named_profile_with_readonly_startup_and_closes(monkeypatch, capsys):
    connection = Connection()
    closed = []
    connection.close = lambda: closed.append(True)
    observed = []
    def connect(**kwargs):
        observed.append(kwargs)
        return connection
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=connect))
    monkeypatch.setattr(sys, 'argv', ['verify', '--service', 'isolated_restore'])
    assert verifier.main() == 0
    assert closed == [True]
    assert observed[0]['service'] == 'isolated_restore'
    assert observed[0]['autocommit'] is True
    assert observed[0]['connect_timeout'] == 5
    assert 'default_transaction_read_only=on' in observed[0]['options']
    assert 'statement_timeout=3000' in observed[0]['options']
    assert set(observed[0]) == {'service','autocommit','connect_timeout','options'}
    assert json.loads(capsys.readouterr().out)['restore_provenance_verified'] is False


def test_cli_close_error_is_sanitized_and_blocks_digest(monkeypatch, capsys):
    connection = Connection()
    def close():
        raise RuntimeError('secret database address')
    connection.close = close
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda **kwargs:connection))
    monkeypatch.setattr(sys, 'argv', ['verify', '--service', 'isolated_restore'])
    assert verifier.main() == 1
    output = capsys.readouterr()
    assert not output.err
    assert 'secret' not in output.out
    assert json.loads(output.out)['record_set_sha256'] is None


def test_catalog_cap_blocks_before_sampling():
    connection = Connection()
    execute = connection.execute
    def overflow(sql, params=()):
        if 'information_schema.columns' in sql:
            connection.calls.append((sql,params))
            return Cursor([('reports','payload')]*257)
        return execute(sql,params)
    connection.execute = overflow
    result = verifier.verify_connection(connection)
    assert result['blockers'] == ['query_row_limit_exceeded']
    assert not any(sql.startswith('SELECT pg_catalog.left("') for sql,_ in connection.calls)


def test_missing_migration_row_does_not_create_or_repair_it():
    connection = Connection()
    execute = connection.execute
    def missing(sql, params=()):
        if 'WHERE version' in sql:
            connection.calls.append((sql,params))
            return Cursor([])
        return execute(sql,params)
    connection.execute = missing
    result = verifier.verify_connection(connection)
    assert result['blockers'] == ['migration_contract_missing_or_mismatched']
    assert result['record_set_sha256'] is None
    assert not any('INSERT' in sql or 'CREATE' in sql or 'UPDATE' in sql for sql,_ in connection.calls)


def test_changed_sample_changes_digest_without_exposing_value():
    before = verifier.verify_connection(Connection())
    connection = Connection()
    execute = connection.execute
    def changed(sql, params=()):
        cursor = execute(sql,params)
        if sql.startswith('SELECT pg_catalog.left("') and '"reports"' in sql:
            values = list(cursor.rows[0])
            values[0] = 'changed-private-report'
            cursor.rows = [tuple(values)]
        return cursor
    connection.execute = changed
    after = verifier.verify_connection(connection)
    assert after['status'] == 'verified_read_observation'
    assert after['record_set_sha256'] != before['record_set_sha256']
    assert 'changed-private-report' not in json.dumps(after)


@pytest.mark.parametrize('stored_hash', [None, '', '0' * 64, 'match_plus_suffix', 'oversized'])
def test_ledger_projection_is_sql_bounded_and_malformed_hashes_block(stored_hash):
    connection = Connection()
    execute = connection.execute
    expected = verifier._contract.storage_schema_contract()['contract_sha256']
    value = (expected + 'x' if stored_hash == 'match_plus_suffix' else
             'x' * 100000 if stored_hash == 'oversized' else stored_hash)
    def ledger(sql, params=()):
        if 'WHERE version' in sql:
            connection.calls.append((sql, params))
            # Assert the SQL projection itself: a client-side slice is too late
            # because psycopg may buffer the entire returned TEXT value.
            assert sql == ('SELECT pg_catalog.left(contract_sha256::text, 65) '
                           'FROM "public"."nico_schema_migrations" WHERE version = %s LIMIT 2')
            assert params == (verifier._contract.storage_schema_contract()['version'],)
            return Cursor([(None if value is None else value[:65],)])
        return execute(sql, params)
    connection.execute = ledger
    result = verifier.verify_connection(connection)
    assert result['blockers'] == ['migration_contract_missing_or_mismatched']
    assert result['record_set_sha256'] is None
    assert result['transaction_rolled_back']


@pytest.mark.parametrize('empty_table', ['assessment_runs', 'reports'])
def test_each_required_application_sample_must_be_nonempty(empty_table):
    connection = Connection()
    execute = connection.execute
    def sample(sql, params=()):
        cursor = execute(sql, params)
        if sql.startswith('SELECT pg_catalog.left("') and f'FROM "public"."{empty_table}"' in sql:
            return Cursor([])
        return cursor
    connection.execute = sample
    result = verifier.verify_connection(connection)
    assert result['blockers'] == ['application_sample_empty']
    assert result['bounded_application_reads_verified'] is False
    assert result['record_set_sha256'] is None
    assert result['table_samples'] == []
    assert result['restore_provenance_verified'] is False
    assert result['evidence_record_written'] is False


@pytest.mark.parametrize('args', [
    ['--service', 'isolated_restore', '--password', 'SYNTHETIC_SECRET'],
    ['--service', 'isolated_restore', '--sample-rows', 'SYNTHETIC_SECRET'],
    ['--service', 'isolated_restore', '--sample-rows', 'postgres://user:SYNTHETIC_SECRET@host/db'],
    ['--service', 'postgres://user:SYNTHETIC_SECRET@host/db'],
    ['--service', 'isolated_restore', '--schema', 'postgres://user:SYNTHETIC_SECRET@host/db'],
    [], ['--service'], ['--service', 'isolated_restore', '--sample-rows'],
    ['--service', 'isolated_restore', '--schema'],
    ['--service', 'isolated_restore', '--sample-rows', '26'],
])
def test_cli_argument_errors_are_sanitized_in_subprocess(args):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/verify_restored_storage_readonly.py'), *args],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert result.stderr == 'invalid_arguments\n'
    assert 'SYNTHETIC_SECRET' not in result.stdout + result.stderr
    assert 'postgres://' not in result.stdout + result.stderr
