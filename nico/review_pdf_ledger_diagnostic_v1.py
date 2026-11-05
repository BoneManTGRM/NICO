"""Disabled-canary ledger metadata only; no claims, maintenance or payload export."""
import json
import os
import re
from threading import BoundedSemaphore, Event, Thread

from nico.review_pdf_canary_scope_v1 import CanaryScope, FIELDS
from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
from nico.review_pdf_preparation_jobs_v1 import WORKFLOW

SCHEMA = 'nico.pdf-canary-ledger-read.v1'
SEARCH_SCOPE = 'configured-row-tenant-and-identity-run-locale'
MAX_ROWS = 32
MAX_OUTPUT_BYTES = 24 * 1024
DEADLINE_SECONDS = 10
_SLOT = BoundedSemaphore(1)
STATES = frozenset({'queued','rendering','rendered_unverified','ready','failed','budget_exhausted','cancelled','unknown'})

# Filter the configured tenant/run/locale, NOT current source revision or policy.
# That deliberate distinction exposes obsolete rows hidden by ordinary lookup.
# All selected values are bounded scalar metadata computed inside PostgreSQL.
QUERY = """SELECT
    CASE WHEN job_id ~ '^reviewpdfprep_[0-9a-f]{64}$' THEN job_id ELSE NULL END,
    CASE WHEN status IN ('queued','rendering','rendered_unverified','ready','failed','budget_exhausted','cancelled')
         THEN status ELSE 'unknown' END,
    COALESCE(payload->>'status'=status, false),
    ARRAY(SELECT expected.key FROM jsonb_each(%s::jsonb) AS expected
          WHERE (payload->'identity'->expected.key) IS DISTINCT FROM expected.value
          ORDER BY expected.key),
    CASE WHEN payload->'identity'->>'renderer_revision' ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'
         THEN payload->'identity'->>'renderer_revision' ELSE NULL END,
    CASE WHEN payload->'identity'->>'policy_sha256' ~ '^[0-9a-f]{64}$'
         THEN payload->'identity'->>'policy_sha256' ELSE NULL END,
    CASE WHEN jsonb_typeof(payload->'attempts')='number'
              AND payload->>'attempts' ~ '^[0-9]{1,9}$'
         THEN (payload->>'attempts')::integer ELSE NULL END,
    CASE WHEN jsonb_typeof(payload->'lease_until_epoch')='number'
         THEN (payload->>'lease_until_epoch')::numeric > EXTRACT(EPOCH FROM statement_timestamp()) ELSE NULL END,
    CASE WHEN jsonb_typeof(payload->'deadline_epoch')='number'
         THEN (payload->>'deadline_epoch')::numeric <= EXTRACT(EPOCH FROM statement_timestamp()) ELSE NULL END
    FROM client_jobs
    WHERE customer_id=%s AND project_id=%s AND payload->>'workflow'=%s
      AND payload->'identity'->>'run_id'=%s AND payload->'identity'->>'language'=%s
    ORDER BY job_id LIMIT %s"""


def unknown(status='unavailable'):
    return dict(schema=SCHEMA, status=status, search_scope=SEARCH_SCOPE, job_integrity_verified=False, query_complete=False,
                scoped_rows_present=None, exact_source_row_present=None,
                rows_returned=0, rows=[], physical_worker_exit_confirmed=None,
                activation_authorized=False)


