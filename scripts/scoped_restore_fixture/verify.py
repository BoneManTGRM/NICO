"""Bounded application-code restore read; no bootstrap, installations or database writes."""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import sys
import types
from functools import lru_cache
from collections.abc import Mapping
from typing import Any

ROOT = Path(__file__).resolve().parent
TARGET = 'UNBOUND-NOT-EXECUTABLE'
MAX_OUTPUT = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024

def require(ok, code):
    if not ok:
        raise ValueError(code)

def selected(name, names, namespace):
    tree = ast.parse((ROOT/'source'/f'{name}.py').read_text())
    nodes = []
    found = set()
    for node in tree.body:
        node_name = getattr(node, 'name', None)
        if isinstance(node, ast.Assign):
            node_name = getattr(node.targets[0], 'id', None)
        elif isinstance(node, ast.AnnAssign):
            node_name = getattr(node.target, 'id', None)
        if node_name in names:
            nodes.append(node); found.add(node_name)
    require(found == set(names), 'source_symbol_missing')
    # Exact original AST nodes, including function bodies and decorators.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), name, 'exec'), namespace)

@lru_cache(maxsize=1)
def _load_code():
    manifest = json.loads((ROOT/'source-manifest.json').read_text())
    require(manifest.get('release') == '5eb768b5776f88bae86e972c76267915cc874c85', 'source_release_mismatch')
    expected_paths = {
        'source/comprehensive_orchestration_contract.py', 'source/comprehensive_run_record.py',
        'source/comprehensive_run_storage_chunks_v1.py', 'source/comprehensive_run_storage_codec_v1.py',
        'source/comprehensive_run_storage_dedup_v1.py', 'source/comprehensive_run_store.py',
        'source/decision_grade_human_evidence_v1.py', 'source/report_delivery_timing_v1.py',
        'source/review_pdf_admission_observability_v1.py', 'source/storage_schema_contract_v1.py',
        'source/strategic_human_evidence_v1.py',
    }
    require(set(manifest['files']) == expected_paths, 'source_manifest_scope_mismatch')
    for path, digest in manifest['files'].items():
        file = ROOT/path
        require(not file.is_symlink() and file.is_file() and file.resolve().parent == ROOT/'source',
                'source_manifest_scope_mismatch')
        require(hashlib.sha256(file.read_bytes()).hexdigest() == digest, 'source_hash_mismatch')
    package = types.ModuleType('nico'); package.__path__ = [str(ROOT/'source')]
    sys.modules['nico'] = package  # No production package __init__/installers.
    import nico.report_delivery_timing_v1 as timing
    import nico.comprehensive_run_storage_codec_v1 as codec
    common = {'Any': Any, 'Mapping': Mapping, 'json': json, 'hashlib': hashlib,
              'report_delivery_phase': timing.report_delivery_phase}
    orchestration = dict(common)
    selected('comprehensive_orchestration_contract', ['EXPRESS_STAGES','COMPREHENSIVE_ONLY_STAGES','TERMINAL_STAGES','COMPREHENSIVE_STAGES'], orchestration)
    human = dict(common)
    selected('decision_grade_human_evidence_v1', ['MODULE_DEFINITIONS'], human)
    selected('strategic_human_evidence_v1', ['VERSION','MODULES','_canonical_hash','verify_strategic_human_evidence'], human)
    record = dict(common, COMPREHENSIVE_STAGES=orchestration['COMPREHENSIVE_STAGES'],
                  HUMAN_EVIDENCE_VERSION=human['VERSION'], verify_strategic_human_evidence=human['verify_strategic_human_evidence'])
    selected('comprehensive_run_record', ['VERSION','LEGACY_VERSION','TERMINAL_STATUSES',
        '_HASH_BATCH_BYTES','_HASH_NATIVE_NODE_LIMIT','_HASH_NATIVE_BYTES_LIMIT',
        '_bounded_native_json','_LegacyHashEncodingRequired','_canonical_hash_chunks','_canonical_hash',
        '_record_hash','_validate_record','validate_comprehensive_run_record'], record)
    from nico.review_pdf_admission_observability_v1 import timed
    store = dict(common, timed=timed)
    selected('comprehensive_run_store', ['_review_history','_review_history_sha256','_assert_review_history_commitment'], store)
    return codec, record, store, human

def load_code_offline():
    # Explicit test-only source check; the disabled CLI never reads the package.
    try:
        return _load_code()
    except Exception:
        raise ValueError('offline_source_verification_failed') from None

