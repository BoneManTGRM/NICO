"""Every project context needs real compiler and bound dependency evidence."""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import pytest

from nico import assessment_cpp_project_snapshot as snapshot
from nico.assessment_cpp_full_project import compilation_contexts


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capability(name):
    import importlib.util
    spec = importlib.util.find_spec('nico.assessment_cpp_project_compiler')
    assert spec is not None, 'missing project-wide compiler/header replay'
    from nico import assessment_cpp_project_compiler as compiler
    return getattr(compiler, name)


def inputs(tmp_path, extra=()):
    targets = {'main.cpp': digest(b'#include "config.h"\nint main(){return VALUE;}\n'),
               'original.h': digest(b'#define ORIGINAL 1\n')}
    def command(file, output, value):
        return ['/usr/local/bin/g++', '-DVALUE='+str(value), '-I/work/build/generated',
                '-I/work/source', *extra, '-std=c++20', '-c', file, '-o', output]
    rows = [dict(directory='/work/build', file='/work/source/main.cpp',
                 arguments=command('/work/source/main.cpp','one.o',1)),
            dict(directory='/work/build/nested', file='/work/source/main.cpp',
                 arguments=command('/work/source/main.cpp','two.o',2)),
            dict(directory='/work/build/generated', file='/work/build/generated/file.capnp.c++',
                 arguments=command('/work/build/generated/file.capnp.c++','gen.o',3))]
    raw = json.dumps(rows).encode()
    contexts = compilation_contexts(raw, targets, '/work/build')
    build=tmp_path/'build'; (build/'generated').mkdir(parents=True)
    (build/'generated/file.capnp.c++').write_bytes(b'#include "config.h"\nint generated(){return VALUE;}\n')
    (build/'generated/config.h').write_bytes(b'// owned generated header\n')
    (build/'generated/unvisited.h').write_bytes(b'// not included\n')
    private=tmp_path/'private'; private.mkdir(mode=0o700)
    captured=snapshot.capture_project_snapshot(build, private/'generated-baseline',
                                               snapshot.project_snapshot_request(contexts))
    return raw, targets, captured, contexts


def test_all_contexts_replay_with_private_generated_source_and_original_semantics(tmp_path):
    raw, targets, captured, contexts = inputs(tmp_path)
    plan = capability('project_compiler_request')(raw, targets, captured)
    assert [r['context_id'] for r in plan['contexts']] == [r['context_id'] for r in contexts['contexts']]
    assert len(plan['contexts']) == 3
    for row in plan['contexts']:
        argv = row['invocation']
        assert '-fsyntax-only' in argv and '-MD' in argv
        assert '-I/work/analysis/generated-baseline/generated' in argv
        assert '-I/work/source' in argv
        assert not any(a == '/work/build/generated/file.capnp.c++' or a == '-I/work/build/generated' for a in argv)
        assert argv[argv.index('-MF')+1].startswith('/work/analysis/compiler-baseline/')
    assert '/work/analysis/generated-baseline/generated/file.capnp.c++' in plan['contexts'][2]['invocation']
    assert plan['contexts'][0]['context_id'] != plan['contexts'][1]['context_id']
    assert plan['snapshot_population_sha256'] == captured['file_population_sha256']
    assert plan['limits'] == {'wall_seconds':540,'case_seconds':90,'parallel':4}
    assert not any('base64' in v for v in plan['generated_files'].values())


@pytest.mark.parametrize('flag', ['-ftrapv','-fno-extended-identifiers','-fcf-protection=full',
    '-Wbidi-chars=any','-mavx','-mavx2','-msha','-msse4','-msse4.1',
    '-fmacro-prefix-map=/work/source=.', '-fstack-reuse=none'])
def test_observed_scalar_flags_are_preserved_without_broadening_legacy_parser(tmp_path, flag):
    raw, targets, captured, _ = inputs(tmp_path, [flag])
    request=capability('project_compiler_request')(raw, targets, captured)
    assert all(flag in r['invocation'] for r in request['contexts'])


