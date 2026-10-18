"""Source and SQLite catalog/run-selection mock tests, NOT PostgreSQL qualification."""
import ast
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'scripts/restore_observation'
source=(REPO/'nico/storage_schema_contract_v1.py').read_text()
namespace={}
for node in ast.parse(source).body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='STORAGE_SCHEMA_MIGRATION_TABLE' for t in node.targets):
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<contract>','exec'),namespace)
    if isinstance(node,ast.AnnAssign) and node.target.id=='EXPECTED_TABLE_COLUMNS':
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<contract>','exec'),namespace)
CONTRACT=namespace['EXPECTED_TABLE_COLUMNS']
store=(REPO/'nico/comprehensive_run_store.py').read_text()
EXTRA={}
for name in ['nico_comprehensive_runs','nico_comprehensive_browser_projections']:
    block=store.split('CREATE TABLE IF NOT EXISTS '+name+' (',1)[1].split(')',1)[0]
    EXTRA[name]=[line.strip().split()[0] for line in block.splitlines() if line.strip()]
ALL=[(t,c) for t,cols in {**CONTRACT,**EXTRA}.items() for c in cols]
SQL=(ROOT/'comprehensive_metadata_observation.sql').read_text()
CATALOG=(ROOT/'required_columns_query.sql').read_text()


def catalog(missing=None):
    db=sqlite3.connect(':memory:')
    db.execute("ATTACH DATABASE ':memory:' AS information_schema")
    db.execute('CREATE TABLE information_schema.columns(table_schema,table_name,column_name)')
    db.executemany('INSERT INTO information_schema.columns VALUES (?,?,?)',
                   [('public',t,c) for t,c in ALL if (t,c)!=missing])
    return db


def test_exact_contract_and_actual_store_column_sets():
    required={(t,c) for t,c,g in re.findall(r"\('([^']+)','([^']+)','(contract|comprehensive)'\)",CATALOG)}
    assert required==set(ALL)
    assert len(CONTRACT)==14 and len(EXTRA['nico_comprehensive_runs'])==12
    assert len(EXTRA['nico_comprehensive_browser_projections'])==6
    assert CATALOG.rstrip(';\n') in SQL
    with catalog() as db:assert db.execute(CATALOG).fetchone()==(1,0,0)


@pytest.mark.parametrize('missing',ALL)
def test_each_required_column_missing_fails_catalog_guard(missing):
    with catalog(missing) as db:
        valid,contract_missing,comprehensive_missing=db.execute(CATALOG).fetchone()
    assert valid==0
    assert contract_missing+comprehensive_missing==1
    assert (comprehensive_missing==1)==(missing[0] in EXTRA)


def test_missing_comprehensive_store_not_hidden_by_complete_generic_schema():
    with catalog() as db:
        db.execute("DELETE FROM information_schema.columns WHERE table_name LIKE 'nico_comprehensive_%'")
        assert db.execute(CATALOG).fetchone()==(0,0,18)


@pytest.mark.parametrize('canonical_present,generic_present',[(True,False),(False,True),(False,False)])
def test_actual_run_selection_is_independent_of_generic_reports(canonical_present,generic_present):
    # Execute the proposal's exact bounded SELECT on a SQLite mock namespace;
    # only psql variable substitution changes to an SQLite parameter binding.
    select=SQL.split('runs AS MATERIALIZED (',1)[1].split('), joined AS',1)[0].strip()
    select=select.replace(":'expected_run_id'",':expected_run_id')
    db=sqlite3.connect(':memory:');db.execute("ATTACH DATABASE ':memory:' AS public")
    db.execute('CREATE TABLE public.nico_comprehensive_runs ('+', '.join(c+' TEXT' for c in EXTRA['nico_comprehensive_runs'])+')')
    db.execute('CREATE TABLE public.reports(report_id TEXT)')
    if canonical_present:db.execute("INSERT INTO public.nico_comprehensive_runs(run_id) VALUES ('comprun_fixture')")
    if generic_present:db.execute("INSERT INTO public.reports VALUES ('generic_fixture')")
    assert len(db.execute(select,{'expected_run_id':'comprun_fixture'}).fetchall())==int(canonical_present)
    db.close()


