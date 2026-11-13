"""Trusted builder input/startup controls; subprocess adapter is synthetic."""
from copy import deepcopy
import hashlib,json,plistlib,shutil,subprocess
from pathlib import Path
import pytest
from scripts import build_cpp_clang_header_observer as builder
from scripts.provision_cpp_fuzz_tools import validate_lock,LOCK,HEADER_SDK_LOCK

ROOT=Path(__file__).parents[1]
def inputs(tmp_path):
    source=tmp_path/'source';sdk=tmp_path/'sdk';runtime=tmp_path/'runtime'
    shutil.copytree(ROOT/'scripts/clang-header-evidence',source);sdk.mkdir();runtime.mkdir()
    shutil.copyfile(HEADER_SDK_LOCK,sdk/'lock.json');shutil.copyfile(LOCK,runtime/'lock.json')
    return source,sdk,runtime,tmp_path/'output'

class BuildFixture:
    def __init__(self,kind=None):self.kind=kind;self.calls=[]
    def __call__(self,argv,**kwargs):
        self.calls.append((argv,kwargs))
        if '-dumpfullversion' in argv:output=b'14.2.0\n'
        elif '-dumpversion' in argv:output=b'17.0.6\n'
        elif '--analyze' not in argv:
            binary=Path(argv[argv.index('-o')+1]);binary.write_bytes(b'\x7fELF\x02\x01'+b'\0'*12+b'\x3e\0'+b'\0'*44)
            if self.kind=='corrupt_binary':binary.write_bytes(b'corrupt')
            output=b''
        else:
            env=kwargs['env'];source=argv[-3];trace={'schema':'nico.clang-header-observer.v1','clang_version':'17.0.6',
                'source':source,'context_id':env['NICO_CLANG_HEADER_CONTEXT'],'standard':'c++17',
                'translation_unit_started':True,'translation_unit_ended':self.kind!='partial',
                'diagnostic_errors':False,'observation_overflow':False,'files':[{'path':source,'ast_body_callbacks':1}]}
            Path(env['NICO_CLANG_HEADER_OUTPUT']).write_text(json.dumps(trace))
            Path(argv[-1]).write_bytes(plistlib.dumps({'diagnostics':[]}));output=b''
        return subprocess.CompletedProcess(argv,0,output,b'')

def test_valid_builder_fixture_retains_probe_raw_digests_and_false_qualification(tmp_path):
    args=inputs(tmp_path);run=BuildFixture();receipt=builder.build(*args,run=run)
    assert receipt['qualification_completed'] is False and len(run.calls)==4
    control=json.loads((args[-1]/'startup-control.json').read_bytes())
    assert control['trace_sha256']==hashlib.sha256((args[-1]/'probe.header.json').read_bytes()).hexdigest()
    assert control['plist_sha256']==hashlib.sha256((args[-1]/'probe.plist').read_bytes()).hexdigest()
    assert run.calls[-1][1]['timeout']==30 and run.calls[2][1]['timeout']==180
    assert '-analyzer-checker=nico.HeaderEvidence' in run.calls[-1][0]

@pytest.mark.parametrize('kind',['source','manifest','sdk','runtime','existing_output','symlink','corrupt_binary','partial'])
def test_wrong_stale_or_incomplete_builder_inputs_or_startup_reject(kind,tmp_path):
    source,sdk,runtime,output=inputs(tmp_path);run=BuildFixture(kind)
    if kind in {'source','manifest','sdk','runtime'}:
        path={'source':source/'HeaderObserver.cpp','manifest':source/'manifest.json','sdk':sdk/'lock.json','runtime':runtime/'lock.json'}[kind]
        path.write_bytes(path.read_bytes()+b' ')
    elif kind=='existing_output':output.mkdir()
    elif kind=='symlink':
        path=source/'HeaderObserver.cpp';raw=path.read_bytes();path.unlink();other=tmp_path/'other.cpp';other.write_bytes(raw);path.symlink_to(other)
    with pytest.raises((ValueError,FileExistsError)):builder.build(source,sdk,runtime,output,run=run)
    assert not (output/'receipt.json').exists()

def test_matching_sdk_is_inside_existing_aggregate_runtime_package_budget():
    sdk=json.loads(HEADER_SDK_LOCK.read_bytes());runtime=json.loads(LOCK.read_bytes())
    rows=validate_lock(sdk);assert len(rows)==2
    assert sum(row['bytes'] for row in [*rows,*validate_lock(runtime)])<=200*1024*1024

@pytest.mark.parametrize('key,value',[('version','18.0.0'),('sha256','a'*64),('bytes',1),('url','https://example.com/untrusted.deb')])
def test_sdk_rejects_unpinned_package_identity(key,value):
    sdk=deepcopy(json.loads(HEADER_SDK_LOCK.read_bytes()));sdk['packages'][0][key]=value
    with pytest.raises(ValueError):validate_lock(sdk)
