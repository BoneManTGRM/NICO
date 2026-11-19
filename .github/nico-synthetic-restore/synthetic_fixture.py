"""Job-only synthetic writer/reader; fixed local socket, no URLs/default credentials."""
import os,sys,json
from datetime import datetime,timezone
from pathlib import Path
from native_reader import modules
from native_pg18_driver import qualify_snapshot
Store=modules()
from nico.comprehensive_run_record import create_comprehensive_run_record
import psycopg
ROOT=Path('/tmp/nico-native-fixture')
def connect(db, *, reader=False):
    if os.environ.get('NICO_SYNTHETIC_JOB')!='pg18-native-v1' or db not in ('nico_fixture','nico_fixture_recovered'):
        raise ValueError('synthetic_job_required')
    # All options explicit; environment is scrubbed by launcher.
    return psycopg.connect(host=str(ROOT/'socket'),hostaddr='',port=6543,user='fixture_reader' if reader else 'postgres',dbname=db,
        password='',passfile='/dev/null',service='',connect_timeout=5,autocommit=True,
        options='-c statement_timeout=3000 -c lock_timeout=1000')
def record(run_id):
    return create_comprehensive_run_record(run_id=run_id,repository='fixture/synthetic',commit_sha='a'*40,
        evidence_ledger_id='fixture_ledger_'+run_id,customer_id='synthetic_customer',project_id='synthetic_project',
        authorized=True,now=datetime(2026,11,19,tzinfo=timezone.utc))
def seed():
    store=Store(lambda:connect('nico_fixture'),dialect='postgres');store.ensure_schema()
    for name in ('valid','tampered','missing'):
        store.create(record('comprun_'+name))
    with connect('nico_fixture') as c:
        c.execute("DELETE FROM nico_comprehensive_review_history_commitments WHERE run_id='comprun_missing'")
        c.execute("UPDATE nico_comprehensive_runs SET payload=jsonb_set(payload,'{client_delivery_allowed}','true'::jsonb) WHERE run_id='comprun_tampered'")
def read():
    results={}
    for name in ('valid','tampered','missing'):
        c=connect('nico_fixture_recovered',reader=True)
        with c.cursor() as cur:
            cur.execute("SELECT session_user, current_user, has_table_privilege(current_user,'public.nico_comprehensive_runs','SELECT'), has_table_privilege(current_user,'public.nico_comprehensive_runs','INSERT,UPDATE,DELETE')")
            if cur.fetchone()!=('fixture_reader','fixture_reader',True,False):raise ValueError('reader_role')
            cur.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit FROM pg_catalog.pg_roles WHERE rolname=current_user")
            if cur.fetchone()!=(False,False,False,False,False,False):raise ValueError('role_authority')
            cur.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE,TEMP'),has_schema_privilege(current_user,'public','CREATE'),EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user))")
            if cur.fetchone()!=(False,False,False):raise ValueError('writer_or_membership')
        r=qualify_snapshot(Store,c,run_id='comprun_'+name,customer_id='synthetic_customer',project_id='synthetic_project')
        expected='synthetic_native_read_passed' if name=='valid' else 'blocked'
        if r['status']!=expected:raise ValueError('unexpected_read_result')
        results[name]=r['status']
    print(json.dumps({'artifact_schema':'nico.synthetic_native_restore.v1','synthetic_only':True,
        'gate_eligible':False,'production_restore_proven':False,'checks':results},sort_keys=True))
def main():
    try:
        if sys.argv[1:] == ['seed']:seed()
        elif sys.argv[1:]==['read']:read()
        elif sys.argv[1:]==['after-backup']:Store(lambda:connect('nico_fixture'),dialect='postgres').create(record('comprun_after_backup'))
        else:raise ValueError('mode')
        return 0
    except Exception:
        print('synthetic_fixture_failed');return 1
if __name__=='__main__':raise SystemExit(main())
