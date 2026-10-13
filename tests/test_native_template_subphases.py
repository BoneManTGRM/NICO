"""Owned deterministic native accounting and versioned evidence contracts."""
import os
from pathlib import Path
import subprocess
import shutil
import json
import pytest
from scripts.native_stage_counters import evidence as e, binding as b, instrument as i

ROOT=Path(__file__).resolve().parents[1]

def compile_owned(path, record):
    # Only this small C++11 fixture uses the runner compiler. Analyzer pins stay fixed.
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.fail('owned_native_compiler_unavailable: g++ is required on PATH')
    record('owned_native_compiler_path', compiler)
    version = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=5)
    record('owned_native_compiler_version', version.stdout)
    assert version.returncode == 0, ('owned_native_compiler_version_failed', version.stderr)
    argv = [compiler, '-std=c++11', '-O2', '-Wno-deprecated-declarations',
            '-I'+str(i.HEADER.parent), str(ROOT/'tests/native_stage_owned/template_scopes.cc'),
            '-o', str(path)]
    record('owned_native_compiler_argv', json.dumps(argv))
    result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, ('owned_native_compile_failed', result.stderr)
    return path


@pytest.fixture(scope='module')
def binary(tmp_path_factory, record_testsuite_property):
    def record(name, value):
        record_testsuite_property(name, value)
        print(f'{name}={value}')
    return compile_owned(tmp_path_factory.mktemp('template-scopes')/'owned', record)


def test_missing_owned_compiler_fails_without_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('must not execute'))
    with pytest.raises(pytest.fail.Exception, match='owned_native_compiler_unavailable'):
        compile_owned(tmp_path/'owned', lambda *a: None)


@pytest.mark.parametrize('failure', ['version', 'compile'])
def test_owned_compiler_failure_is_fatal(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(shutil, 'which', lambda name: '/owned/g++')
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        failed = failure == 'version' or '--version' not in argv
        return subprocess.CompletedProcess(argv, 1 if failed else 0, 'owned compiler', 'retained failure')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(AssertionError, match='retained failure'):
        compile_owned(tmp_path/'owned', lambda *a: None)
    assert len(calls) == (1 if failure == 'version' else 2)


@pytest.mark.parametrize('mode',['scopes','snapshot','clock','unavailable','caps','mutation','rate','visit-clock','backward','post-failure','saturation','cross-checkpoint'])
def test_owned_accounting(binary,mode):
    r=subprocess.run([str(binary),mode],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':'1'},capture_output=True,timeout=5)
    assert r.returncode==0,(r.stdout,r.stderr)
    parsed=e.parse_snapshots(r.stderr,timed_out=mode=='snapshot',binary_sha256='a'*64,expected_version=3)
    if mode=='caps':assert len(parsed['records'])==128
    if mode=='scopes':assert parsed['records'][-1]['transition_id']==10
    if mode=='snapshot':
        row=parsed['records'][-1]
        assert row['active_bucket']==3 and row['bucket_depth']==2
        assert row['stable_selection_ns']==0 and row['stable_expansion_ns']==30
        assert row['expansion_completed']==0
    if mode in ('clock','unavailable'):assert parsed['records'][-1]['thread_clock_status']==2

@pytest.mark.parametrize('value',['','0','true','11'])
def test_disabled_no_clock_or_output(binary,value):
    r=subprocess.run([str(binary)],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':value},capture_output=True,timeout=5)
    assert r.returncode==0 and r.stderr==b''

def record(**updates):
    row=dict.fromkeys(e.FIELDS_V2,0);row.update(phase=1,thread_clock_status=1);row.update(updates)
    return ('NICO_STAGE_V2 1 0 1 0 123 10 1000000 '+' '.join(str(row[k]) for k in e.FIELDS_V2)+'\n').encode()

@pytest.mark.parametrize('updates',[{'active_bucket':5},{'active_bucket':1}, {'bucket_depth':1},
    {'thread_clock_status':3},{'selection_completed':1},{'thread_clock_status':0,'selection_cpu_ns':1},
    {'selection_visits':2**64},{'active_bucket':1,'bucket_depth':1},
    {'active_bucket':1,'bucket_depth':2,'selection_entered':1}])
def test_malformed_v2_rejected(updates):
    with pytest.raises(ValueError):e.parse_snapshots(record(**updates),timed_out=True,binary_sha256='a'*64,expected_version=2)

@pytest.mark.parametrize('raw',[b'NICO_STAGE_V4 1\n',record().replace(b'V2',b'V1'),record()+record().replace(b'V2',b'V1')])
def test_mismatched_versions_fail_closed(raw):
    with pytest.raises(ValueError):e.parse_snapshots(raw,timed_out=True,binary_sha256='a'*64,expected_version=2)

def test_regressed_cpu_or_visits_rejected():
    for key in ['selection_cpu_ns','selection_visits','selection_entered']:
        with pytest.raises(ValueError,match='regressed'):
            e.parse_snapshots(record(**{key:10})+record(**{key:9}).replace(b'V2 1 ',b'V2 2 '),timed_out=True,binary_sha256='a'*64)

def test_old_binding_version_rejected():
    from test_native_stage_counters import runtime_binding
    value=runtime_binding();value['schema']='nico.stage-runtime-binding.v2'
    with pytest.raises(ValueError):b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])

def test_record_version_bound():
    from test_native_stage_counters import runtime_binding
    for version in [None,1,True,'2']:
        value=runtime_binding();value['record_version']=version
        with pytest.raises(ValueError):b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])


