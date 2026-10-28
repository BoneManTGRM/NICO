#!/usr/bin/env python3
"""Observe a restored Postgres target without initializing NICO or writing evidence.

The caller supplies an idle connection owned exclusively by this verifier. The CLI
uses an existing libpq service profile; no URLs/passwords are accepted or printed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Importing nico normally executes its application bootstrap. Load only the pure
# contract module by filename, never storage, adapters, readiness or application.
_CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'nico' / 'storage_schema_contract_v1.py'
_spec = importlib.util.spec_from_file_location('_restore_storage_contract', _CONTRACT_PATH)
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)

MAX_SAMPLE_ROWS = 25
MAX_CATALOG_ROWS = 256
MAX_FIELD_CHARACTERS = 256
MAX_FIELD_BYTES = 1024
STATEMENT_TIMEOUT_MS = 3000
LOCK_TIMEOUT_MS = 1000
_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')
_SAMPLE_FIELDS = ('customer_id', 'project_id', 'run_id', 'status')


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can contain rejected values, including credentials.
        self.exit(2, 'invalid_arguments\n')


class _Blocked(Exception):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode('ascii')).hexdigest()


def _rows(connection, sql, params=(), *, maximum):
    with connection.execute(sql, params) as cursor:
        rows = cursor.fetchmany(maximum + 1)
    if len(rows) > maximum:
        raise _Blocked('query_row_limit_exceeded')
    return rows


def _one(connection, sql, params=()):
    rows = _rows(connection, sql, params, maximum=1)
    if len(rows) != 1:
        raise _Blocked('required_observation_missing')
    return rows[0]


def verify_connection(connection, *, schema='public', sample_rows=3) -> dict[str, Any]:
    """Return bounded read observations, never an assertion of restore provenance."""
    contract = _contract.storage_schema_contract()
    output = {
        'artifact_schema': 'nico.readonly_restore_observation.v1',
        'status': 'blocked',
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'schema_contract_sha256': contract['contract_sha256'],
        'required_tables_verified': False,
        'migration_contract_verified': False,
        'bounded_application_reads_verified': False,
        'read_only_transaction_verified': False,
        'transaction_rolled_back': False,
        'restore_provenance_verified': False,
        'evidence_record_written': False,
        'record_set_scope': 'bounded_identifier_status_and_payload_type_projection',
        'record_set_sha256': None,
        'table_samples': [],
        'blockers': [],
    }
    if not isinstance(schema, str) or not _IDENTIFIER.fullmatch(schema):
        output['blockers'] = ['invalid_schema_identifier']
        return output
    if type(sample_rows) is not int or not 1 <= sample_rows <= MAX_SAMPLE_ROWS:
        output['blockers'] = ['invalid_sample_limit']
        return output
    # Do not join or roll back somebody else's transaction.
    if getattr(getattr(connection, 'info', None), 'transaction_status', None) != 0:
        output['blockers'] = ['idle_owned_connection_required']
        return output
    begun = False
    observations = []
    try:
        begun = True
        connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY').close()
        connection.execute(f'SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}').close()
        connection.execute(f'SET LOCAL lock_timeout = {LOCK_TIMEOUT_MS}').close()
        connection.execute('SET LOCAL idle_in_transaction_session_timeout = 10000').close()
        connection.execute('SET LOCAL search_path = pg_catalog').close()
        if _one(connection, 'SHOW transaction_read_only')[0] != 'on':
            raise _Blocked('read_only_transaction_not_established')
        if _one(connection, 'SHOW transaction_isolation')[0] != 'repeatable read':
            raise _Blocked('repeatable_read_not_established')
        output['read_only_transaction_verified'] = True
        if _one(connection, 'SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s)', (schema,))[0] is not True:
            raise _Blocked('required_schema_missing')
        catalog_rows = _rows(connection, '''SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position LIMIT 257''',
            (schema, sorted(contract['tables'])), maximum=MAX_CATALOG_ROWS)
        catalog = _contract.normalize_catalog_rows([
            {'table_name': row[0], 'column_name': row[1]} for row in catalog_rows])
        comparison = _contract.compare_schema_catalog(catalog)
        if not comparison['complete']:
            raise _Blocked('required_tables_or_columns_missing')
        output['required_tables_verified'] = True
        ledger = _rows(connection,
            f'SELECT pg_catalog.left(contract_sha256::text, 65) FROM "{schema}"."nico_schema_migrations" WHERE version = %s LIMIT 2',
            (contract['version'],), maximum=2)
        if len(ledger) != 1 or ledger[0][0] != contract['contract_sha256']:
            raise _Blocked('migration_contract_missing_or_mismatched')
        output['migration_contract_verified'] = True
        for table, columns in sorted(contract['tables'].items()):
            if table == contract['migration_table']:
                continue
            fields = [columns[0], *(name for name in _SAMPLE_FIELDS if name in columns and name != columns[0])]
            # Bound every returned scalar in SQL; no payload bodies, blobs or
            # full-table counts/digests are transferred. Unknown scalar types or
            # incompatible payload columns fail through the normal read error.
            projection = ', '.join(f'pg_catalog.left("{field}"::text, 257)' for field in fields)
            has_payload = 'payload' in columns
            if has_payload:
                projection += ', pg_catalog.jsonb_typeof("payload")'
            rows = _rows(connection,
                f'SELECT {projection} FROM "{schema}"."{table}" ORDER BY "{columns[0]}" LIMIT %s',
                (sample_rows,), maximum=sample_rows)
            normalized = []
            for row in rows:
                if len(row) != len(fields) + int(has_payload) or not row[0]:
                    raise _Blocked('application_projection_invalid')
                values = list(row[:len(fields)])
                if any(value is not None and (type(value) is not str or len(value) > MAX_FIELD_CHARACTERS
                        or len(value.encode('utf-8')) > MAX_FIELD_BYTES) for value in values):
                    raise _Blocked('application_projection_limit_exceeded')
                if has_payload and row[-1] != 'object':
                    raise _Blocked('application_payload_not_object')
                normalized.append(list(row))
            if table in ('assessment_runs', 'reports') and not rows:
                raise _Blocked('application_sample_empty')
            observations.append({'table': table, 'fields': fields,
                'payload_type_checked': has_payload, 'sampled_rows': len(rows),
                'sample_sha256': _digest(normalized)})
        output['bounded_application_reads_verified'] = True
    except _Blocked as exc:
        output['blockers'].append(str(exc))
    except Exception:
        # Never emit raw SQL errors, connection strings or sampled data.
        output['blockers'].append('verification_read_failed')
    finally:
        if begun:
            try:
                connection.execute('ROLLBACK').close()
                output['transaction_rolled_back'] = True
            except Exception:
                output['blockers'].append('transaction_rollback_failed')
    if not output['blockers']:
        output['status'] = 'verified_read_observation'
        output['table_samples'] = observations
        output['record_set_sha256'] = _digest({'contract': contract['contract_sha256'],
            'schema': schema, 'sample_limit': sample_rows, 'tables': observations})
    return output


def main():
    parser = _SanitizedParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--service', required=True, help='Existing libpq service profile name; never a URL')
    parser.add_argument('--schema', default='public')
    parser.add_argument('--sample-rows', type=int, default=3)
    args = parser.parse_args()
    if not _IDENTIFIER.fullmatch(args.service):
        parser.error('service must be a bounded identifier')
    if not _IDENTIFIER.fullmatch(args.schema) or not 1 <= args.sample_rows <= MAX_SAMPLE_ROWS:
        parser.error('schema and sample limit must satisfy verifier bounds')
    connection = None
    try:
        import psycopg
        connection = psycopg.connect(service=args.service, autocommit=True, connect_timeout=5,
            options='-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000')
        result = verify_connection(connection, schema=args.schema, sample_rows=args.sample_rows)
    except Exception:
        result = {'status': 'blocked', 'blockers': ['verification_connection_failed'],
                  'restore_provenance_verified': False, 'evidence_record_written': False}
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                result['status'] = 'blocked'
                result.setdefault('blockers', []).append('verification_connection_close_failed')
                result['record_set_sha256'] = None
                result['table_samples'] = []
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'verified_read_observation' else 1


if __name__ == '__main__':
    raise SystemExit(main())
