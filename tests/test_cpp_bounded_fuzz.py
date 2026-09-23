"""Bounded-fuzz contract tests. Synthetic receipts do not establish execution."""
from copy import deepcopy
import pytest
from nico.assessment_cpp_fuzz import fuzz_plan, validate_plan, target_arguments


def targets():
    return {'corpus/seed': 'a' * 64, 'fuzz.cpp': 'b' * 64}


def plan():
    return fuzz_plan(build_targets=['fuzz_control'], cmake_options={'NICO_FUZZ_ONLY': 'ON'},
        targets=[{'name': 'control', 'binary': 'fuzz_control', 'corpus': ['corpus/seed'], 'environment': {}}],
        runs=128, seconds=2, seed=7)


def test_frozen_fuzz_plan_rejects_unbounded_defaults_and_retains_exact_sources():
    p = plan()
    assert validate_plan(p, targets()) == p
    argv = target_arguments(p, 0, phase='campaign')
    assert '-runs=128' in argv and '-max_total_time=2' in argv
    assert '-seed=7' in argv and '-timeout=1' in argv
    assert '-jobs=0' in argv and '-fork=0' in argv


@pytest.mark.parametrize('field,value', [('runs', -1), ('runs', True), ('seconds', 0),
    ('seconds', 11), ('seed', 0), ('seed', False), ('max_len', 4097), ('rss_limit_mb', 0)])
def test_unbounded_or_malformed_budget_is_rejected(field, value):
    p = plan(); p[field] = value
    with pytest.raises(ValueError): validate_plan(p, targets())


@pytest.mark.parametrize('mutation', ['path', 'corpus', 'env', 'target', 'option', 'duplicate'])
def test_unbound_inputs_or_execution_overrides_are_rejected(mutation):
    p = plan()
    if mutation == 'path': p['targets'][0]['binary'] = '../escape'
    elif mutation == 'corpus': p['targets'][0]['corpus'] = ['absent']
    elif mutation == 'env': p['targets'][0]['environment'] = {'LD_PRELOAD': 'bad'}
    elif mutation == 'target': p['build_targets'] = ['--help']
    elif mutation == 'option': p['cmake_options'] = {'CMAKE_CXX_COMPILER': 'bad'}
    else: p['targets'].append(deepcopy(p['targets'][0]))
    with pytest.raises(ValueError): validate_plan(p, targets())


def test_corpus_replay_is_distinct_from_a_campaign():
    p = plan()
    argv = target_arguments(p, 0, phase='replay', seed_index=0)
    assert argv[-1] == '/work/fuzz-snapshots/t0/s0'
    assert '-runs=1' in argv
    assert '/work/fuzz-runs/t0-campaign/corpus' not in argv


import base64
import hashlib
import json
from nico.assessment_cpp_fuzz_runtime import run_fuzz
from nico.assessment_cpp_fuzz import validate_evidence


