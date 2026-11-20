"""Synthetic canonical read qualification. Supplied connection only; no opener."""
import hashlib,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REVISION='5eb768b5776f88bae86e972c76267915cc874c85'
def modules():
    manifest=json.loads((ROOT/'native-source-manifest.json').read_text())
    for path,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/'native-source'/path).read_bytes()).hexdigest()!=digest:raise ValueError('source_hash_mismatch')
    if 'nico' in sys.modules:raise ValueError('fresh_process_required')
    pkg=types.ModuleType('nico');pkg.__path__=[str(ROOT/'native-source/nico')];sys.modules['nico']=pkg
    from nico.comprehensive_run_store import ComprehensiveRunStore
    return ComprehensiveRunStore
QUERY='''SELECT runs.payload, commitments.event_count, commitments.chain_sha256,
 runs.run_id, runs.customer_id, runs.project_id, runs.repository,
 runs.commit_sha, runs.evidence_ledger_id, runs.status, runs.revision,
 runs.terminal, runs.integrity_sha256, runs.updated_at
 FROM nico_comprehensive_runs AS runs
 LEFT JOIN nico_comprehensive_review_history_commitments AS commitments
 ON commitments.run_id = runs.run_id WHERE runs.run_id = %s'''
def norm(s):return ' '.join(s.split())
class Restricted:
    def __init__(self,conn,run_id,customer,project):self.conn=conn;self.ids=(run_id,customer,project);self.used=False;self.closed=False
    def cursor(self):return self
    def execute(self,sql,params):
        if self.used or norm(sql)!=norm(QUERY) or params!=(self.ids[0],):raise ValueError('query_boundary')
        self.used=True
        with self.conn.cursor() as cur:
            cur.execute(sql,params);rows=cur.fetchmany(2)
        if len(rows)!=1:raise ValueError('exactly_one_run_required')
        row=rows[0]
        if tuple(row[3:6])!=self.ids:raise ValueError('scope_mismatch')
        # Synthetic first qualification excludes compressed/chunked payloads.
        payload=row[0] if isinstance(row[0],dict) else json.loads(row[0])
        if not isinstance(payload,dict) or payload.get('artifact_schema') is None or 'encoding' in payload:raise ValueError('plain_canonical_fixture_required')
        if len(json.dumps(payload).encode())>65536:raise ValueError('fixture_payload_limit')
        self.row=row
    def fetchone(self):return self.row
    def commit(self):raise ValueError('commit_forbidden')
    def rollback(self):self.conn.rollback()
    def close(self):
        if not self.closed:
            try:self.conn.rollback()
            finally:self.conn.close();self.closed=True

def read_snapshot(store_class,conn,*,run_id,customer_id,project_id):
    """Caller must prequalify PG18, physical schema, idle exclusive connection,
    read-only repeatable snapshot, timeout and <=64KiB SQL payload preflight.
    This function intentionally cannot assert those external prerequisites.
    """
    wrapper=Restricted(conn,run_id,customer_id,project_id)
    factory_calls=0
    def factory():
        nonlocal factory_calls
        factory_calls+=1
        if factory_calls!=1:raise ValueError('one_connection_only')
        return wrapper
    try:
        record=store_class(factory,dialect='postgres').load_without_maintenance(run_id)
        if tuple(record['identity'][k] for k in ('run_id','customer_id','project_id'))!=(run_id,customer_id,project_id):raise ValueError('canonical_scope')
        return {'status':'synthetic_native_read_passed','synthetic_only':True,'gate_eligible':False,
                'record_digest':hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest(),
                'revision':REVISION,'production_restore_proven':False}
    except Exception:
        return {'status':'blocked','synthetic_only':True,'gate_eligible':False,'revision':REVISION}
    finally:wrapper.close()