def test_queries_keep_readonly_and_non_integrity_claims_explicit():
    assert '\\if :columns_ok' in SQL and '\\else' in SQL and '\\endif' in SQL
    assert "jsonb_typeof(payload) = 'object'" in SQL
    assert "envelope - ARRAY['schema','encoding','size_bytes','sha256','data'] = '{}'::jsonb" in SQL
    assert "left(envelope ->> 'size_bytes',12) ~ '^[0-9]{1,10}$'" in SQL
    assert "projection_revision = revision" in SQL
    assert "run_integrity_sha256 = integrity_sha256" in SQL
    assert 'ledger_valid AND run_count=1 AND joined_row_count=1' in SQL
    for flag in ['canonical_payload_deserialized','canonical_integrity_recomputed','projection_hash_recomputed','report_bytes_verified','restore_provenance_verified','evidence_record_written']:
        assert "'"+flag+"',false" in SQL
    assert 'FROM public.reports' not in SQL and 'FROM public.assessment_runs' not in SQL
    assert 'LIMIT 2' in SQL
    for name in ['observe-console.sh','discover-console.sh']:
        shell=(ROOT/name).read_text()
        assert 'timeout --kill-after=5s 90s env -i' in shell
        assert 'PGPASSFILE=/dev/null PGREQUIREAUTH=none' in shell
        assert "-d 'require_auth=none passfile=/dev/null'" in shell
        assert 'ON_ERROR_STOP=1' in shell
        assert 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;' in shell
        assert 'ROLLBACK;' in shell
        assert 'PGPASSWORD' not in shell

@pytest.mark.parametrize('name', ['observe','discover'])
@pytest.mark.parametrize('psql_exit', [0,1,2])
def test_wrapper_clean_env_exact_args_and_exit(tmp_path,name,psql_exit):
    import os, json
    fake=tmp_path/'psql'
    capture=tmp_path/'capture.json'
    fake.write_text('#!/usr/bin/python3\nimport os,sys,json\nfrom pathlib import Path\n'
        +f'Path({str(capture)!r}).write_text(json.dumps(dict(env=dict(os.environ),args=sys.argv[1:],sql=sys.stdin.read())))\n'
        +f'raise SystemExit({psql_exit})\n')
    fake.chmod(0o700)
    env={**os.environ,'PATH':str(tmp_path)+':/usr/bin:/bin',
         'POSTGRES_USER':'local_fixture','POSTGRES_DB':'fixture',
         'NICO_EXPECTED_RUN_ID':"comprun_quote'fixture",'PGPASSWORD':'synthetic_must_not_leak',
         'PGSERVICE':'synthetic_must_not_leak','PGHOST':'remote.invalid',
         'HOME':str(tmp_path),'SECRET_SENTINEL':'synthetic_must_not_leak'}
    proc=subprocess.run(['bash',str(ROOT/(name+'-console.sh'))],env=env,text=True,capture_output=True)
    observed=json.loads(capture.read_text())
    assert observed['env']['PGHOST']=='/var/run/postgresql'
    assert observed['env']['PGPASSFILE']=='/dev/null'
    assert observed['env']['PGREQUIREAUTH']=='none'
    assert observed['env']['PGUSER']=='local_fixture' and observed['env']['PGDATABASE']=='fixture'
    assert not {'PGPASSWORD','PGSERVICE','HOME','SECRET_SENTINEL'} & observed['env'].keys()
    assert observed['args'][observed['args'].index('-d')+1]=='require_auth=none passfile=/dev/null'
    assert '-X' in observed['args'] and '-w' in observed['args']
    if name=='observe':
        assert "expected_run_id=comprun_quote'fixture" in observed['args']
        assert "WHERE run_id = :'expected_run_id'" in observed['sql']
    assert observed['sql']==(ROOT/('comprehensive_metadata_observation.sql' if name=='observe' else 'terminal_run_discovery.sql')).read_text()
    assert proc.returncode==(0 if psql_exit==0 else 1)
    assert proc.stdout==('observation_transaction_closed\n' if psql_exit==0 else 'observation_failed\n')
    assert proc.stderr==''


def test_additive_diagnostics_preserve_acceptance_and_hide_payload_contents():
    # These are output-contract checks. Actual PostgreSQL behavior is qualified
    # by postgres_comprehensive_observation_proof.py in the existing workflow.
    assert "'projection_count'," in SQL
    assert "'canonical_diagnostics'," in SQL
    for field in ['exact_run_status','artifact_schema','final_stage_completed',
                  'final_stage_status','report_package_object_present','reports_object_present']:
        assert "'"+field+"'" in SQL
    gate = '''WHEN ledger_valid AND run_count=1 AND joined_row_count=1 AND run_metadata_valid
                    AND projection_metadata_bound AND stored_report_manifest_present
                    AND storage_metadata_shape_valid'''
    assert SQL.count(gate)==2  # Original success and digest predicates unchanged.
    discovery=(ROOT/'terminal_run_discovery.sql').read_text()
    assert "'exact_run_status'" in discovery
    assert 'payload ->' not in discovery and 'payload #>' not in discovery