class Commands:
    """Synthetic Docker transport: no command is run by this test double."""
    def __init__(self, *, negative=False, interrupted=False, no_symbols=False, changed=False, silent=False):
        self.negative=negative;self.interrupted=interrupted;self.no_symbols=no_symbols
        self.changed=changed;self.silent=silent;self.calls=[]
        self.snapshot={'t0':{'path':'/work/fuzz-snapshots/t0/program','sha256':'e'*64,'bytes':1024,
            'uid':0,'mode':0o555,'corpus':{'corpus/seed':{'sha256':'a'*64,'bytes':1}}}}

    def __call__(self,args,*,data=None,**kwargs):
        from nico.assessment_cpp_fuzz_runtime import SNAPSHOT_PROGRAM, INSPECT_PROGRAM, VERIFY_PROGRAM, ARTIFACT_PROGRAM
        from nico.assessment_cpp_native_tests import PROBE_PROGRAM
        self.calls.append(args);code=0;timeout=False
        if SNAPSHOT_PROGRAM in args:
            assert '--user=0:0' in args
            assert json.loads(data)['hashes']=={'corpus/seed':'a'*64}
            out=json.dumps(self.snapshot).encode()
        elif INSPECT_PROGRAM in args:
            assert '--user=1001:1001' in args
            out=json.dumps({'symbols':[] if self.no_symbols else sorted(['LLVMFuzzerRunDriver','LLVMFuzzerTestOneInput','__asan_init','__sanitizer_cov_8bit_counters_init']),
                'nm_sha256':'b'*64,'nm_bytes':1024,
                'dynamic':base64.b64encode(b' 0 (NEEDED) Shared library: [libc.so.6]\n').decode(),
                'interpreter':base64.b64encode(b' [Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]\n').decode()}).encode()
        elif PROBE_PROGRAM in args:
            user=next(a for a in args if a.startswith('--user='))[7:];uid=int(user.split(':')[0])
            assert uid>=3000 and '/usr/bin/env' in args and '-i' in args
            out=json.dumps({'uid':uid,'gid':uid,'write_denied':True,'binary_sha256':'e'*64,
                'no_new_privileges':True,'capabilities':0,'credential_environment_absent':True}).encode()
        elif VERIFY_PROGRAM in args:
            value=json.loads(data)
            if self.changed:value['sha256']='f'*64
            out=json.dumps(value).encode()
        elif ARTIFACT_PROGRAM in args:
            campaign='campaign' in args[-2]
            present=campaign and self.negative
            out=json.dumps({'present':present,'bytes':1 if present else 0,
                'sha256':hashlib.sha256(b'X').hexdigest() if present else None,
                'data':base64.b64encode(b'X').decode() if present else ''}).encode()
        else:
            assert '/usr/bin/env' in args and '-i' in args
            assert not any(a=='--user=1001:1001' for a in args)
            campaign=any(a.endswith('/corpus') for a in args)
            if campaign and self.negative:code=77
            timeout=campaign and self.interrupted
            if timeout:code=124
            out=(b'#128 DONE cov: 7\nstat::number_of_executed_units: 128\n' if campaign else b'Executed /work/fuzz-snapshots/t0/s0 in 0 ms\n')
            if self.silent:out=b''
        return {'exit_code':code,'timed_out':timeout,'output_truncated':False,'output':out}


def proof(commands=None):
    return run_fuzz(commands or Commands(),'synthetic-container',plan(),targets())


def test_native_operations_bind_immutable_binary_seeds_and_separate_run_uids():
    c=Commands();native=proof(c);result=validate_evidence(native,plan(),targets())
    assert result['complete'] is True
    assert result['source_coverage'] is None
    assert result['completed_targets']==['control']
    assert [p['runtime_user'] for p in result['targets'][0]['phases']]==['3000:3000','3008:3008']
    assert result['targets'][0]['phases'][1]['tool_reported_executions']==128
    assert not any('--privileged' in a or '--volume' in a for a in c.calls)


def test_failed_campaign_is_retained_without_turning_exit_77_into_a_pass():
    native=proof(Commands(negative=True));result=validate_evidence(native,plan(),targets())
    campaign=result['targets'][0]['phases'][1]
    assert result['complete'] is False and result['executed_targets']==['control']
    assert campaign['status']=='failed' and campaign['exit_code']==77
    assert campaign['retained_failure_input']['data']==base64.b64encode(b'X').decode()


@pytest.mark.parametrize('field',['interrupted','no_symbols','changed','silent'])
def test_incomplete_or_unsupported_evidence_cannot_become_completed_fuzzing(field):
    native=proof(Commands(**{field:True}))
    result=validate_evidence(native,plan(),targets())
    assert result['complete'] is False