def test_partial_v2_snapshot_keeps_valid_prefix():
    result=e.parse_snapshots(record()+b'NICO_STAGE_V2 2 0',timed_out=True,binary_sha256='a'*64,expected_version=2)
    assert result['incomplete_tail'] and len(result['records'])==1
    with pytest.raises(ValueError,match='version_mismatch'):
        e.parse_snapshots(record()+b'NICO_STAGE_V1 2 0',timed_out=True,binary_sha256='a'*64,expected_version=2)


def test_bad_version_in_collector_is_retained_as_error():
    import base64,hashlib,json
    raw=record().replace(b'V2',b'V1')
    row={'context_id':'owned','execution':{'output':base64.b64encode(raw).decode(),
        'output_sha256':hashlib.sha256(raw).hexdigest(),'timed_out':True,'output_truncated':False}}
    result=e.collect_case_snapshots(json.dumps({'diagnostic_partial_record':row}).encode(),
        {'instrumented_binary_sha256':'a'*64,'record_version':2},['owned'])
    assert result[0]['snapshots'] is None and result[0]['error']=='stage_version_mismatch'


@pytest.mark.parametrize('second',[
    record().replace(b'V2 1 ',b'V2 2 ').replace(b' 123 ',b' 122 '),
    record().replace(b'V2 1 ',b'V2 2 ').replace(b' 1000000 ',b' 1000 '),
])
def test_clock_metadata_mismatch_rejected(second):
    with pytest.raises(ValueError):
        e.parse_snapshots(record()+second,timed_out=True,binary_sha256='a'*64,expected_version=2)


@pytest.mark.parametrize('raw',[b'NICO_STAGE_V4 1', b'NICO_STAGE_V2 '+b'1 '*600])
def test_invalid_partial_record_rejected(raw):
    with pytest.raises(ValueError):
        e.parse_snapshots(raw,timed_out=True,binary_sha256='a'*64,expected_version=2)


def test_partial_only_v2_retains_version():
    result=e.parse_snapshots(b'NICO_STAGE_V2 1',timed_out=True,binary_sha256='a'*64)
    assert result['schema']=='nico.cppcheck-stage-counter-evidence.v2'
    assert result['incomplete_tail'] and not result['records']


def sparse_record(seq=1, **updates):
    row=dict.fromkeys(e.FIELDS_V3,0)
    row.update(phase=1,thread_clock_status=1,clock_reads=2*seq-1)
    row.update(updates)
    return (f'NICO_STAGE_V3 {seq} 0 1 0 {seq*100} 10 1000000 '+' '.join(str(row[k]) for k in e.FIELDS_V3)+'\n').encode()

