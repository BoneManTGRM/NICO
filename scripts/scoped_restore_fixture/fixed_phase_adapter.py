"""Small fixed-phase acceptance adapter for synthetic psql streams, no live I/O."""
from copy import deepcopy
from enum import Enum, auto
from functools import cache
import hashlib
import json
import re
from pathlib import Path

from no_child_design import BEGIN_STMT, END_STMT, READY_STMT
from offline_read_runner import (CONTRACT, EXTRA_TABLE, RUN_TABLE, SUPPLEMENTAL, MAX_ROW, MAX_TRANSCRIPT,
                                 METADATA_MAX, SCHEMA, SyntheticTranscript,
                                 handle_obj, verify_fixture)
from binding import derive_synthetic_transport_binding, validate_read_scope, SCOPE_ID
from no_child_design import RELEASE

ROOT=Path(__file__).resolve().parent
READ_TYPES={
    'nico_schema_migrations':{'version':'text','contract_sha256':'text'},
    RUN_TABLE:{'run_id':'text','customer_id':'text','project_id':'text','revision':'int4','integrity_sha256':'text',
                               'status':'text','payload':'jsonb'},
    EXTRA_TABLE:{'run_id':'text','event_count':'int4','chain_sha256':'text'},
}
IDENT=re.compile(r'[a-z_][a-z0-9_]{0,62}\Z')

class Phase(Enum):
    BOOTSTRAP=auto()
    CATALOG=auto()
    LEDGER=auto()
    SAMPLE=auto()
    ROLLBACK=auto()

def require(good,code):
    if not good:
        raise ValueError(code)

@cache
def _expected():
    expected=handle_obj((ROOT/'expected-schema.json').read_bytes(),METADATA_MAX)
    declared=expected.pop('contract_sha256')
    encoded=json.dumps(expected,ensure_ascii=True,allow_nan=False,sort_keys=True,
                       separators=(',',':')).encode()
    require(declared==CONTRACT and hashlib.sha256(encoded).hexdigest()==CONTRACT
            and SCHEMA=='public','source_schema_mismatch')
    return expected

def _fixed_sql(scope):
    require(type(scope) is tuple and len(scope)==2 and
            all(type(x) is str and SCOPE_ID.fullmatch(x) and x.casefold() not in ('all','any','unbound') for x in scope),
            'fixture_read_scope_invalid')
    customer,project=scope
    expected=_expected()
    tables=sorted(set(expected['tables']) | set(SUPPLEMENTAL))
    require(all(IDENT.fullmatch(x) for x in tables),'source_schema_mismatch')
    exact_names=','.join("'" + x + "'" for x in tables)
    # No data table is resolved or read until catalog phase passes. SQL is
    # fixed from verified source metadata: not from the binding or transcript.
    common_catalog=("SELECT pg_catalog.json_build_object('schema','public','tables',"
        "COALESCE(pg_catalog.json_object_agg(q.relname,"
        "pg_catalog.json_build_object('kind',q.kind,'columns',q.columns,'types',q.types)),'{}'::pg_catalog.json)) "
        "FROM (SELECT c.relname,CASE WHEN c.relkind='r' AND c.relpersistence='p' "
        "THEN 'base_table' ELSE 'unsupported' END AS kind,"
        "pg_catalog.json_agg(a.attname ORDER BY a.attnum) AS columns,pg_catalog.json_object_agg(a.attname,CASE WHEN tn.nspname='pg_catalog' THEN t.typname ELSE 'unsupported' END) AS types "
        "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace "
        "WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped "
        "AND c.relname IN ("+exact_names+") GROUP BY c.relname,c.relkind,c.relpersistence) q;")
    ledger=("SELECT pg_catalog.json_build_object('migrations',COALESCE(pg_catalog.json_agg("
        "pg_catalog.json_build_object('version',v.version,'contract_sha256',v.contract_sha256)),"
        "'[]'::pg_catalog.json)) FROM (SELECT version,contract_sha256 FROM ONLY "
        "public.nico_schema_migrations WHERE version='2026.09.08.1' LIMIT 2) v;")
    # Single fixed scope. The live selector still needs explicit approval of
    # data scope on the isolated target. A repeatable-read transaction alone
    # does not prove no DDL identity swap; target access controls remain needed.
    sample=("SELECT pg_catalog.json_build_object('row',pg_catalog.row_to_json(q)) FROM "
        "(SELECT r.run_id,r.customer_id,r.project_id,r.revision,r.integrity_sha256,c.event_count,c.chain_sha256,"
        "CASE WHEN pg_catalog.octet_length(r.payload::pg_catalog.text)<=4000000 "
        "THEN r.payload ELSE NULL END AS payload "
        "FROM ONLY public.nico_comprehensive_runs AS r JOIN ONLY "
        "public.nico_comprehensive_review_history_commitments AS c ON c.run_id=r.run_id "
        'WHERE r.customer_id COLLATE pg_catalog."C" = ' + "'" + customer + "'::pg_catalog.text "
        'AND r.project_id COLLATE pg_catalog."C" = ' + "'" + project + "'::pg_catalog.text "
        "AND c.event_count=0 AND c.chain_sha256 IS NOT NULL "
        "AND r.status NOT IN ('approved','rejected') AND pg_catalog.pg_column_size(r.payload)<=4000000 "
        "ORDER BY r.run_id LIMIT 3) q;")
    # Bootstrap display is fixed SQL only; this fixture adapter does not
    # implement actual psql stdout tagging or selectors.
    return ((BEGIN_STMT+'; '+READY_STMT+';',common_catalog,ledger,sample,END_STMT+';'),set(tables))