@pytest.mark.parametrize('flag', ['-fplugin=/work/source/helper.so','@/work/source/options',
    '-B/work/source','-specs=/work/source/specs','-wrapper','-save-temps',
    '-fmacro-prefix-map=/etc=.', '-fmacro-prefix-map=/work/source=../../escape'])
def test_executable_or_unbounded_options_are_rejected_before_any_process(tmp_path, flag):
    raw, targets, captured, _ = inputs(tmp_path, [flag])
    with pytest.raises(ValueError): capability('project_compiler_request')(raw, targets, captured)


def test_snapshot_substitution_is_not_a_compile_plan(tmp_path):
    raw, targets, captured, _ = inputs(tmp_path)
    captured['files']['generated/config.h']['sha256']='0'*64
    with pytest.raises(ValueError): capability('project_compiler_request')(raw, targets, captured)


def result_for(request):
    records=[]
    for row in request['contexts']:
        source=row['analysis_file']
        deps=('nico_unit: '+source+' /work/source/original.h /work/analysis/generated-baseline/generated/config.h /usr/include/stdint.h\n').encode()
        records.append({'context_id':row['context_id'], 'invocation':row['invocation'],
            'execution':{'exit_code':0,'timed_out':False,'output_truncated':False,'duration_ms':1,
                         'output':'','output_sha256':digest(b'')},
            'dependency_bytes':base64.b64encode(deps).decode(),'dependency_sha256':digest(deps),
            'source_dependencies':{**({'main.cpp':request['targets']['main.cpp']} if row['origin']=='original' else {}),
                                   'original.h':request['targets']['original.h']},
            'generated_dependencies':{**({'generated/file.capnp.c++':request['generated_files']['generated/file.capnp.c++']['sha256']} if row['origin']=='generated' else {}),
                                      'generated/config.h':request['generated_files']['generated/config.h']['sha256']},
            'toolchain_dependencies':['/usr/include/stdint.h'], 'error':None})
    return {'schema':'nico.cpp-project-compiler-evidence.v1','request_sha256':digest(json.dumps(request,sort_keys=True,separators=(',',':')).encode()),
            'analyst_uid':1001,'records':records,'duration_ms':5}


def test_controller_reconstructs_context_and_header_populations_not_file_counts(tmp_path):
    raw, targets, captured, _ = inputs(tmp_path)
    request=capability('project_compiler_request')(raw, targets, captured)
    evidence=result_for(request)
    verified=capability('validate_project_compiler')(json.dumps(evidence).encode(),request)
    assert verified['complete'] is True
    assert len(verified['checked_contexts'])==3
    assert set(verified['source_header_inclusions'])=={'original.h'}
    assert set(verified['generated_header_inclusions'])=={'generated/config.h'}
    assert 'generated/unvisited.h' in verified['unvisited_generated_headers']
    assert verified['static_analysis_executed'] is False
    assert verified['object_code_generated'] is False
    assert verified['production_qualified'] is False


@pytest.mark.parametrize('fault',['missing','duplicate','argv','dependency-digest','unbound-header',
    'source-substitution','claim-unvisited','bool-exit','false-complete','time'])
def test_controller_rejects_forged_execution_and_header_evidence(tmp_path,fault):
    raw,targets,captured,_=inputs(tmp_path)
    request=capability('project_compiler_request')(raw,targets,captured)
    evidence=result_for(request); r=evidence['records'][0]
    if fault=='missing': evidence['records'].pop()
    elif fault=='duplicate': evidence['records'][1]=deepcopy(r)
    elif fault=='argv': r['invocation']=['true']
    elif fault=='dependency-digest': r['dependency_sha256']='0'*64
    elif fault=='unbound-header': r['generated_dependencies']['missing.h']='1'*64
    elif fault=='source-substitution': r['source_dependencies']['main.cpp']='0'*64
    elif fault=='claim-unvisited': r['generated_dependencies']['generated/unvisited.h']=request['generated_files']['generated/unvisited.h']['sha256']
    elif fault=='bool-exit': r['execution']['exit_code']=True
    elif fault=='false-complete': evidence['complete']=True
    elif fault=='time': r['execution']['duration_ms']=1000000
    with pytest.raises(ValueError): capability('validate_project_compiler')(json.dumps(evidence).encode(),request)