@pytest.mark.parametrize('change',[
    {'transition_saturated':1},{'transition_id':2**64-1},{'clock_reads':3},
    {'interval_kind':1},{'stable_selection_ns':1},{'observer_ns':1},
    {'interval_kind':7},{'thread_clock_status':2},{'active_bucket':1,'bucket_depth':1},
])
def test_sparse_malformed_prefix(change):
    with pytest.raises(ValueError):
        e.parse_snapshots(sparse_record(**change),timed_out=True,binary_sha256='a'*64,expected_version=3)


def test_sparse_interval_attribution_and_totals_fail_closed():
    first=sparse_record(active_bucket=1,bucket_depth=1,selection_entered=1,transition_id=1)
    attrs=dict(active_bucket=1,bucket_depth=1,selection_entered=1,transition_id=1,interval_kind=1,interval_ns=20,stable_selection_ns=20,observer_ns=2)
    good=sparse_record(2,**attrs)
    parsed=e.parse_snapshots(first+good,timed_out=True,binary_sha256='a'*64,expected_version=3)
    assert parsed['records'][-1]['stable_selection_ns']==20
    for changed in [{'transition_id':3},{'stable_selection_ns':19},{'active_bucket':2,'matching_entered':1},{'clock_reads':5}]:
        with pytest.raises(ValueError):
            e.parse_snapshots(first+sparse_record(2,**{**attrs,**changed}),timed_out=True,binary_sha256='a'*64,expected_version=3)


def test_sparse_old_records_do_not_satisfy_new_binding():
    from test_native_stage_counters import runtime_binding
    value=runtime_binding()
    for version in [1,2,True,None,'3']:
        value['record_version']=version
        with pytest.raises(ValueError):b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])
    with pytest.raises(ValueError,match='version_mismatch'):
        e.parse_snapshots(record(),timed_out=True,binary_sha256='a'*64,expected_version=3)
    assert e.parse_snapshots(record(),timed_out=True,binary_sha256='a'*64)['schema'].endswith('.v2')


def test_sparse_transition_saturation_never_claims_stable_interval():
    first=sparse_record(transition_id=2**64-1,transition_saturated=1)
    second=sparse_record(2,transition_id=2**64-1,transition_saturated=1,interval_kind=5,interval_ns=10,unattributed_ns=10)
    assert e.parse_snapshots(first+second,timed_out=True,binary_sha256='a'*64,expected_version=3)['records'][-1]['unattributed_ns']==10
    with pytest.raises(ValueError):
        e.parse_snapshots(first+sparse_record(2,transition_id=2**64-1,transition_saturated=1,interval_kind=6,interval_ns=10,outside_ns=10),timed_out=True,binary_sha256='a'*64,expected_version=3)


def test_sparse_worst_width_stays_within_existing_record_cap():
    row=dict.fromkeys(e.FIELDS_V3,2**64-1)
    row.update(phase=3,**{'pass':10},active_bucket=4,thread_clock_status=2,
        transition_saturated=1,clock_reads=255,interval_kind=7)
    raw=('NICO_STAGE_V3 128 2 3 4294967295 18446744073709551615 9223372036854775807 1000000 '+
         ' '.join(str(row[k]) for k in e.FIELDS_V3)+'\n').encode()
    assert len(raw)<=e.MAX_RECORD_BYTES


def test_held_exact_timer_binding_rejected():
    from test_native_stage_counters import runtime_binding
    value=runtime_binding();value['schema']='nico.stage-runtime-binding.v3';value['record_version']=2
    with pytest.raises(ValueError):b.validate_binding(value,value['image'],b.binding_digest(value),value['original_image'])


def test_native_contract_gate_precedes_tool_acquisition():
    workflow = (ROOT/'.github/workflows/native-timeout-diagnostic.yml').read_text()
    gate = workflow.split('- name: Verify diagnostic contracts', 1)[1].split('- uses: actions/checkout@', 1)[0]
    assert 'tests/test_native_template_subphases.py' in gate
    assert '--junitxml=native-diagnostic-evidence/contracts.xml' in gate
    assert workflow.index('- name: Verify diagnostic contracts') < workflow.index('repository: cppcheck-opensource/cppcheck')
