"""Missing versus denied inputs, exact generation cover and installed transport.

The adapter is deliberately not an executed compiler/production receipt. The
owned real CMake failure and corrected execution are retained separately.
"""
import base64
from copy import deepcopy
import errno
import hashlib
import json
from pathlib import Path

import pytest

from nico.assessment_cpp_configuration_probe import probe_project_configuration, READ_PROGRAM
from nico.assessment_cpp_fileapi_membership import CAPTURE_PROGRAM as FILEAPI_CAPTURE, QUERY_PROGRAM, QUERY_NAMES, EMPTY_SHA, configured_target_membership
from nico.assessment_cpp_native_commands import CAPTURE_PROGRAM as NATIVE_CAPTURE, configured_native_commands
from nico.assessment_cpp_generated_inputs import OBSERVE_PROGRAM, observe_generated_inputs, generated_input_plan, validate_observation
from nico.assessment_cpp_project_snapshot import PROJECT_SNAPSHOT_PROGRAM, ProjectSnapshotFailure, capture_project_snapshot, project_snapshot_request
from nico.assessment_cpp_project_compiler import PROGRAM as COMPILER_PROGRAM
from nico.assessment_cpp_full_project import _database
from nico.assessment_cpp_baseline_evidence import retained_baseline_bytes, validate_retained_baseline
from nico.assessment_cpp_configure_first_execution import summarize_probe
from nico.assessment_worker_receipts import canonical_bytes
from scripts.qualify_cpp_project_configuration import persist_project_artifact, qualification_probe_receipt
from tests.test_cpp_baseline_execution import Native, contract
from tests.test_cpp_configure_first_execution import ref

FIXTURE = Path(__file__).parent/'fixtures/cpp/excluded-generated-owned'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def adapted(client):
    database=(FIXTURE/'compile_commands.json').read_bytes()
    cache=(FIXTURE/'CMakeCache.txt').read_bytes()
    fileapi=json.loads((FIXTURE/'fileapi.json').read_bytes())
    for name,row in fileapi['files'].items():
        if name.startswith('index-'):
            model=json.loads(base64.b64decode(row['data']))
            model['reply']={client:model['reply'][fileapi['client']]}
            raw=canonical_bytes(model)
            row.update(data=base64.b64encode(raw).decode(),bytes=len(raw),sha256=sha(raw))
    fileapi['client']=client
    fileapi['cache_sha256']=sha(cache)
    fileapi_raw=canonical_bytes(fileapi)
    native=json.loads((FIXTURE/'native.json').read_bytes())
    native.update(fileapi_capture_sha256=sha(fileapi_raw),cache_sha256=sha(cache))
    return fileapi_raw,canonical_bytes(native),database,cache,fileapi['source_hashes']


def reconstruction():
    fileapi,native,database,cache,targets=adapted('client-nico-owned-generation')
    kwargs=dict(source_root='/work/source',build_root='/work/build',client='client-nico-owned-generation',
        cache_sha256=sha(cache),compiler_versions={'CXX':'14.2.0'},compiler_paths={'CXX':'/usr/local/bin/g++'},
        cmake_path='/opt/cmake-wheel/cmake/data/bin/cmake')
    membership=configured_target_membership(fileapi,database,targets,**kwargs)
    plan=configured_native_commands(native,fileapi,database,targets,**kwargs)
    contexts=_database(base64.b64decode(plan['analysis_database']),None,'/work/build',nested=True,source_targets=targets)
    return fileapi,native,membership,plan,project_snapshot_request(contexts)


def test_actual_owned_capture_has_one_missing_exported_context_and_exact_utility_cover(tmp_path):
    fileapi,native,membership,plan,request=reconstruction()
    assert plan['context_count']==2 and plan['original_database_context_count']==1
    observation=observe_generated_inputs(tmp_path,request)
    assert observation['files']['generated/hidden.cpp']['errno']==errno.ENOENT
    chosen=generated_input_plan(native,fileapi,membership,plan,request,observation,analyst=False)
    assert chosen['selected_targets'][0]['target_name']=='hidden_inputs'
    assert chosen['missing_units']==chosen['selected_targets'][0]['required_outputs']==['generated/hidden.cpp']
    assert chosen['analysis_executed'] is False and chosen['header_coverage_verified'] is False
    (tmp_path/'generated').mkdir()
    (tmp_path/'generated/hidden.cpp').write_bytes(b'int hidden(){return 11;}\n')
    repeat=generated_input_plan(native,fileapi,membership,plan,request,
        observe_generated_inputs(tmp_path,request),analyst=False)
    assert repeat['selected_targets']==[] and repeat['missing_units']==[]


