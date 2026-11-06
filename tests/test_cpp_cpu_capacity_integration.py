"""Owned-only integration controls; no live host/container capacity measurement."""
import ast
from copy import deepcopy
import inspect
import json
from types import SimpleNamespace
import pytest
from nico import assessment_cpp_cpu_capacity as cpu
from nico import assessment_cpp_project_compiler as compiler
from scripts.cpp_qualification_diagnostics import failure_diagnostic


def observed():
    files={cpu.PROC_CGROUP:b'0::/leaf\n',cpu.PROC_MOUNTS:b'36 25 0:32 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n',
        '/sys/fs/cgroup/leaf/cpu.max':b'400000 100000','/sys/fs/cgroup/cpu.max':b'200000 100000'}
    return cpu.observe(reader=lambda p,n:files[p],affinity=lambda:{2,4,6},cpu_count=lambda:64,workers=4)


def test_generated_reader_matches_reviewed_source_without_live_io():
    ns={};exec(cpu.PROGRAM,ns)
    assert ast.dump(ast.parse(inspect.getsource(cpu.observe)).body[0])==ast.dump(next(n for n in ast.parse(cpu.PROGRAM).body if isinstance(n,ast.FunctionDef) and n.name=='observe'))
    result=ns['observe'](reader=lambda p,n:(_ for _ in ()).throw(OSError('PRIVATE')),affinity=lambda:{1},cpu_count=lambda:128,workers=4)
    assert result['observation_scope']=='collector_thread' and result['affinity_count']==1
    assert result['effective_capacity_state']=='unknown'
    embedded={};exec(compiler.PROGRAM.rsplit('\nrun_project_compiler()',1)[0],embedded)
    assert embedded['CPU_OBSERVATION_PROGRAM']==cpu.PROGRAM
    assert 'pidfd' not in compiler.PROGRAM


def test_observer_exception_only_yields_unavailable(monkeypatch):
    monkeypatch.setattr(compiler,'CPU_OBSERVATION_PROGRAM',"raise RuntimeError('PRIVATE')")
    assert compiler._observe_cpu_capacity(4)==cpu.unavailable()


