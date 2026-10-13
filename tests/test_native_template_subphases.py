"""Owned deterministic native accounting and versioned evidence contracts."""
import os
from pathlib import Path
import subprocess
import pytest
from scripts.native_stage_counters import evidence as e, binding as b, instrument as i

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    path=tmp_path_factory.mktemp('template-scopes')/'owned'
    result=subprocess.run(['/usr/bin/g++-14','-std=c++11','-O2','-Wno-deprecated-declarations',
        '-I'+str(i.HEADER.parent),str(ROOT/'tests/native_stage_owned/template_scopes.cc'),'-o',str(path)],
        capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr.decode()
    return path

@pytest.mark.parametrize('mode',['scopes','snapshot','clock','unavailable','caps','mutation','rate','visit-clock','backward'])
def test_owned_accounting(binary,mode):
    r=subprocess.run([str(binary),mode],env={**os.environ,'NICO_CPP_STAGE_COUNTERS':'1'},capture_output=True,timeout=5)
    assert r.returncode==0,(r.stdout,r.stderr)
    parsed=e.parse_snapshots(r.stderr,timed_out=mode=='snapshot',binary_sha256='a'*64,expected_version=2)
    if mode=='caps':assert len(parsed['records'])==128
    if mode=='snapshot':
        row=parsed['records'][0]
        assert row['active_bucket']==3 and row['bucket_depth']==2
        assert row['selection_cpu_ns']==10 and row['expansion_cpu_ns']==30
        assert row['expansion_completed']==0
    if mode in ('clock','unavailable'):assert parsed['records'][0]['thread_clock_status']==2

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

@pytest.mark.parametrize('raw',[b'NICO_STAGE_V3 1\n',record().replace(b'V2',b'V1'),record()+record().replace(b'V2',b'V1')])
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


@pytest.mark.parametrize('raw',[b'NICO_STAGE_V3 1', b'NICO_STAGE_V2 '+b'1 '*600])
def test_invalid_partial_record_rejected(raw):
    with pytest.raises(ValueError):
        e.parse_snapshots(raw,timed_out=True,binary_sha256='a'*64,expected_version=2)


def test_partial_only_v2_retains_version():
    result=e.parse_snapshots(b'NICO_STAGE_V2 1',timed_out=True,binary_sha256='a'*64)
    assert result['schema']=='nico.cppcheck-stage-counter-evidence.v2'
    assert result['incomplete_tail'] and not result['records']