@pytest.mark.parametrize('fault',['denied','wrong_uid','wrong_request','wrong_database','wrong_native','omitted_unit','uncovered'])
def test_incomplete_or_unbound_inputs_cannot_authorize_generation(tmp_path,fault):
    fileapi,native,membership,plan,request=reconstruction()
    observed=observe_generated_inputs(tmp_path,request);observed.update(uid=1001,gid=1001)
    if fault=='denied':observed['files']['generated/hidden.cpp'].update(state='unavailable',errno=errno.EACCES)
    elif fault=='wrong_uid':observed['uid']=1000
    elif fault=='wrong_request':observed['request_sha256']='0'*64
    elif fault=='wrong_database':plan['analysis_database_sha256']='0'*64
    elif fault=='wrong_native':plan['native_capture_sha256']='0'*64
    elif fault=='omitted_unit':request['generated_units']=[]
    else:
        capsule=json.loads(native)
        name='CMakeFiles/hidden_inputs.dir/build.make'
        raw=base64.b64decode(capsule['files'][name]['data']).replace(
            b'hidden_inputs: generated/hidden.cpp',b'hidden_inputs: different.cpp')
        capsule['files'][name]={'data':base64.b64encode(raw).decode(),'bytes':len(raw),'sha256':sha(raw)}
        native=canonical_bytes(capsule);plan['native_capture_sha256']=sha(native)
    with pytest.raises(ValueError):
        generated_input_plan(native,fileapi,membership,plan,request,observed)


def test_no_follow_and_actual_permission_denial_are_not_missing_inputs(tmp_path):
    request=reconstruction()[-1]
    (tmp_path/'generated').mkdir()
    path=tmp_path/'generated/hidden.cpp';path.write_text('owned')
    path.chmod(0)
    try:
        observed=observe_generated_inputs(tmp_path,request)
        assert observed['files']['generated/hidden.cpp']['state']=='unavailable'
        assert observed['files']['generated/hidden.cpp']['errno']==errno.EACCES
    finally:
        path.chmod(0o600)
    path.unlink();path.symlink_to(tmp_path/'elsewhere')
    with pytest.raises(ValueError):observe_generated_inputs(tmp_path,request)


class GenerationDocker(Native):
    def __init__(self,targets,tmp_path,fault=None):
        super().__init__(targets)
        self.tmp_path,self.fault=tmp_path,fault
        self.fileapi=self.native=None;self.available=False;self.compiler_request=None
        self.database=(FIXTURE/'compile_commands.json').read_bytes()

    def __call__(self,args,**kwargs):
        raw,code=None,0
        if QUERY_PROGRAM in args:
            raw=canonical_bytes({'client':args[-1],'query':{q:EMPTY_SHA for q in QUERY_NAMES}})
        elif FILEAPI_CAPTURE in args:
            request=json.loads(kwargs['input_bytes'])
            self.fileapi,self.native,_,_,_=adapted(request['client']);raw=self.fileapi
        elif NATIVE_CAPTURE in args:raw=self.native
        elif READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
            raw=canonical_bytes({'data':base64.b64encode(self.database).decode(),'truncated':False})
        elif READ_PROGRAM in args and '/work/build/CMakeCache.txt' in args:
            raw=canonical_bytes({'data':base64.b64encode((FIXTURE/'CMakeCache.txt').read_bytes()).decode(),'truncated':False})
        elif OBSERVE_PROGRAM in args:
            request=json.loads(kwargs['input_bytes'])
            build=self.tmp_path/'observed-build';build.mkdir(exist_ok=True)
            if self.available:
                (build/'generated').mkdir(exist_ok=True)
                (build/'generated/hidden.cpp').write_bytes((FIXTURE/'source/hidden.cpp.in').read_bytes())
            observed=observe_generated_inputs(build,request);observed.update(uid=1001,gid=1001)
            if self.fault=='permission':observed['files']['generated/hidden.cpp'].update(state='unavailable',errno=errno.EACCES,bytes=None,links=None,mode=None)
            raw=canonical_bytes(observed)
        elif 'cmake' in args and '--target' in args:
            assert args[args.index('--target')+1]=='hidden_inputs'
            assert kwargs['timeout']<=1200
            self.available=self.fault!='no_output';raw=b'owned adapter generator output\n'
        elif PROJECT_SNAPSHOT_PROGRAM in args:
            request=json.loads(kwargs['input_bytes'])
            build=self.tmp_path/'observed-build';build.mkdir(exist_ok=True)
            private=self.tmp_path/'private';private.mkdir(mode=0o700,exist_ok=True)
            try:raw=canonical_bytes(capture_project_snapshot(build,private/'baseline',request))
            except ProjectSnapshotFailure:raw,code=b'owned missing generated source',1
        elif COMPILER_PROGRAM in args:
            self.compiler_request=json.loads(kwargs['input_bytes'])
            raw,code=b'owned compiler deliberately unavailable',1
        if raw is None:return super().__call__(args,**kwargs)
        self.calls.append((args,kwargs))
        return {'exit_code':code,'timed_out':False,'output_truncated':False,'output':raw}