def test_failed_or_timed_out_context_never_receives_completed_coverage(tmp_path):
    raw,targets,captured,_=inputs(tmp_path)
    request=capability('project_compiler_request')(raw,targets,captured)
    evidence=result_for(request); evidence['records'][1]['execution']['exit_code']=1
    value=capability('validate_project_compiler')(json.dumps(evidence).encode(),request)
    assert value['complete'] is False and len(value['checked_contexts'])==2
    assert request['contexts'][1]['context_id'] not in value['checked_contexts']


@pytest.mark.parametrize('fault', [None, 'exit', 'timeout', 'truncated', 'digest', 'missing', 'compile-failure', 'sink'])
def test_project_probe_runs_compiler_only_after_verified_snapshot_and_retains_native_bytes(tmp_path, fault):
    import inspect
    from nico import assessment_cpp_configuration_probe as probe
    from nico import assessment_cpp_project_compiler as compiler
    from tests.test_cpp_baseline_execution import Native, source, contract
    from tests.test_cpp_project_snapshot import _empty_native_snapshot
    assert 'project_compiler_evidence' in inspect.signature(probe.probe_project_configuration).parameters, 'missing project compiler integration'
    root, targets = source(tmp_path); native=Native(targets); retained={}
    def command(argv,**kwargs):
        if snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            native.calls.append((argv,kwargs))
            raw=json.dumps(_empty_native_snapshot(json.loads(kwargs['input_bytes']))).encode()
        elif compiler.PROGRAM in argv:
            native.calls.append((argv,kwargs))
            request=json.loads(kwargs['input_bytes']); records=[]
            for c in request['contexts']:
                deps=('nico_unit: '+c['analysis_file']+'\n').encode()
                records.append({'context_id':c['context_id'],'invocation':c['invocation'],
                    'execution':{'exit_code':0,'timed_out':False,'output_truncated':False,'duration_ms':1,
                        'output':'','output_sha256':digest(b'')},
                    'dependency_bytes':base64.b64encode(deps).decode(),'dependency_sha256':digest(deps),
                    'source_dependencies':{c['path']:targets[c['path']]},'generated_dependencies':{},
                    'toolchain_dependencies':[],'error':None})
            if fault == 'compile-failure': records[0]['execution']['exit_code']=1
            if fault == 'missing': records.pop()
            raw=json.dumps({'schema':'nico.cpp-project-compiler-evidence.v1','request_sha256':
                '0'*64 if fault=='digest' else digest(compiler._canonical(request)),
                'analyst_uid':1001,'records':records,'duration_ms':5}).encode()
            return {'exit_code':1 if fault=='exit' else 0, 'timed_out':fault=='timeout',
                    'output_truncated':fault=='truncated','output':raw}
        else: return native(argv,**kwargs)
        return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':raw}
    def sink(key,raw):
        retained[key]=raw
        if fault=='sink' and key=='project-compiler-evidence': raise OSError('owned sink failure')
        return {'path':'artifacts/'+key+'-'+digest(raw)+'.json','sha256':digest(raw),'bytes':len(raw)}
    result=probe.probe_project_configuration(root,targets,'sha256:'+'a'*64,project_options={'BUILD_TESTS':'ON'},
        baseline_execution=contract(),capture_generated_context=True,project_compiler_evidence=True,
        retain_artifact=sink,command=command)
    if fault is not None:
        assert result['status']=='UNPROVEN'
        assert result['compiled'] and result['tests_passed'] and result['generated_context_verified']
        assert result['cleanup_verified'] and not result['full_project_qualified']
        assert not result['project_compiler'] or result['project_compiler']['complete'] is False
        assert 'project-compiler-evidence' in retained
        return
    assert result['status']=='BASELINE_EXECUTED'
    assert result['schema']=='nico.cpp-project-configuration-probe.v5'
    assert result['project_compiler']['complete'] is True
    assert result['project_compiler']['static_analysis_executed'] is False
    assert result['full_project_qualified'] is False
    ids=[op['id'] for op in result['operations']]
    assert ids.index('project-generated-context') < ids.index('project-compiler-evidence')
    op=next(op for op in result['operations'] if op['id']=='project-compiler-evidence')
    assert op['output'] is None and op['output_artifact']['sha256']==digest(retained['project-compiler-evidence'])
    invocation, kwargs=next((a,k) for a,k in native.calls if compiler.PROGRAM in a)
    assert '--user=1001:1001' in invocation and kwargs['timeout']<=550


