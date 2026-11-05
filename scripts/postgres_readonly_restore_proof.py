"""Qualify the verifier only on the existing synthetic PostgreSQL CI service."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / 'scripts/verify_restored_storage_readonly.py'
spec = importlib.util.spec_from_file_location('readonly_restore_verifier', VERIFIER)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
FIXTURE_URL = 'postgresql://nico:nico@127.0.0.1:5432/nico'


def fixture_connection():
    # This is a synthetic test writer, never a general-purpose database tool.
    # Refuse every target except the already configured workflow service.
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('NICO_TEST_DATABASE_URL') != FIXTURE_URL:
        raise ValueError('existing_synthetic_ci_fixture_required')
    for key in tuple(os.environ):
        if key.startswith('PG') or key in {'DATABASE_URL', 'DATABASE_PRIVATE_URL',
                'POSTGRES_URL', 'POSTGRES_PRIVATE_URL', 'RAILWAY_DATABASE_URL', 'RAILWAY_POSTGRES_URL'}:
            os.environ.pop(key)
    import psycopg
    return psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
        user='nico', password='nico', dbname='nico', autocommit=True, connect_timeout=5,
        options='-c statement_timeout=3000 -c lock_timeout=1000')


def _snapshot(connection, schema):
    """Fixture table/column names, column types and rows; not all schema objects."""
    columns = connection.execute('''SELECT table_name, column_name, data_type
        FROM information_schema.columns WHERE table_schema = %s
        ORDER BY table_name, ordinal_position''', (schema,)).fetchall()
    tables = sorted({row[0] for row in columns})
    rows = {}
    for table in tables:
        if not verifier._IDENTIFIER.fullmatch(table):
            raise AssertionError('unexpected_fixture_relation')
        rows[table] = connection.execute(
            f'SELECT pg_catalog.to_jsonb(t)::text FROM "{schema}"."{table}" AS t ORDER BY 1').fetchall()
    return columns, rows


def _seed(connection, schema):
    contract = verifier._contract.storage_schema_contract()
    with connection.transaction():
        connection.execute(f'CREATE SCHEMA "{schema}"')
        for table, columns in contract['tables'].items():
            definitions = []
            for column in columns:
                kind = 'jsonb' if column == 'payload' else 'text'
                definitions.append(f'"{column}" {kind}' + (' PRIMARY KEY' if column == columns[0] else ''))
            connection.execute(f'CREATE TABLE "{schema}"."{table}" ({", ".join(definitions)})')
            if table == contract['migration_table']:
                connection.execute(f'INSERT INTO "{schema}"."{table}" (version, contract_sha256) VALUES (%s, %s)',
                                   (contract['version'], contract['contract_sha256']))
            elif 'payload' in columns:
                connection.execute(f'INSERT INTO "{schema}"."{table}" ("{columns[0]}", payload) VALUES (%s, %s::jsonb)',
                                   ('synthetic-id', '{"synthetic":true}'))
            else:
                connection.execute(f'INSERT INTO "{schema}"."{table}" ("{columns[0]}") VALUES (%s)', ('synthetic-id',))


class _WriteAttempt:
    """Attempt a write inside the verifier's actual transaction, then recover."""
    def __init__(self, connection, schema):
        self.connection, self.schema, self.blocked = connection, schema, False
    @property
    def info(self):
        return self.connection.info
    def execute(self, sql, params=()):
        if sql.startswith('SELECT pg_catalog.left("') and not self.blocked:
            import psycopg
            self.connection.execute('SAVEPOINT readonly_write_probe')
            try:
                self.connection.execute(f'INSERT INTO "{self.schema}"."customers" (customer_id) VALUES (%s)',
                                        ('forbidden-write',))
            except psycopg.errors.ReadOnlySqlTransaction:
                self.blocked = True
            finally:
                self.connection.execute('ROLLBACK TO SAVEPOINT readonly_write_probe')
                self.connection.execute('RELEASE SAVEPOINT readonly_write_probe')
            if not self.blocked:
                raise AssertionError('server_did_not_enforce_readonly')
        return self.connection.execute(sql, params)


def _assert_digest(digest):
    assert type(digest) is str and re.fullmatch(r'[0-9a-f]{64}', digest) is not None


def proof():
    checks = {}
    schema = 'readonly_proof_' + uuid4().hex
    with fixture_connection() as connection:
        try:
            _seed(connection, schema)
            def observe(name, *, target=None, blocker=None, wrapped=None):
                before = _snapshot(connection, schema)
                result = verifier.verify_connection(wrapped or connection, schema=target or schema)
                assert connection.info.transaction_status == 0
                assert result['transaction_rolled_back'] is True
                assert result['restore_provenance_verified'] is False
                assert result['evidence_record_written'] is False
                assert _snapshot(connection, schema) == before
                if blocker:
                    assert result['status'] == 'blocked'
                    assert result['blockers'] == [blocker]
                    assert result['record_set_sha256'] is None
                    assert result['table_samples'] == []
                else:
                    assert result['status'] == 'verified_read_observation'
                    assert result['bounded_application_reads_verified'] is True
                    assert result['required_tables_verified'] is True
                    assert result['migration_contract_verified'] is True
                    assert result['read_only_transaction_verified'] is True
                    assert len(result['table_samples']) == 13
                    _assert_digest(result['record_set_sha256'])
                checks[name] = True
                checks[name + '_contents_unchanged'] = True
                return result
            first = observe('bounded_reads')
            second = observe('repeat_reads')
            assert first['record_set_sha256'] == second['record_set_sha256']
            checks['stable_digest'] = True
            observe('missing_schema', target=schema + '_missing', blocker='required_schema_missing')
            connection.execute(f'ALTER TABLE "{schema}".reports RENAME TO reports_missing')
            observe('missing_table', blocker='required_tables_or_columns_missing')
            connection.execute(f'ALTER TABLE "{schema}".reports_missing RENAME TO reports')
            expected = verifier._contract.storage_schema_contract()['contract_sha256']
            for name, value in [('ledger_mismatch', '0' * 64), ('ledger_overlong', expected + 'x' * 100000)]:
                connection.execute(f'UPDATE "{schema}".nico_schema_migrations SET contract_sha256 = %s', (value,))
                observe(name, blocker='migration_contract_missing_or_mismatched')
            connection.execute(f'UPDATE "{schema}".nico_schema_migrations SET contract_sha256 = %s', (expected,))
            wrapped = _WriteAttempt(connection, schema)
            observe('server_readonly_enforcement', wrapped=wrapped)
            assert wrapped.blocked
            checks['write_rejected_by_postgres'] = True
        finally:
            # Cleanup is limited to this invocation's generated synthetic schema.
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        assert connection.execute('SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s', (schema,)).fetchone() is None
        checks['synthetic_schema_removed'] = True
    return checks


def main():
    output = ROOT / 'audit-results/postgres-readonly-restore-proof.json'
    result = {'status': 'failed', 'synthetic': True, 'live_production_claim': False,
              'restore_provenance_verified': False, 'evidence_record_written': False,
              'commit_sha': os.environ.get('GITHUB_SHA', ''),
              'verifier_sha256': hashlib.sha256(VERIFIER.read_bytes()).hexdigest(), 'checks': {}}
    try:
        result['checks'] = proof()
        result['status'] = 'passed'
    except Exception:
        result['error'] = 'synthetic_postgres_proof_failed'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True) + '\n')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