def safe_row(row):
    if type(row) not in (tuple, list) or len(row) != 9:
        raise ValueError('invalid_ledger_metadata')
    job_id,state,payload_matches,mismatches,renderer,policy,attempts,lease,expired = row
    for value, pattern in ((job_id,r'reviewpdfprep_[0-9a-f]{64}'),
                           (renderer,r'[0-9a-f]{40}|[0-9a-f]{64}'),(policy,r'[0-9a-f]{64}')):
        if value is not None and (type(value) is not str or re.fullmatch(pattern,value) is None):
            raise ValueError('invalid_ledger_metadata')
    if (state not in STATES or type(payload_matches) is not bool
            or type(mismatches) is not list or len(mismatches)>len(FIELDS)
            or any(type(key) is not str or key not in FIELDS for key in mismatches)
            or len(set(mismatches)) != len(mismatches)
            or (attempts is not None and (type(attempts) is not int or not 0<=attempts<=999999999))
            or any(value is not None and type(value) is not bool for value in (lease,expired))):
        raise ValueError('invalid_ledger_metadata')
    return dict(job_id=job_id,state=state,payload_state_matches=payload_matches,
                source_binding_matches=not mismatches, binding_mismatches=sorted(mismatches),
                renderer_revision=renderer,policy_sha256=policy,attempts=attempts,
                lease_active_at_read=lease,deadline_expired_at_read=expired)


def inspect_ledger(app, run_id, language, guard):
    # Diagnostic is intentionally unavailable while either preparation switch is on.
    if any(os.getenv(key)=='true' for key in
           ('NICO_ENABLE_REVIEW_PDF_PREPARATION','NICO_REVIEW_PDF_PG_QUALIFIED')):
        return unknown()
    raw=os.getenv('NICO_REVIEW_PDF_CANARY_SCOPE','')
    scope=CanaryScope.parse(raw)
    binding=json.loads(raw)
    scope.request(run_id,language,{key:binding[key] for key in ('commit_sha','canonical_truth_sha256')})
    state=getattr(app.state,'comprehensive_runtime',None)
    store=app.state.comprehensive_api_controller._service._store
    if (type(state) is not dict or store._dialect!='postgres'
            or state.get('persistence_adapter')!='postgres' or state.get('configured') is not True):
        return unknown()
    connection=None
    result=unknown()
    transaction=False
    try:
        guard.check()
        connection=store._connection_factory()
        if int(connection.info.transaction_status)!=0:
            return result
        guard.check()
        connection.execute('BEGIN READ ONLY')
        transaction=True
        connection.execute("SET LOCAL statement_timeout = '3s'")
        connection.execute("SET LOCAL lock_timeout = '1s'")
        connection.execute("SET LOCAL idle_in_transaction_session_timeout = '5s'")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only') = 'on'")
            if cursor.fetchone()[0] is not True:
                return result
            guard.check()
            cursor.execute(QUERY,(json.dumps(binding,sort_keys=True),binding['customer_id'],binding['project_id'],
                                  WORKFLOW,run_id,language,MAX_ROWS+1))
            fetched=cursor.fetchmany(MAX_ROWS+1)
            if len(fetched)>MAX_ROWS+1:
                raise ValueError('invalid_ledger_row_bound')
            metadata=[safe_row(row) for row in fetched]
        guard.check()
        complete=len(metadata)<=MAX_ROWS
        exact=any(row['source_binding_matches'] for row in metadata)
        rows=metadata[:MAX_ROWS]
        result=dict(schema=SCHEMA,status='complete' if complete else 'partial',search_scope=SEARCH_SCOPE,
                    job_integrity_verified=False,query_complete=complete,
                    read_only_transaction=True,scoped_rows_present=bool(metadata),
                    exact_source_row_present=True if exact else False if complete else None,
                    rows_returned=len(rows),rows=rows,
                    physical_worker_exit_confirmed=None,activation_authorized=False)
        if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>MAX_OUTPUT_BYTES:
            raise ValueError('invalid_ledger_output_bound')
        guard.check()
    finally:
        if connection is not None:
            try:
                if transaction: connection.rollback()
            finally:
                connection.close()
    return result


def diagnose_ledger(app, run_id, language):
    if not _SLOT.acquire(blocking=False):
        return unknown('busy')
    guard=DeadlineGuard(DEADLINE_SECONDS,Event())
    try:
        return guard.call(inspect_ledger,app,run_id,language,guard)
    except Exception:
        return unknown()
    finally:
        guard.stop.set()
        def release():
            while not guard.idle(): Event().wait(.02)
            _SLOT.release()
        if guard.idle(): release()
        else: Thread(target=release,daemon=True,name='nico-ledger-read-quarantine').start()
