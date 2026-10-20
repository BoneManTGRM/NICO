from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import sqlite3

from fastapi import FastAPI
import pytest

from nico.comprehensive_native_providers import architecture_data_flow_provider
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY, build_production_capability_executors
from nico.comprehensive_run_record import _record_hash
from nico.source_function_collection_v1 import KEY_COLLECTION, collect_contract
from nico.source_function_conformance_v1 import KEY as RESULT_KEY, build_conformance
from nico.source_function_measurements_v1 import KEY, _aggregate, _dimension, _hash, _json
from nico.source_function_witness_v1 import STORE_STATE_KEY, load_witness, _Witness
from source_function_witness_fixture import persisted
from test_source_function_measurement_report_v1 import collected


def fixture(monkeypatch,tmp_path):
    inputs=collected(monkeypatch,tmp_path,text='def f(x):\n'+'    if x: pass\n'*20+'    return 0\n')
    store,path,witness=persisted(*inputs,tmp_path)
    assert witness is not None
    return inputs,store,path,witness


def edit_payload(path, run_id, mutate, *, repair_hash=False, repair_column=False):
    with sqlite3.connect(path) as connection:
        payload=json.loads(connection.execute('SELECT payload FROM nico_comprehensive_runs WHERE run_id=?',(run_id,)).fetchone()[0])
        mutate(payload)
        if repair_hash:
            payload['integrity_sha256']=_record_hash(payload)
        connection.execute('UPDATE nico_comprehensive_runs SET payload=? WHERE run_id=?',(json.dumps(payload),run_id))
        if repair_column:
            connection.execute('UPDATE nico_comprehensive_runs SET integrity_sha256=? WHERE run_id=?',(payload['integrity_sha256'],run_id))


def test_collection_recomputes_from_full_parser_records(monkeypatch,tmp_path):
    from nico.full_assessment_complexity_evidence import _analyze_python
    from nico.source_function_measurements_v1 import build_measurements
    files={'a.py':'def f(x):\n    if x: return 1\n    return 0\n'}
    analyses=[_analyze_python('a.py',files['a.py'])]
    value=build_measurements(files,analyses,{})
    value['files'][0]['metrics']['cc']=_dimension({'1':1},'cc')
    value['aggregate']=_aggregate(value['files'])
    with pytest.raises(ValueError,match='reconciliation'):
        collect_contract(files,analyses,{},value)
    value=build_measurements(files,analyses,{})
    value['producer_source_sha256']={key:'f'*64 for key in value['producer_source_sha256']}
    with pytest.raises(ValueError,match='reconciliation'):
        collect_contract(files,analyses,{},value)


def test_server_executor_reloads_reference_and_ignores_context_proofs(monkeypatch,tmp_path):
    inputs,store,path,_=fixture(monkeypatch,tmp_path)
    context,repo,complexity=inputs
    app=FastAPI()
    setattr(app.state,STORE_STATE_KEY,store)
    setattr(app.state,PROVIDER_STATE_KEY,{'architecture_data_flow':architecture_data_flow_provider})
    executors=build_production_capability_executors(app)
    from nico.comprehensive_runtime import configure_comprehensive_runtime
    configure_comprehensive_runtime(app,capability_executors=executors,connection_factory=lambda:sqlite3.connect(path),dialect='sqlite')
    execute=executors['architecture_data_flow']
    output=execute(context)['evidence'][RESULT_KEY]
    assert output['status']=='qualified'
    assert output['combined']['cc']['percentage']==0.0
    malicious=deepcopy(context)
    value=malicious['prior_stage_results']['repository_and_delivery_evidence']['complexity_evidence']
    value[KEY]['files'][0]['metrics']['cc']=_dimension({'1':1},'cc')
    value[KEY]['aggregate']=_aggregate(value[KEY]['files'])
    value[KEY_COLLECTION]['measurement_sha256']=_hash(_json(value[KEY]))
    malicious.update(witness={'verified':True}, trusted_store=store, connection_factory=lambda: pytest.fail('caller factory invoked'))
    assert execute(malicious)['evidence'][RESULT_KEY]['status']=='unavailable'
    setattr(app.state,STORE_STATE_KEY,None)
    assert execute(context)['evidence'][RESULT_KEY]['status']=='unavailable'


