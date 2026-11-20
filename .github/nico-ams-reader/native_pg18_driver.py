"""Unexecuted PG18 driver. No connection opener or credentials. Synthetic only."""
from native_reader import read_snapshot

def qualify_snapshot(store_class, connection, *, run_id, customer_id, project_id):
    try:
        if connection.info.transaction_status != 0 or not 180000<=connection.info.server_version<190000:raise ValueError('connection')
        with connection.cursor() as cur:
            cur.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for sql in ('SET LOCAL statement_timeout = 3000','SET LOCAL lock_timeout = 1000',
                        'SET LOCAL idle_in_transaction_session_timeout = 10000','SET LOCAL search_path = pg_catalog, public'):
                cur.execute(sql)
            cur.execute('SHOW transaction_read_only')
            if cur.fetchone()!=('on',):raise ValueError('readonly')
            cur.execute('SHOW transaction_isolation')
            if cur.fetchone()!=('repeatable read',):raise ValueError('snapshot')
            cur.execute("SELECT c.relname,c.relkind FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('nico_comprehensive_runs','nico_comprehensive_review_history_commitments') ORDER BY c.relname")
            if cur.fetchmany(3)!=[('nico_comprehensive_review_history_commitments','r'),('nico_comprehensive_runs','r')]:raise ValueError('relations')
            cur.execute('SELECT pg_catalog.octet_length(payload::text), customer_id, project_id FROM public.nico_comprehensive_runs WHERE run_id=%s LIMIT 2',(run_id,))
            rows=cur.fetchmany(2)
            if len(rows)!=1 or not 0<rows[0][0]<=65536 or rows[0][1:]!=(customer_id,project_id):raise ValueError('size_scope')
        return read_snapshot(store_class,connection,run_id=run_id,customer_id=customer_id,project_id=project_id)
    except Exception:
        try:connection.rollback()
        finally:connection.close()
        return {'status':'blocked','synthetic_only':True,'gate_eligible':False}
