"""Real local SQLite persistence for collection/witness tests; no verified flags."""
from copy import deepcopy
import sqlite3
from uuid import uuid4

from nico.comprehensive_run_record import create_comprehensive_run_record, apply_comprehensive_stage_result
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.source_function_witness_v1 import load_witness


def persisted(context, repository, complexity, tmp_path):
    # Keep verifier storage outside checkout fixtures that inventory tmp_path.
    state = tmp_path.parent / 'function-witness-state'
    state.mkdir(exist_ok=True)
    database = state / f'function-witness-{uuid4().hex}.sqlite'
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database), dialect='sqlite')
    store.ensure_schema()
    record = create_comprehensive_run_record(**{k:context[k] for k in (
        'run_id','repository','commit_sha','evidence_ledger_id','customer_id','project_id')}, authorized=True)
    record = store.create(record)
    results = deepcopy(context['prior_stage_results'])
    results['repository_and_delivery_evidence'] = {'repository_evidence':deepcopy(repository), 'complexity_evidence':deepcopy(complexity)}
    for stage in COMPREHENSIVE_STAGES:
        previous = record['revision']
        record = apply_comprehensive_stage_result(record, stage_id=stage, result={'status':'complete', **results.get(stage,{})})
        record = store.save(record, expected_revision=previous)
        if stage == 'repository_and_delivery_evidence':
            break
    return store, database, load_witness(store,context)


def bind_fixture_witness(monkeypatch, tmp_path, context, repository, complexity):
    from nico import source_function_witness_v1 as module
    store, database, witness = persisted(context,repository,complexity,tmp_path)
    from contextvars import ContextVar
    monkeypatch.setattr(module,'_CURRENT',ContextVar('test_collection_witness',default=witness))
    return store,database,witness


def persist_parser_population(monkeypatch, tmp_path, inputs, files, analyses, ast_result):
    """A new synthetic collection, never a mutation of an existing trusted snapshot."""
    from nico.source_function_measurements_v1 import KEY, build_measurements, bind_measurements
    from nico.source_function_collection_v1 import KEY_COLLECTION, collect_contract, bind_collection
    context,repo,complexity=inputs
    measurement=build_measurements(files,analyses,ast_result)
    complexity[KEY]=measurement
    complexity[KEY_COLLECTION]=collect_contract(files,analyses,ast_result,measurement)
    bind_measurements(complexity)
    bind_collection(complexity)
    return bind_fixture_witness(monkeypatch,tmp_path,context,repo,complexity)


def architecture_from_persisted(context, repository, complexity, tmp_path):
    from fastapi import FastAPI
    from nico.comprehensive_native_providers import architecture_data_flow_provider
    from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY, build_production_capability_executors
    from nico.source_function_witness_v1 import STORE_STATE_KEY
    store,_,_=persisted(context,repository,complexity,tmp_path)
    app=FastAPI()
    setattr(app.state,STORE_STATE_KEY,store)
    setattr(app.state,PROVIDER_STATE_KEY,{'architecture_data_flow':architecture_data_flow_provider})
    return build_production_capability_executors(app)['architecture_data_flow'](context)