@pytest.mark.parametrize('elapsed',[0.0,600.0])
def test_observation_is_inside_shared_deadline_and_does_not_change_commands(monkeypatch,elapsed):
    import resource
    class OwnedPath:
        def __init__(self,*args):pass
        def lstat(self):return SimpleNamespace(st_uid=1001,st_mode=0o700)
        def resolve(self,**kwargs):return self
        def __truediv__(self,child):return self
        def mkdir(self,**kwargs):pass
        def __str__(self):return '/owned-no-files'
    clock=[0.0];calls=[];snapshots=[]
    context={'index':0,'context_id':'owned','invocation':['owned-compiler','-fsyntax-only'],'analysis_file':'owned.cpp','origin':'original','path':'owned.cpp'}
    request={'schema':'nico.cpp-project-compiler-request.v2','limits':dict(compiler.EXTENDED_LIMITS),'contexts':[context],'generated_files':{},'targets':{'owned.cpp':'a'*64}}
    monkeypatch.setattr(compiler,'Path',OwnedPath)
    monkeypatch.setattr(compiler.os,'getuid',lambda:1001);monkeypatch.setattr(compiler.os,'getgid',lambda:1001)
    monkeypatch.setattr(resource,'setrlimit',lambda *a:None)
    monkeypatch.setattr(compiler.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(compiler,'_syntax_argv',lambda *a:(context['invocation'],context['analysis_file']))
    monkeypatch.setattr(compiler,'_verify_input',lambda *a:None)
    def observe(workers):snapshots.append(workers);clock[0]=elapsed;return cpu.unavailable()
    monkeypatch.setattr(compiler,'_observe_cpu_capacity',observe)
    def run(argv,stem,deadline,environment):
        calls.append((argv,deadline,environment))
        return {'exit_code':1,'timed_out':False,'output_truncated':False}
    monkeypatch.setattr(compiler,'_run',run)
    result=compiler.collect_project_compiler(request)
    assert snapshots==[4] and result['cpu_capacity']==cpu.unavailable()
    assert [r['context_id'] for r in result['records']]==['owned']
    assert request['limits']=={'wall_seconds':600,'case_seconds':90,'parallel':4}
    if elapsed:
        assert not calls and result['records'][0]['execution'] is None
        assert result['records'][0]['error']=='worker_project_compiler_deadline'
    else:
        assert calls[0][0]==context['invocation'] and calls[0][1]==90
        assert result['records'][0]['execution']['exit_code']==1


@pytest.mark.parametrize('observation',[None,{'secret':'PRIVATE'},True,'PRIVATE'])
@pytest.mark.parametrize('success',[True,False])
def test_optional_diagnostics_never_change_compiler_acceptance(tmp_path,observation,success):
    from tests.test_cpp_project_compiler import inputs,result_for
    raw,targets,captured,_=inputs(tmp_path)
    request=compiler.project_compiler_request(raw,targets,captured)
    evidence=result_for(request)
    if not success:evidence['records'][0]['execution']['exit_code']=1
    old=compiler.validate_project_compiler(json.dumps(evidence).encode(),request)
    evidence['cpu_capacity']=observation
    new=compiler.validate_project_compiler(json.dumps(evidence).encode(),request)
    # Native bytes/identity honestly change; all acceptance and coverage fields do not.
    old.pop('native_evidence_sha256');new.pop('native_evidence_sha256')
    assert new==old and new['complete'] is success and new['production_qualified'] is False


@pytest.mark.parametrize('key,value',[('effective_capacity_state','verified'),('qualification_credit',True),
    ('observation_scope','compiler_child'),('observation_consistency','atomic'),('affinity_count',True),
    ('configured_workers',257),('visible_levels_read',65),('errors',['PRIVATE']),('visible_ceiling_numerator',1000),
    ('visible_quota_numerator',10**13),('extra','PRIVATE')])
def test_malformed_observation_is_unknown_and_never_prints_private_fields(key,value):
    raw=observed();raw[key]=value
    projected=cpu.summarize(raw);assert projected==cpu.unavailable('invalid')
    result=failure_diagnostic({'probe':{'project_compiler_cpu_capacity':raw,'project_compiler_requested_cpus':4}},ValueError('qualification_failed'))
    assert result['compiler_cpu_capacity']['observation']==cpu.unavailable('invalid')
    assert 'PRIVATE' not in json.dumps(result)


def test_console_distinguishes_requested_worker_affinity_and_visible_quota():
    raw=observed();assert cpu.summarize(raw)==raw
    result=failure_diagnostic({'probe':{'project_compiler_cpu_capacity':raw,'project_compiler_requested_cpus':4}},ValueError('qualification_failed'))
    diagnostic=result['compiler_cpu_capacity'];assert diagnostic['requested_cpus']==4
    assert diagnostic['observation']['configured_workers']==4
    assert diagnostic['observation']['affinity_count']==3
    assert diagnostic['observation']['visible_quota_numerator']==2
    assert diagnostic['observation']['os_cpu_count']==64
    assert diagnostic['observation']['effective_capacity_state']=='unknown'
    assert len(json.dumps(result).encode())<4096
    assert all(s not in json.dumps(result) for s in ('/proc','/sys','PRIVATE'))


def test_configuration_probe_uses_same_analyst_invocation_and_requested_resources():
    from nico import assessment_cpp_configuration_probe as probe
    text=inspect.getsource(probe)
    assert "['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name," in text
    assert "'python3', '-I', '-S', '-c', PROGRAM]" in text
    assert "seconds=request['limits']['wall_seconds'] + 10" in text
    assert "result['project_compiler_requested_cpus'] = int(resources['cpus'])" in text


@pytest.mark.parametrize('transport_fault',[None,'output_truncated','timed_out','exit_code'])
def test_transport_failure_suppresses_even_complete_json_cpu_prefix(tmp_path,monkeypatch,transport_fault):
    from nico import assessment_cpp_configuration_probe as probe
    from tests.test_cpp_compiler_budget_v2 import probe_fixture
    real=probe.probe_project_configuration
    observation=observed()
    from functools import wraps
    @wraps(real)
    def with_owned_transport(*args,**kwargs):
        command=kwargs['command']
        def wrapped(argv,**options):
            response=command(argv,**options)
            if compiler.PROGRAM in argv:
                # Retained bytes form complete valid JSON even when transport
                # reports loss, so JSON parsing alone cannot justify projection.
                native=json.loads(response['output']);native['cpu_capacity']=observation
                response={**response,'output':compiler._canonical(native)}
                if transport_fault:response[transport_fault]=7 if transport_fault=='exit_code' else True
            return response
        kwargs['command']=wrapped
        return real(*args,**kwargs)
    monkeypatch.setattr(probe,'probe_project_configuration',with_owned_transport)
    result,_,_,static_calls=probe_fixture(tmp_path,monkeypatch,version='v2')
    assert result['project_compiler_requested_cpus']==4
    if transport_fault:
        assert result['project_compiler_cpu_capacity']==cpu.unavailable()
        assert result['error']=='worker_configuration_probe_compiler_failed'
        assert result['project_compiler'] is None and not static_calls
    else:assert result['project_compiler_cpu_capacity']==observation