def validate_row(row, *, expected_scope):
    require(type(expected_scope) is tuple and len(expected_scope)==2 and
            all(type(x) is str and x for x in expected_scope),'application_record_scope_missing')
    require((row.get('customer_id'),row.get('project_id'))==expected_scope,
            'application_record_scope_mismatch')
    CODEC, RECORD, STORE, _ = load_code_offline()
    payload = row['payload']
    if isinstance(payload, str): payload = json.loads(payload)
    require(isinstance(payload, dict), 'payload_not_object')
    envelope = payload.get(CODEC.ENVELOPE_KEY)
    if envelope is not None:
        require(isinstance(envelope, dict) and type(envelope.get('size_bytes')) is int
                and 0 < envelope['size_bytes'] <= MAX_EXPANDED, 'expanded_size_limit')
    record = CODEC.decode_run_storage(payload)
    identity=record.get('identity')
    require(type(identity) is dict and
            (identity.get('customer_id'),identity.get('project_id'))==expected_scope,
            'application_record_scope_mismatch')
    # These exclusions define this bounded sample; never emulate missing review validators.
    require(record.get('status') not in ('approved','rejected')
            and record.get('client_delivery_allowed') is False
            and record.get('review_decision') is None
            and not record.get('review_history')
            and record.get('accepted_edition') is None, 'reviewed_record_outside_verifier_scope')
    require(record.get('artifact_schema') in (RECORD['VERSION'],RECORD['LEGACY_VERSION']), 'unsupported_record_schema')
    STORE['_assert_review_history_commitment'](record, committed_count=row['event_count'],
        committed_sha256=row['chain_sha256'], allow_append=False)
    result = RECORD['validate_comprehensive_run_record'](record)
    require(result['status'] == 'valid', 'application_record_validation_failed')
    require(record['identity']['run_id'] == row['run_id']
            and record['revision'] == row['revision']
            and record['integrity_sha256'] == row['integrity_sha256'], 'column_record_identity_mismatch')
    return [row['run_id'],row['revision'],row['integrity_sha256'],row['event_count'],row['chain_sha256']]

def verify_synthetic_snapshot(snapshot, *, expected_scope):
    require(snapshot.get('read_only') == 'on','transaction_not_readonly')
    expected=json.loads((ROOT/'expected-schema.json').read_text())
    catalog={}
    for row in snapshot['schema'] or []: catalog.setdefault(row['table'],set()).add(row['column'])
    for table, columns in expected['tables'].items():
        require(set(columns)<=catalog.get(table,set()),'required_schema_missing')
    require(any(x['version']==expected['version'] and x['contract_sha256']==expected['contract_sha256']
                for x in snapshot['migrations'] or []),'schema_ledger_mismatch')
    rows=snapshot['rows'] or []
    require(1<=len(rows)<=3,'bounded_sample_unavailable')
    for row in rows:
        validate_row(row,expected_scope=expected_scope)
    # This cannot generate registration fields, an unbound digest or a passed
    # production result. A future connector and evidence assembler must be separate.
    return {'status':'synthetic_only', 'sample_count':len(rows),
            'database_execution_enabled':False, 'restore_evidence_eligible':False}

def local_psql_command(parent):
    user=parent.get('POSTGRES_USER') or parent.get('PGUSER')
    database=parent.get('POSTGRES_DB') or parent.get('PGDATABASE')
    require(bool(user and database),'local_database_identity_missing')
    # libpq treats dbname values containing '=' or a URI prefix as connection
    # strings; a strict ASCII identifier disallows that entire interpretation.
    for value in (user, database):
        require(isinstance(value,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}',value) is not None,
                'local_database_identity_invalid')
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGCONNECT_TIMEOUT':'5',
         'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=1000',
         'PGPASSFILE':'/nonexistent/nico-restore-no-password-file'}
    # Explicit allowlist: never inherit PGHOST/PGHOSTADDR/PGSERVICE/PGSERVICEFILE,
    # PGOPTIONS/PGPASSWORD/HOME/LD_PRELOAD or any other ambient connection setting.
    cmd=['/usr/bin/psql','-X','-w','-q','-A','-t','-v','ON_ERROR_STOP=1','-h','/var/run/postgresql','-p','5432','-U',user,'-d',database]
    return cmd,env

def require_bound_target(parent, arguments):
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', TARGET) is not None, 'target_unbound')
    require(arguments == ['--confirmed-target', TARGET], 'target_confirmation_required')
    require(isinstance(parent.get('RAILWAY_SERVICE_ID'), str) and bool(parent['RAILWAY_SERVICE_ID']), 'service_identity_missing')
    require(parent['RAILWAY_SERVICE_ID'] == TARGET, 'service_identity_mismatch')

def run():
    require_bound_target(os.environ, sys.argv[1:])
    raise ValueError('execution_disabled_preflight_only')

if __name__=='__main__':
    try:
        resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(60,60))
        run()
    except Exception as exc:
        # Never emit raw SQL errors, record content, connection details or traceback.
        code=str(exc) if isinstance(exc,ValueError) and str(exc) in (
            'target_unbound','execution_disabled_preflight_only','service_identity_missing','target_confirmation_required','service_identity_mismatch','local_database_identity_missing',
            'local_database_identity_invalid','local_readonly_psql_failed','query_output_limit','required_schema_missing','schema_ledger_mismatch',
            'bounded_sample_unavailable','reviewed_record_outside_verifier_scope','application_record_validation_failed',
            'column_record_identity_mismatch','expanded_size_limit','transaction_not_readonly') else 'verification_failed'
        print(json.dumps({'status':'failed','code':code}));sys.exit(1)