def test_compressed_storage_collection_save_reload(monkeypatch,tmp_path):
    from nico.comprehensive_run_storage_codec_v1 import COMPRESSION_THRESHOLD_BYTES, ENVELOPE_KEY

    context,repo,complexity=collected(monkeypatch,tmp_path)
    # Real save() crosses the production threshold; no codec or threshold stub.
    context['prior_stage_results'].setdefault('authorization_and_scope',{})['retained_test_payload']='x'*(COMPRESSION_THRESHOLD_BYTES+1)
    store,path,_=persisted(context,repo,complexity,tmp_path)
    with sqlite3.connect(path) as connection:
        encoded=json.loads(connection.execute('SELECT payload FROM nico_comprehensive_runs').fetchone()[0])
    assert ENVELOPE_KEY in encoded
    restored=store.load(context['run_id'])
    assert restored['stage_results']['repository_and_delivery_evidence']['complexity_evidence']==complexity
    witness=load_witness(store,context)
    assert witness is not None
    app=FastAPI()
    setattr(app.state,STORE_STATE_KEY,store)
    setattr(app.state,PROVIDER_STATE_KEY,{'architecture_data_flow':architecture_data_flow_provider})
    output=build_production_capability_executors(app)['architecture_data_flow'](context)['evidence'][RESULT_KEY]
    assert output['status']=='qualified'
    assert output['combined']['cc']['percentage']==100.0
    # Row identity must still agree with the decoded canonical record.
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE nico_comprehensive_runs SET customer_id='foreign'")
    assert load_witness(store,context) is None


@pytest.mark.parametrize('fake',[None,{}, {'verified':True}, {'binding':'fake'}, True])
def test_fake_witnesses_cannot_qualify(monkeypatch,tmp_path,fake):
    inputs,_,_,_=fixture(monkeypatch,tmp_path)
    assert build_conformance(*inputs,witness=fake)['status']=='unavailable'
    with pytest.raises(TypeError):
        build_conformance(*inputs,store={'verified':True})
    with pytest.raises(TypeError):
        _Witness('fake',object())


def test_missing_commitment_is_read_only_and_skips_restore(monkeypatch,tmp_path):
    inputs,store,path,_=fixture(monkeypatch,tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute('DELETE FROM nico_comprehensive_review_history_commitments')
    statements=[]
    def traced():
        connection=sqlite3.connect(path)
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(store,'_connection_factory',traced)
    import nico.comprehensive_run_store as module
    monkeypatch.setattr(module,'restore_comprehensive_run_record',lambda _:pytest.fail('restore called without commitment'))
    assert load_witness(store,inputs[0]) is None
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','REPLACE')) for s in statements)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM nico_comprehensive_review_history_commitments').fetchone()[0]==0