def _run_fixture(fake, plan, observed, *, now, max_age_hours):
    digest=derive_synthetic_transport_binding(plan,observed,now=now,max_age_hours=max_age_hours)
    sql, names=_fixed_sql(validate_read_scope(plan['approved_read_scope']))
    token='fixture:fixed-phase-adapter'
    size=0
    started=False
    def request_bytes(phase, limit):
        nonlocal size,started
        started=True
        chunk=fake.response(phase,sql[phase.value-1])
        require(type(chunk) is bytes and len(chunk)<=limit,'fixture_input_bound')
        size+=len(chunk)
        require(size<=MAX_TRANSCRIPT,'fixture_input_bound')
        return chunk
    def request(phase, limit):
        return handle_obj(request_bytes(phase,limit),limit)
    def frame(phase,**values):
        return json.dumps(dict(fixture_token=token,phase=phase,**values),
                          ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
    try:
        from no_child_design import verify_fixture_bootstrap
        boot=request(Phase.BOOTSTRAP,METADATA_MAX)
        require(set(boot)=={'values','status','transaction_status'} and type(boot['values']) is list,
                'fixture_session_invalid')
        verify_fixture_bootstrap(tuple(boot['values']),session_status=boot['status'],
                                 transaction_status=boot['transaction_status'])
        catalog=request(Phase.CATALOG,METADATA_MAX)
        require(set(catalog)=={'schema','tables'} and catalog['schema']==SCHEMA and
                type(catalog['tables']) is dict and set(catalog['tables'])==names and
                all(type(x) is dict and x.get('kind')=='base_table' for x in catalog['tables'].values()),
                'fixture_relation_unverified')
        expected=_expected()
        for name,picked in catalog['tables'].items():
            require(set(picked)=={'kind','columns','types'} and type(picked['columns']) is list and
                    all(type(x) is str for x in picked['columns']) and type(picked['types']) is dict,
                    'fixture_catalog_invalid')
            required=set(expected['tables'].get(name,())) | SUPPLEMENTAL.get(name,set())
            require(required<=set(picked['columns']) and all(picked['types'].get(k)==v
                        for k,v in READ_TYPES.get(name,{}).items()),'fixture_relation_unverified')
        ledger=request(Phase.LEDGER,METADATA_MAX)
        require(set(ledger)=={'migrations'},'fixture_ledger_invalid')
        from offline_read_runner import _shape
        metadata={'schema':catalog['schema'], 'migrations':ledger['migrations'],
                  'tables':{k:{'kind':v['kind'],'columns':v['columns']} for k,v in catalog['tables'].items()}}
        _shape(metadata)
        # Each fixed SELECT result row is one raw newline-terminated JSON object,
        # not an invented array envelope. Terminal/session framing still needs an
        # independently qualified real transport.
        sample=request_bytes(Phase.SAMPLE,MAX_TRANSCRIPT)
        require(sample.endswith(b'\n') and sample.count(b'\n') in (1,2,3),
                'fixture_sample_invalid')
        rows=[handle_obj(line,MAX_ROW) for line in sample[:-1].split(b'\n')]
        require(all(set(x)=={'row'} for x in rows),'fixture_sample_invalid')
        sample_frames=[frame('sample',row=x['row']) for x in rows]
        require(all(len(x)<=MAX_ROW for x in sample_frames),'fixture_input_bound')
        end=request(Phase.ROLLBACK,METADATA_MAX)
        require(end=={'completed':True} and end['completed'] is True,'fixture_transaction_not_closed')
        transcript=SyntheticTranscript(token,RELEASE,digest,
            tuple([frame('bootstrap',session=boot),frame('catalog_and_ledger',metadata=metadata),
                   *sample_frames,frame('rollback',completed=True)]))
        return verify_fixture(transcript,plan,observed,now=now,max_age_hours=max_age_hours)
    except Exception:
        if started:
            try:
                require(fake.close_fixture() is True,'fixture_cleanup_unverified')
            except Exception:
                raise ValueError('fixture_cleanup_unverified') from None
        raise

def validate_fixture(fake, plan, observed, *, now, max_age_hours):
    # fake has no implementation in this package aside from test classes.
    try:
        return _run_fixture(fake,deepcopy(plan),deepcopy(observed),now=now,max_age_hours=max_age_hours)
    except Exception:
        raise ValueError('fixed_phase_fixture_rejected') from None

def dispatch():
    raise ValueError('database_execution_disabled')