@pytest.mark.parametrize('problem',['user','argv','hash','base64','count','flag','input','plan','snapshot'])
def test_result_substitution_and_malformed_observations_fail_closed(problem):
    native=proof()
    if problem=='user':native['operations'][0]['user']='1000:1000'
    elif problem=='argv':native['operations'][0]['invocation']=['echo','fake']
    elif problem=='hash':native['operations'][0]['output_sha256']='b'*64
    elif problem=='base64':native['operations'][0]['output']='??'
    elif problem=='count':native['operations'].pop()
    elif problem=='flag':native['operations'][0]['attempted']=1
    elif problem=='input':native['operations'][4]['input_sha256']='f'*64
    elif problem=='plan':native['plan_sha256']='f'*64
    else:
        row=native['operations'][0];value=json.loads(base64.b64decode(row['output']))
        value['t0']['mode']=0o777;raw=json.dumps(value).encode()
        row['output']=base64.b64encode(raw).decode();row['output_sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):validate_evidence(native,plan(),targets())


def fuzz_fixture(negative=False):
    from tests.test_cpp_combined_configuration import combined_fixture
    from nico.assessment_cpp_full_project import execution_steps
    contract,native=combined_fixture()
    contract['targets']['corpus/seed']='a'*64
    native['source_hashes']=deepcopy(contract['targets'])
    config=contract['configuration'];config.update(fuzz_base_schema=config['schema'],
        schema='nico.cpp-cmake-configuration.v5',bounded_fuzz=plan())
    contract['max_receipt_bytes']=8*1024*1024
    for spec in execution_steps(contract):
        if any(r['id']==spec['id'] for r in native['steps']):continue
        out=b'17.0.6\n' if spec['id']=='fuzz-compiler-version' else b''
        if spec.get('fuzz_execution'):out=json.dumps(proof(Commands(negative=negative))).encode()
        native['steps'].append(dict(id=spec['id'],invocation=spec['invocation'],attempted=True,
            exit_code=0,timed_out=False,output_truncated=False,duration_ms=1,
            output=base64.b64encode(out).decode(),artifacts={}))
    return contract,native


@pytest.mark.parametrize('negative',[False,True])
def test_v5_publishes_fuzz_evidence_through_existing_authenticated_receipt(negative):
    from nico.assessment_worker_receipts import validate_receipt
    from tests.test_assessment_cpp_full_project import wrap
    from scripts.worker_protocol_fixture import identity
    contract,native=fuzz_fixture(negative);receipt=wrap(native,contract)
    _,record,_=validate_receipt(identity(contract),contract,receipt['lease_id'],receipt['worker_id'],receipt)
    build=record['cpp_build_evidence']
    assert record['completed'] is True
    assert build['fuzz_executed'] is True
    assert build['bounded_fuzz_evidence']['complete'] is (not negative)
    assert build['implemented_command_scope_complete'] is (not negative)
    assert build['full_project_qualified'] is False and record['client_delivery_allowed'] is False
    assert build['generated_context'] and build['native_test_binary_evidence']


@pytest.mark.parametrize('language',['en','es-MX'])
def test_exported_report_discloses_bounded_fuzz_failure_and_preserves_human_approval(tmp_path,language):
    from nico.assessment_worker_receipts import validate_receipt
    from nico.assessment_worker_jobs import _digest
    from tests.test_assessment_cpp_full_project import wrap
    from scripts.worker_protocol_fixture import identity
    from scripts.qualify_cpp_full_project_integration import render_result
    contract,native=fuzz_fixture(True);receipt=wrap(native,contract)
    _,record,_=validate_receipt(identity(contract),contract,receipt['lease_id'],receipt['worker_id'],receipt)
    record.update(raw_artifact_retention_complete=True,raw_artifact_sha256=_digest(receipt))
    result=render_result({'canonical_record':record},tmp_path,language)
    content=(tmp_path/('owned-project-'+language+'.md')).read_text()
    assert ('Bounded fuzzing:' if language=='en' else 'Fuzzing acotado:') in content
    assert ('native exit=77' if language=='en' else 'salida nativa=77') in content
    assert result['automated_draft'] and not result['production_report']


@pytest.mark.parametrize('value',[{},[],0,True,'bad'])
def test_snapshot_revalidation_input_digest_is_typed_even_for_unattempted_phases(value):
    native=proof(Commands(no_symbols=True))
    native['operations'][4]['input_sha256']=value
    with pytest.raises(ValueError):validate_evidence(native,plan(),targets())


def test_a_failed_fuzz_build_cannot_borrow_a_successful_fuzz_execution_chain():
    from nico.assessment_cpp_full_project import validate_native
    contract,native=fuzz_fixture()
    next(r for r in native['steps'] if r['id']=='fuzz-build')['exit_code']=2
    result=validate_native(native,contract)
    assert result['build']['bounded_fuzz_evidence']['execution_chain_verified'] is False
    assert result['build']['bounded_fuzz_evidence']['complete'] is False
    assert result['build']['implemented_command_scope_complete'] is False
