"""Execute unchanged probe/wrappers on the existing CI PostgreSQL16 container only."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from uuid import uuid4
import postgres_readonly_restore_proof as generic

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / 'scripts/restore_observation'


def container_id():
    value = os.environ.get('NICO_SYNTHETIC_POSTGRES_CONTAINER', '')
    if not re.fullmatch('[0-9a-f]{12,64}', value):
        raise ValueError('existing_ci_container_required')
    return value


def proof():
    checks = {}
    # Same strict loopback/CI guard and synthetic credentials as the generic proof.
    with generic.fixture_connection() as admin:
        container = container_id()
        db = 'comprehensive_proof_' + uuid4().hex
        admin.execute(f'CREATE DATABASE "{db}"')
        try:
            import psycopg
            with psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=5432,
                    user='nico', password='nico', dbname=db, autocommit=True,
                    connect_timeout=5, options='-c statement_timeout=3000') as conn, tempfile.TemporaryDirectory() as directory:
                # Forward psql to the already existing container, preserving wrapper
                # env and arguments. No new container/service, auth or HBA changes.
                shim = Path(directory) / 'psql'
                shim.write_text('#!/usr/bin/python3\nimport os,sys\n'
                    + 'args=["docker","exec","-i",'+repr(container)+',"env","-i","PATH=/usr/local/bin:/usr/bin:/bin"]\n'
                    + 'args += [k+"="+v for k,v in os.environ.items() if k.startswith("PG")]\n'
                    + 'os.execvp("docker",args+["psql"]+sys.argv[1:])\n')
                shim.chmod(0o700)
                contract = generic.verifier._contract.storage_schema_contract()
                for table, columns in contract['tables'].items():
                    definitions = ','.join('"'+c+'" text' for c in columns)
                    conn.execute(f'CREATE TABLE public."{table}" ({definitions})')
                conn.execute('INSERT INTO nico_schema_migrations(version,contract_sha256) VALUES (%s,%s)',
                             (contract['version'],contract['contract_sha256']))
                conn.execute('CREATE TABLE nico_comprehensive_runs(run_id text,customer_id text,project_id text,repository text,commit_sha text,evidence_ledger_id text,status text,revision integer,terminal boolean,integrity_sha256 text,updated_at text,payload jsonb)')
                conn.execute('CREATE TABLE nico_comprehensive_browser_projections(run_id text,revision integer,run_integrity_sha256 text,projection_sha256 text,updated_at text,projection jsonb)')
                identity = dict(run_id='comprun_synthetic',customer_id='customer',project_id='project',repository='fixture/repo',commit_sha='a'*40,evidence_ledger_id='ledger')
                payload = dict(identity=identity,integrity_sha256='b'*64,
                    artifact_schema='nico.comprehensive_run_record.v5',
                    completed_stages=['final_comprehensive_report_generation'],
                    stage_results={'final_comprehensive_report_generation':dict(status='complete',
                        report_package={'private_report':'synthetic_payload_must_not_escape'})})
                projection = dict(**identity,revision=1,integrity_sha256='b'*64,canonical_status='review_required',terminal=True,
                    response_projection=dict(browser_projection=True,durable_projection=True,terminal_report_manifest_attached=True),
                    reports=dict(pdf_available=True,json_available=True,pdf_sha256='c'*64,canonical_truth_sha256='d'*64))
                def seed(body=payload, projected=projection):
                    conn.execute('DELETE FROM nico_comprehensive_runs')
                    conn.execute('DELETE FROM nico_comprehensive_browser_projections')
                    conn.execute('INSERT INTO nico_comprehensive_runs VALUES (%s,%s,%s,%s,%s,%s,%s,1,true,%s,%s,%s::jsonb)',
                        (*identity.values(),'review_required','b'*64,'2026-10-18T00:00:00Z',json.dumps(body)))
                    conn.execute('INSERT INTO nico_comprehensive_browser_projections VALUES (%s,1,%s,%s,%s,%s::jsonb)',
                        (identity['run_id'],'b'*64,'e'*64,'2026-10-18T00:00:00Z',json.dumps(projected)))
                def observe(name, *, blocked=False, discover=False, error=False, run_id=None, expected=None, discovery_status='review_required'):
                    before = generic._snapshot(conn,'public')
                    env = dict(PATH=directory+':/usr/bin:/bin', POSTGRES_USER='nico', POSTGRES_DB=db,
                        NICO_EXPECTED_RUN_ID=run_id or identity['run_id'], PGPASSWORD='must_not_leak', PGSERVICE='must_not_leak')
                    proc = subprocess.run(['bash',str(PROBES / ('discover-console.sh' if discover else 'observe-console.sh'))],
                        env=env,capture_output=True,text=True,timeout=100)
                    assert generic._snapshot(conn,'public') == before
                    assert conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()', (db,)).fetchone()[0]==0
                    assert proc.stderr == ''
                    assert 'synthetic_payload_must_not_escape' not in proc.stdout
                    if error:
                        assert proc.returncode != 0 and proc.stdout.endswith('observation_failed\n')
                    else:
                        assert proc.returncode == 0, (name,proc.stdout)
                        lines=proc.stdout.splitlines()
                        assert lines[-1]=='observation_transaction_closed'
                        result=json.loads(lines[0])
                        assert result['restore_provenance_verified'] is False
                        assert result['report_bytes_verified'] is False
                        if discover:
                            assert result['runs']==[dict(run_id=identity['run_id'],revision=1,commit_sha='a'*40,exact_run_status=discovery_status)]
                        else:
                            assert result['status']==('blocked' if blocked else 'bounded_comprehensive_metadata_observation'), (name,result)
                            if blocked: assert result['observation_sha256'] is None
                            else: generic._assert_digest(result['observation_sha256'])
                        if expected:
                            for key,value in expected.items():
                                assert result[key]==value, (name,key,result[key],value)
                    checks[name]=True
                    checks[name+'_rows_columns_unchanged_and_session_closed']=True
                canonical = dict(exact_run_status='review_required',uncompressed_canonical=dict(
                    artifact_schema='nico.comprehensive_run_record.v5',final_stage_completed=True,
                    final_stage_status='complete',report_package_object_present=True,reports_object_present=False))
                seed();observe('uncompressed_generic_reports_empty',expected=dict(
                    projection_count=1,canonical_diagnostics=canonical,
                    projection_metadata_bound=True,stored_report_manifest_present=True))
                observe('exact_terminal_discovery',discover=True)
                legacy=copy.deepcopy(payload);legacy['artifact_schema']='nico.comprehensive_run_record.v2'
                seed(legacy);conn.execute('DELETE FROM nico_comprehensive_browser_projections')
                legacy_diagnostic=copy.deepcopy(canonical)
                legacy_diagnostic['uncompressed_canonical']['artifact_schema']='nico.comprehensive_run_record.v2'
                observe('legacy_report_without_projection',blocked=True,expected=dict(projection_count=0,
                    joined_row_count=1,canonical_diagnostics=legacy_diagnostic,
                    projection_metadata_bound=False,stored_report_manifest_present=False))
                for status in ['failed','blocked']:
                    reportless=copy.deepcopy(payload);reportless['completed_stages']=[]
                    reportless['stage_results']={'final_comprehensive_report_generation':{'status':status}}
                    expected=copy.deepcopy(canonical);expected['exact_run_status']=status
                    expected['uncompressed_canonical'].update(final_stage_completed=False,final_stage_status=status,
                        report_package_object_present=False)
                    seed(reportless);conn.execute('UPDATE nico_comprehensive_runs SET status=%s',(status,))
                    conn.execute('DELETE FROM nico_comprehensive_browser_projections')
                    observe(status+'_reportless_missing_projection',blocked=True,expected=dict(
                        projection_count=0,canonical_diagnostics=expected))
                    observe(status+'_discovery',discover=True,discovery_status=status)
                    reportless_projection=copy.deepcopy(projection)
                    reportless_projection['canonical_status']=status
                    reportless_projection['reports']={}
                    reportless_projection['response_projection']['terminal_report_manifest_attached']=False
                    seed(reportless,reportless_projection);conn.execute('UPDATE nico_comprehensive_runs SET status=%s',(status,))
                    observe(status+'_reportless_bound_projection',blocked=True,expected=dict(
                        projection_count=1,canonical_diagnostics=expected,
                        projection_metadata_bound=True,stored_report_manifest_present=False))
                alias=copy.deepcopy(payload);final=alias['stage_results']['final_comprehensive_report_generation']
                final['reports']=final.pop('report_package');expected=copy.deepcopy(canonical)
                expected['uncompressed_canonical'].update(report_package_object_present=False,reports_object_present=True)
                seed(alias);observe('historical_reports_alias',expected=dict(canonical_diagnostics=expected))
                malformed=copy.deepcopy(payload)
                malformed['completed_stages']={'final_comprehensive_report_generation':True}
                malformed['stage_results']['final_comprehensive_report_generation'].update(report_package=[],reports=None)
                expected=copy.deepcopy(canonical)
                expected['uncompressed_canonical'].update(final_stage_completed=False,report_package_object_present=False)
                seed(malformed);observe('nonobject_report_and_nonarray_completion',expected=dict(canonical_diagnostics=expected))
                unknown=copy.deepcopy(payload);unknown['artifact_schema']='synthetic_payload_must_not_escape'
                unknown['stage_results']['final_comprehensive_report_generation']['status']='synthetic_payload_must_not_escape'
                expected=copy.deepcopy(canonical);expected['uncompressed_canonical'].update(artifact_schema=None,final_stage_status=None)
                seed(unknown);observe('unknown_canonical_labels_suppressed',expected=dict(canonical_diagnostics=expected))
                conn.execute('UPDATE nico_comprehensive_runs SET status=%s',('synthetic_payload_must_not_escape',))
                expected['exact_run_status']=None
                observe('unknown_run_status_suppressed',blocked=True,expected=dict(canonical_diagnostics=expected))
                observe('unknown_discovery_status_suppressed',discover=True,discovery_status=None)
                seed()
                observe('wrong_exact_run',blocked=True,run_id='comprun_absent')
                observe('quoted_input',blocked=True,run_id="x' OR true --")
                for version, encoding in [('v1','zlib+base64'),('v2','zlib+json-token-refs-v1+base64'),('v3','zlib+json-chunk-refs-v1+base64')]:
                    envelope={'__nico_comprehensive_run_storage_v1__':dict(schema='nico.comprehensive_run_storage.'+version,encoding=encoding,size_bytes=100,sha256='f'*64,data='eA==')}
                    seed(envelope);observe('stored_envelope_metadata_'+version,expected=dict(canonical_diagnostics=dict(exact_run_status='review_required',uncompressed_canonical=None)))
                # Deliberately not a real compressed report: passing metadata is not decode proof.
                for field,value in [('revision',2),('commit_sha','0'*40),('run_id','other'),('integrity_sha256','0'*64),('terminal',None)]:
                    bad=copy.deepcopy(projection);bad[field]=value;seed(projected=bad);observe('projection_'+field,blocked=True,expected=dict(projection_count=1,projection_metadata_bound=False,stored_report_manifest_present=True,canonical_diagnostics=canonical))
                for value in [None,'bad','c'*65]:
                    bad=copy.deepcopy(projection);bad['reports']['pdf_sha256']=value
                    seed(projected=bad);observe('pdf_digest_'+str(value),blocked=True)
                for field,value in [('sha256','bad'),('size_bytes',0),('schema','unsupported'),('data',None)]:
                    bad=copy.deepcopy(envelope);bad['__nico_comprehensive_run_storage_v1__'][field]=value
                    seed(bad);observe('envelope_'+field,blocked=True)
                seed();conn.execute('DELETE FROM nico_schema_migrations');observe('absent_ledger',blocked=True)
                conn.execute('INSERT INTO nico_schema_migrations(version,contract_sha256) VALUES (%s,%s)',(contract['version'],contract['contract_sha256']))
                seed();conn.execute('DELETE FROM nico_comprehensive_browser_projections');observe('absent_projection',blocked=True,expected=dict(projection_count=0,joined_row_count=1,canonical_diagnostics=canonical))
                seed();conn.execute('UPDATE nico_schema_migrations SET contract_sha256=%s',('0'*64,));observe('wrong_ledger',blocked=True)
                conn.execute('UPDATE nico_schema_migrations SET contract_sha256=%s',(contract['contract_sha256'],))
                seed();conn.execute('UPDATE nico_comprehensive_browser_projections SET projection=NULL');observe('null_projection',blocked=True)
                seed();conn.execute('UPDATE nico_comprehensive_browser_projections SET revision=2');observe('row_revision',blocked=True)
                seed();conn.execute('UPDATE nico_comprehensive_browser_projections SET run_integrity_sha256=%s',('0'*64,));observe('row_integrity',blocked=True)
                seed();conn.execute('UPDATE nico_comprehensive_runs SET payload=NULL');observe('null_payload',blocked=True)
                seed();conn.execute('INSERT INTO nico_comprehensive_runs SELECT * FROM nico_comprehensive_runs');observe('duplicate_run',blocked=True,expected=dict(projection_count=1,canonical_diagnostics=None))
                seed();conn.execute('INSERT INTO nico_comprehensive_browser_projections SELECT * FROM nico_comprehensive_browser_projections');observe('duplicate_projection',blocked=True,expected=dict(projection_count=2,canonical_diagnostics=canonical))
                seed();conn.execute('DELETE FROM nico_comprehensive_runs');conn.execute("INSERT INTO reports(report_id) VALUES ('generic_only')");observe('wrong_table',blocked=True,expected=dict(projection_count=1,canonical_diagnostics=None))
                seed()
                for table,column in [('customers','customer_id'),('nico_comprehensive_runs','payload'),('nico_comprehensive_browser_projections','projection')]:
                    conn.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{column}" TO missing_column')
                    observe('missing_'+table+'_'+column,blocked=True)
                    conn.execute(f'ALTER TABLE "{table}" RENAME COLUMN missing_column TO "{column}"')
                conn.execute('ALTER TABLE nico_comprehensive_runs RENAME TO missing_runs')
                observe('sql_error_nonzero',discover=True,error=True)
                conn.execute('ALTER TABLE missing_runs RENAME TO nico_comprehensive_runs')
                checks['readonly_rollback_in_exact_sql']=all('ROLLBACK;' in (PROBES / name).read_text() and 'REPEATABLE READ READ ONLY' in (PROBES / name).read_text() for name in ['terminal_run_discovery.sql','comprehensive_metadata_observation.sql'])
        finally:
            admin.execute(f'DROP DATABASE "{db}"')
        assert admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',(db,)).fetchone() is None
        checks['synthetic_database_removed']=True
    return checks


def main():
    result=dict(status='failed',synthetic=True,live_production_claim=False,report_bytes_verified=False,
        restore_provenance_verified=False,commit_sha=os.environ.get('GITHUB_SHA',''),checks={},
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PROBES.iterdir()) if p.is_file()})
    try:
        result['checks']=proof();result['status']='passed'
    except Exception:
        import traceback
        traceback.print_exc()
        result['error']='synthetic_comprehensive_observation_failed'
    output=ROOT/'audit-results/postgres-comprehensive-observation-proof.json'
    output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,sort_keys=True)+'\n')
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':
    raise SystemExit(main())
