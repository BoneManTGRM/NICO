"""Staged read verification over an explicit fixture, with no live entrypoint.

This module intentionally has no psql/subprocess/libpq/socket launcher, no
generic SQL input, and no facility to register restoration evidence.
"""
from dataclasses import dataclass
import json
import math
import re
from pathlib import Path

import verify
from no_child_design import RELEASE, verify_fixture_bootstrap
from binding import derive_synthetic_transport_binding, validate_read_scope

ROOT=Path(__file__).resolve().parent
MAX_TRANSCRIPT=16*1024*1024
MAX_ROW=4*1024*1024
METADATA_MAX=1024*1024
SCHEMA='public'
CONTRACT='8ab54b42689aa75fdb3bd40ca4582491eaf585ac6a7c73117cb7d9d200d5e534'
SHA=re.compile(r'[a-f0-9]{64}\Z')
TOKEN=re.compile(r'fixture:[a-z0-9-]{1,48}\Z')
EXTRA_TABLE='nico_comprehensive_review_history_commitments'
EXPECTED_EXTRA={'run_id','event_count','chain_sha256'}
RUN_TABLE='nico_comprehensive_runs'
EXPECTED_RUN={'run_id','customer_id','project_id','revision','integrity_sha256','status','payload'}
SUPPLEMENTAL={EXTRA_TABLE:EXPECTED_EXTRA,RUN_TABLE:EXPECTED_RUN}

def require(good,code):
    if not good: raise ValueError(code)

def unique_pairs(pairs):
    values={}
    for k,v in pairs:
        require(k not in values,'fixture_duplicate_field')
        values[k]=v
    return values

def invalid_constant(_):
    raise ValueError('fixture_bad_number')

def finite_float(raw):
    value=float(raw)
    require(math.isfinite(value),'fixture_bad_number')
    return value

def handle_obj(raw, limit):
    require(type(raw) is bytes and 0<len(raw)<=limit,'fixture_input_bound')
    try:
        obj=json.loads(raw.decode('utf-8','strict'),object_pairs_hook=unique_pairs,
                       parse_constant=invalid_constant,parse_float=finite_float)
    except Exception:
        raise ValueError('fixture_invalid_json') from None
    require(type(obj) is dict,'fixture_shape_invalid')
    return obj

@dataclass(frozen=True)
class SyntheticTranscript:
    """Saved synthetic transcript, not a transport or pre-observed real result."""
    fixture_token: str
    release: str
    binding_digest: str
    records: tuple

def _shape(metadata):
    expected=json.loads((ROOT/'expected-schema.json').read_text())
    require(expected['contract_sha256']==CONTRACT,'fixture_schema_contract_mismatch')
    require(type(metadata) is dict and set(metadata)=={'schema','tables','migrations'},
            'fixture_catalog_invalid')
    require(metadata['schema']==SCHEMA,'fixture_catalog_invalid')
    tables=metadata['tables']
    expected_names=set(expected['tables'])|set(SUPPLEMENTAL)
    require(type(tables) is dict and set(tables)==expected_names,'fixture_catalog_invalid')
    for name in expected_names:
        desc=tables[name]
        require(type(desc) is dict and set(desc)=={'kind','columns'} and desc['kind']=='base_table',
                'fixture_relation_unverified')
        cols=desc['columns']
        require(type(cols) is list and len(cols)<=256 and all(type(x) is str and len(x)<=63 for x in cols),
                'fixture_catalog_invalid')
        required=set(expected['tables'].get(name,())) | SUPPLEMENTAL.get(name,set())
        require(len(set(cols))==len(cols) and required<=set(cols),'fixture_required_columns_missing')
    migrations=metadata['migrations']
    require(type(migrations) is list and len(migrations)==1,'fixture_schema_ledger_mismatch')
    require(migrations[0]=={'version':expected['version'],'contract_sha256':CONTRACT},
            'fixture_schema_ledger_mismatch')

def _execute_fixture(transcript, plan, observed, *, now, max_age_hours):
    # Missing/replaced/stale provider lineage is rejected before reading fixture frames.
    expected_digest=derive_synthetic_transport_binding(plan,observed,now=now,max_age_hours=max_age_hours)
    require(type(transcript) is SyntheticTranscript and type(transcript.fixture_token) is str and
            TOKEN.fullmatch(transcript.fixture_token) and transcript.release==RELEASE and
            transcript.binding_digest==expected_digest,'fixture_identity_mismatch')
    scope=validate_read_scope(plan['approved_read_scope'])
    frames=transcript.records
    require(type(frames) is tuple and 4<=len(frames)<=6 and
            all(type(f) is bytes for f in frames) and sum(map(len,frames))<=MAX_TRANSCRIPT,
            'fixture_input_bound')
    def phase(i,label,expected_key,max_size=METADATA_MAX):
        packet=handle_obj(frames[i],max_size)
        require(set(packet)=={'fixture_token','phase',expected_key} and
                packet['fixture_token']==transcript.fixture_token and packet['phase']==label,
                'fixture_phase_mismatch')
        return packet[expected_key]
    boot=phase(0,'bootstrap','session')
    require(type(boot) is dict and set(boot)=={'values','status','transaction_status'} and
            type(boot['values']) is list,'fixture_session_shape_invalid')
    verify_fixture_bootstrap(tuple(boot['values']),session_status=boot['status'],
                             transaction_status=boot['transaction_status'])
    _shape(phase(1,'catalog_and_ledger','metadata'))
    identities=set()
    for i in range(2,len(frames)-1):
        row=phase(i,'sample','row',MAX_ROW)
        require(type(row) is dict and set(row)=={'payload','run_id','revision','integrity_sha256','event_count','chain_sha256','customer_id','project_id'},
                'fixture_sample_invalid')
        require(type(row['run_id']) is str and 1<=len(row['run_id'])<=256 and row['run_id'] not in identities and
                type(row['revision']) is int and row['revision']>=1 and type(row['event_count']) is int and
                row['event_count']==0 and all(type(row[x]) is str and SHA.fullmatch(row[x])
                                                for x in ('integrity_sha256','chain_sha256')),
                'fixture_sample_invalid')
        require((row['customer_id'],row['project_id'])==scope,'fixture_sample_scope_mismatch')
        verify.validate_row(row,expected_scope=scope)
        identities.add(row['run_id'])
    require(phase(len(frames)-1,'rollback','completed') is True,'fixture_transaction_not_closed')
    return {'status':'synthetic_only','sample_count':len(identities),
            'database_execution_enabled':False,'restore_evidence_eligible':False}

def verify_fixture(transcript, plan, observed, *, now, max_age_hours):
    try:
        return _execute_fixture(transcript,plan,observed,now=now,max_age_hours=max_age_hours)
    except Exception:
        # Do not expose supplied identities, rows, native/runtime messages or trace chains.
        raise ValueError('offline_read_fixture_rejected') from None

def dispatch():
    raise ValueError('database_execution_disabled')