def test_compiler_artifact_sink_uses_same_immutable_digest_contract(tmp_path):
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    raw=b'{"synthetic_compiler_test":true}'
    value=persist_project_artifact(tmp_path,'project-compiler-evidence',raw)
    assert (tmp_path/value['path']).read_bytes()==raw
    assert value['sha256']==digest(raw)


def test_workflow_and_owned_control_require_actual_project_compiler_evidence():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert '--capture-generated-context --project-compiler-evidence' in text
    control=(root/'scripts/qualify_cpp_project_generated_context.py').read_text()
    assert 'project_compiler_evidence=True' in control
    assert "['checked_contexts']" in control


def test_actual_local_gcc_checks_captured_generated_source_and_retains_dependencies(tmp_path):
    """Owned compiler smoke test only; Docker/UID/cgroup proof is hosted."""
    import shutil
    import subprocess
    compiler=shutil.which('g++')
    if compiler is None:
        pytest.skip('native GCC is unavailable in this unit-test environment')
    raw,targets,captured,_=inputs(tmp_path)
    request=capability('project_compiler_request')(raw,targets,captured)
    original=tmp_path/'source'; original.mkdir()
    (original/'main.cpp').write_bytes(b'#include "config.h"\nint main(){return VALUE;}\n')
    analysis=tmp_path/'private'; out=analysis/'compiler-baseline'; out.mkdir()
    for plan in request['contexts']:
        argv=[v.replace('/work/source',str(original)).replace('/work/analysis',str(analysis)) for v in plan['invocation']]
        argv[0]=compiler
        result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        depfile=Path(argv[argv.index('-MF')+1])
        assert b'config.h' in depfile.read_bytes()
        assert not Path(argv[argv.index('-o')+1]).exists()
    assert len(list(out.glob('*.d')))==3


@pytest.mark.parametrize('path', ['/work/build/generated/config.h','/etc/passwd',
    '/work/source/../../etc/passwd','/work/analysis/generated-baseline/../../build/generated/config.h'])
def test_dependency_evidence_cannot_escape_immutable_namespaces(tmp_path,path):
    raw,targets,captured,_=inputs(tmp_path)
    request=capability('project_compiler_request')(raw,targets,captured)
    with pytest.raises(ValueError): capability('_dependency_populations')(('nico_unit: '+path+'\n').encode(),request)


def test_canonical_dependency_paths_preserve_bound_relative_header_includes(tmp_path):
    raw,targets,captured,_=inputs(tmp_path)
    request=capability('project_compiler_request')(raw,targets,captured)
    deps=b'nico_unit: /work/source/sub/../original.h /work/analysis/generated-baseline/generated/sub/../config.h\n'
    original,generated,system=capability('_dependency_populations')(deps,request)
    assert original=={'original.h':targets['original.h']}
    assert generated=={'generated/config.h':captured['files']['generated/config.h']['sha256']}
    assert not system
