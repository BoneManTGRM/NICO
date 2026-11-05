"""Count/boolean-only diagnostic; no startup, schema initialization or row reads."""
from threading import BoundedSemaphore, Event, Thread

from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard

_SLOT = BoundedSemaphore(1)
DEADLINE_SECONDS = 10

EXPECTED = {
    'client_jobs': ('job_id', 'customer_id', 'project_id', 'status', 'payload', 'created_at', 'updated_at'),
    'nico_comprehensive_runs': ('run_id', 'customer_id', 'project_id', 'repository', 'commit_sha', 'revision', 'integrity_sha256', 'terminal', 'payload'),
    'nico_comprehensive_review_history_commitments': ('run_id', 'event_count', 'chain_sha256'),
}


def inspect_existing_runtime(app, guard):
    result = {
        'schema': 'nico.pdf-storage-readonly-probe.v1',
        'canonical_postgres': None,
        'runtime_configured': None,
        'runtime_durability_claim': None,
        'read_only_transaction': None,
        'schema_read_compatible': None,
        'tables': {name: None for name in EXPECTED},
        'probe_complete': False,
        'lifecycle_qualified': False,
    }
    connection = None
    owns_connection = False
    try:
        state = getattr(app.state, 'comprehensive_runtime', None)
        controller = getattr(app.state, 'comprehensive_api_controller', None)
        if type(state) is not dict or controller is None:
            return result
        store = controller._service._store
        dialect, adapter = getattr(store, '_dialect', None), state.get('persistence_adapter')
        if type(dialect) is str and dialect and type(adapter) is str and adapter:
            result['canonical_postgres'] = dialect == adapter == 'postgres'
        configured = state.get('configured')
        result['runtime_configured'] = configured if type(configured) is bool else None
        # A runtime claim, NOT an independently observed restart test.
        durability = state.get('survives_container_replacement_verified')
        result['runtime_durability_claim'] = durability if type(durability) is bool else None
        if not all(result[key] for key in (
                'canonical_postgres', 'runtime_configured', 'runtime_durability_claim')):
            return result
        guard.check()
        connection = store._connection_factory()
        # The canonical factory owns a fresh connection, never a borrowed pool handle.
        # Refuse unexpected transaction state and close without issuing SQL.
        if int(connection.info.transaction_status) != 0:
            return result
        owns_connection = True
        guard.check()
        connection.execute('BEGIN READ ONLY')
        connection.execute("SET LOCAL statement_timeout = '3s'")
        connection.execute("SET LOCAL lock_timeout = '1s'")
        connection.execute("SET LOCAL idle_in_transaction_session_timeout = '5s'")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only') = 'on'")
            result['read_only_transaction'] = cursor.fetchone()[0] is True
            if not result['read_only_transaction']:
                return result
            for table, columns in EXPECTED.items():
                guard.check()
                # Catalogs only: no assessment rows, source text or credentials.
                cursor.execute('''SELECT c.relkind IN ('r','p'),
                    pg_catalog.has_table_privilege(c.oid, 'SELECT'),
                    ARRAY(SELECT a.attname::text FROM pg_catalog.pg_attribute a
                          WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped)
                    FROM pg_catalog.pg_class c
                    WHERE c.oid=pg_catalog.to_regclass(%s)''', (table,))
                row = cursor.fetchone()
                result['tables'][table] = bool(row and row[0] and row[1]
                                               and set(columns).issubset(row[2]))
        result['schema_read_compatible'] = all(result['tables'].values())
        guard.check()
        result['probe_complete'] = True
    except Exception:
        # Intentionally omit raw errors, SQL diagnostics, URLs and credentials.
        pass
    finally:
        if connection is not None:
            if owns_connection:
                try:
                    connection.rollback()
                except Exception:
                    result['probe_complete'] = False
            try:
                connection.close()
            except Exception:
                result['probe_complete'] = False
    return result


def diagnose_storage(app):
    if not _SLOT.acquire(blocking=False):
        return {'schema': 'nico.pdf-storage-readonly-probe.v1', 'status': 'busy',
                'probe_complete': False, 'lifecycle_qualified': False}
    guard = DeadlineGuard(DEADLINE_SECONDS, Event())
    try:
        return guard.call(inspect_existing_runtime, app, guard)
    except Exception:
        return {'schema': 'nico.pdf-storage-readonly-probe.v1', 'status': 'unavailable',
                'probe_complete': False, 'lifecycle_qualified': False}
    finally:
        guard.stop.set()
        def release():
            while not guard.idle():
                Event().wait(.02)
            _SLOT.release()
        if guard.idle():
            release()
        else:
            Thread(target=release, daemon=True, name='nico-storage-probe-quarantine').start()