@pytest.mark.parametrize('column,value',[('run_id','foreign'),('customer_id','foreign'),('project_id','foreign'),('repository','foreign'),('commit_sha','b'*40),('evidence_ledger_id','foreign'),('status','failed'),('revision',999),('integrity_sha256','f'*64),('updated_at','foreign'),('terminal',1)])
def test_same_snapshot_row_mismatches_fail(monkeypatch,tmp_path,column,value):
    inputs,store,path,_=fixture(monkeypatch,tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(f'UPDATE nico_comprehensive_runs SET {column}=?',(value,))
    assert load_witness(store,inputs[0]) is None


@pytest.mark.parametrize('damage',['corrupt','rehashed','legacy','bad_contract','missing_stage','bad_history','malformed_json'])
def test_invalid_persisted_records_fail(monkeypatch,tmp_path,damage):
    inputs,store,path,_=fixture(monkeypatch,tmp_path)
    run_id=inputs[0]['run_id']
    if damage=='bad_history':
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE nico_comprehensive_review_history_commitments SET chain_sha256=?",('f'*64,))
    elif damage=='malformed_json':
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE nico_comprehensive_runs SET payload='{' ")
    else:
        def mutate(payload):
            stages=payload['stage_results']
            if damage=='missing_stage': stages.pop('repository_and_delivery_evidence')
            else:
                evidence=stages['repository_and_delivery_evidence']['complexity_evidence']
                if damage=='legacy': evidence.pop(KEY_COLLECTION)
                elif damage=='bad_contract': evidence[KEY_COLLECTION]['version']='foreign'
                else: evidence[KEY]['producer_source_sha256']={key:'f'*64 for key in evidence[KEY]['producer_source_sha256']}
        edit_payload(path,run_id,mutate,repair_hash=damage!='corrupt',repair_column=damage in {'legacy','bad_contract','missing_stage'})
    assert load_witness(store,inputs[0]) is None


def test_later_revision_and_defensive_copy_isolation(monkeypatch,tmp_path):
    inputs,store,_,witness=fixture(monkeypatch,tmp_path)
    context,repo,complexity=inputs
    old=deepcopy(inputs)
    record=store.load(context['run_id'])
    revision=record['revision']
    record['revision']+=1
    record['integrity_sha256']=_record_hash(record)
    store.save(record,expected_revision=revision)
    later=load_witness(store,{**context,'revision':revision})
    assert build_conformance(*inputs,witness=later)['status']=='qualified'
    with pytest.raises(FrozenInstanceError): witness.binding='changed'
    complexity[KEY]['files'][0]['metrics']['cc']=_dimension({'1':1},'cc')
    assert build_conformance(*inputs,witness=witness)['status']=='unavailable'
    assert build_conformance(*old,witness=witness)['status']=='qualified'
    assert load_witness(store,old[0]).binding==witness.binding
    assert load_witness(store,{**old[0],'customer_id':'foreign'}) is None


def test_unavailable_store_does_not_fail_existing_report(monkeypatch,tmp_path):
    inputs,store,_,_=fixture(monkeypatch,tmp_path)
    def unavailable(): raise RuntimeError('unavailable')
    monkeypatch.setattr(store,'_connection_factory',unavailable)
    assert load_witness(store,inputs[0]) is None


@pytest.mark.parametrize('field,bad',[('lfs_pointer_entries',{}),('submodule_entries','malformed'),('lfs_pointer_entries',[{'path':'assets/x','oid':'sha256:'+'a'*64,'size_bytes':True}]),('submodule_entries',[{'path':'../foreign','commit_sha':'a'*40}])])
def test_trusted_copy_does_not_bypass_coverage_validation(monkeypatch,tmp_path,field,bad):
    inputs,_,_,_=fixture(monkeypatch,tmp_path)
    context,repo,complexity=inputs
    complexity['profile_coverage'][field]=deepcopy(bad)
    repo['file_evidence']['profile_coverage'][field]=deepcopy(bad)
    _,_,witness=persisted(*inputs,tmp_path)
    assert witness is not None
    assert build_conformance(*inputs,witness=witness)['status']=='unavailable'


def test_optional_contract_rejection_preserves_legacy_collection(monkeypatch):
    from nico import typescript_ast_complexity_v1 as collector
    from nico import source_function_collection_v1 as contracts
    files={'a.py':'def f(): return 0'}
    original=collector._build_complexity(files)
    original.pop(KEY_COLLECTION)
    def rejected(*args): raise ValueError('inconsistent_optional_proof')
    monkeypatch.setattr(contracts,'collect_contract',rejected)
    assert collector._build_complexity(files)==original