def run_case(tmp_path,*,enabled=True,fault=None):
    source,out=tmp_path/'source',tmp_path/'out';source.mkdir();out.mkdir()
    targets=adapted('client-nico-owned-generation')[-1]
    for name in targets:(source/name).write_bytes((FIXTURE/'source'/name).read_bytes())
    docker=GenerationDocker(targets,tmp_path,fault)
    baseline=contract();baseline.pop('compilation_database_sha256')
    baseline.update(schema='nico.cpp-baseline-execution.v2',freeze_compilation_database='after_configuration_before_build')
    probe=probe_project_configuration(source,targets,'sha256:'+'a'*64,project_options={},
        baseline_execution=baseline,command=docker,capture_enabled_targets=True,capture_native_commands=True,
        capture_generated_context=True,project_compiler_evidence=True,materialize_generated_inputs=enabled,
        retain_artifact=lambda key,raw:persist_project_artifact(out,key,raw))
    return probe,docker,targets,out,{'schema':'nico.cpp-configure-first-contract.v8','baseline_execution':baseline}


def test_original_path_missing_input_and_corrected_installed_controller(tmp_path):
    old=tmp_path/'original';old.mkdir()
    original,docker,_,_,_=run_case(old,enabled=False)
    assert original['compiled'] is True and original['tests_executed'] is True
    assert original['error']=='worker_configuration_probe_snapshot_failed'
    assert docker.compiler_request is None and not any('--target' in a for a,k in docker.calls)
    fixed=tmp_path/'corrected';fixed.mkdir()
    result,docker,targets,out,cfg=run_case(fixed)
    assert result['schema']=='nico.cpp-project-configuration-probe.v10'
    assert result['generated_input_materialization']['complete'] is True
    assert result['compilation_database_sha256']==sha(docker.database)
    assert result['configured_invocations']==1 and result['analysis_invocations']==2
    assert docker.compiler_request is not None and result['generated_context_verified'] is True
    assert result['error']=='worker_configuration_probe_compiler_failed' and result['full_project_qualified'] is False
    artifacts={r['id']:ref(r['id'],(out/r['output_artifact']['path']).read_bytes())
        for r in result['operations'] if r.get('output_artifact')}
    generation=result['generated_input_materialization']['artifact'];raw_generation=(out/generation['path']).read_bytes()
    projected=qualification_probe_receipt(result)['generated_input_materialization']
    assert projected=={'schema':'nico.cpp-generated-input-evidence.v1','complete':True,
        'artifact':generation,'native_evidence_sha256':sha(raw_generation),'receipt_projection':'hash-bound-summary-v1'}
    assert 'before' not in projected and 'plan' not in projected
    artifacts['project-generation-evidence']=ref('project-generation-evidence',raw_generation)
    native=summarize_probe(result,targets,artifacts);native['project_options']={}
    assert native['schema']=='nico.cpp-configure-first-native.v7' and native['complete_execution'] is False
    raw=retained_baseline_bytes(result,targets,cfg,'sha256:'+'a'*64)
    assert json.loads(raw)['schema']=='nico.cpp-baseline-evidence.v4'
    kwargs=dict(membership_raw=docker.fileapi,native_raw=docker.native,native_post_raw=docker.native,generation_raw=raw_generation)
    assert validate_retained_baseline(raw,targets,cfg,'sha256:'+'a'*64,native,**kwargs)['collection_complete'] is True
    for fault in ('missing_generation','false_digest','wrong_target','wrong_observer','omitted_operation','late_generation','changed_image','reset_budget'):
        payload=json.loads(raw);summary=deepcopy(native);mutated=dict(kwargs)
        if fault=='missing_generation':mutated['generation_raw']=None
        elif fault=='false_digest':summary['generation_evidence_sha256']='0'*64
        elif fault=='wrong_target':next(r for r in payload['probe']['operations'] if r['id']=='generation-target-000')['invocation'][7]='other_target'
        elif fault=='wrong_observer':next(r for r in payload['probe']['operations'] if r['id']=='generation-inputs-before')['invocation'][2]='--user=1000:1000'
        elif fault=='omitted_operation':payload['probe']['operations']=[r for r in payload['probe']['operations'] if r['id']!='generation-target-000']
        elif fault=='late_generation':
            rows=payload['probe']['operations'];before=next(i for i,r in enumerate(rows) if r['id']=='generation-inputs-before');rows[before],rows[before+1]=rows[before+1],rows[before]
        else:
            evidence=json.loads(raw_generation)
            if fault=='changed_image':evidence['image_config_digest']='sha256:'+'0'*64
            else:evidence['build_elapsed_ms']=1200001
            changed=canonical_bytes(evidence);digest=sha(changed)
            payload['probe']['generated_input_materialization']={**evidence,'artifact':{'path':'artifacts/project-generation-evidence-'+digest+'.json','sha256':digest,'bytes':len(changed)}}
            summary['generation_evidence_sha256']=digest;mutated['generation_raw']=changed
        with pytest.raises(ValueError):validate_retained_baseline(canonical_bytes(payload),targets,cfg,'sha256:'+'a'*64,summary,**mutated)


@pytest.mark.parametrize('fault',['permission','no_output'])
def test_unavailable_generation_keeps_truthful_failure_and_stops_compiler(tmp_path,fault):
    result,docker,_,_,_=run_case(tmp_path,fault=fault)
    assert result['status']=='UNPROVEN' and result['cleanup_verified'] is True
    assert result['generated_context_verified'] is False and docker.compiler_request is None
    if fault=='permission':assert not any('--target' in a for a,k in docker.calls)
    else:assert result['generated_input_materialization']['complete'] is False
