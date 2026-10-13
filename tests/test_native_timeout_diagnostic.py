"""Owned tests for diagnostic-only replay; never a production acceptance waiver."""
import json
import pytest
from scripts.native_timeout_diagnostic import (
    isolated_ctest_argv, metrics_delta, provision_script, diagnostic_status,
)


def test_isolated_selection_preserves_original_timeout_and_requires_exact_membership():
    argv = isolated_ctest_argv(["other", "slow.test+"], "slow.test+", 300)
    assert argv == ["ctest", "--test-dir", "/work/sanitize-address", "--parallel", "1",
                    "--timeout", "300", "--output-on-failure", "--output-junit",
                    "/work/sanitize-address/nico-diagnostic-junit.xml", "-R", r"^slow\.test\+$"]


@pytest.mark.parametrize("names,name,seconds", [
    (["a"], "b", 300), (["a", "a"], "a", 300), ([], "a", 300),
    (["a"], "a", True), (["a"], "a", 301), (["a"], "a", 0),
    (["a"], "a", 3.0), (["a\n"], "a\n", 300),
])
def test_invalid_selection_is_rejected(names, name, seconds):
    with pytest.raises(ValueError):
        isolated_ctest_argv(names, name, seconds)


def test_resource_deltas_preserve_unknown_and_do_not_infer_oom_from_peak():
    before = {"cpu": {"usage_usec": 10, "throttled_usec": 3}, "memory_events": {"oom_kill": 0}, "memory_peak_bytes": 100}
    after = {"cpu": {"usage_usec": 45, "throttled_usec": 5}, "memory_events": {"oom_kill": 0}, "memory_peak_bytes": 12*1024**3}
    assert metrics_delta(before, after) == {"cpu": {"usage_usec": 35, "throttled_usec": 2}, "memory_events": {"oom_kill": 0}}
    assert metrics_delta({}, after) == {"cpu": None, "memory_events": None}
    assert metrics_delta(after, before)["cpu"] is None


@pytest.mark.parametrize("runtime,static,boundary,cleanup,expected", [
    (True, True, True, True, "ISOLATED_CASES_COMPLETED"),
    (False, True, True, True, "INCOMPLETE"),
    (True, False, True, True, "INCOMPLETE"),
    (True, True, False, True, "INCOMPLETE"),
    (True, True, True, False, "INCOMPLETE"),
])
def test_diagnostic_can_never_be_qualified(runtime, static, boundary, cleanup, expected):
    value = diagnostic_status(runtime, static, boundary, cleanup)
    assert value == {"status": expected, "production_qualified": False,
                     "full_project_qualified": False, "assessment_completed": False}


def test_provisioning_uses_the_existing_exact_recipe_without_assessed_source():
    from pathlib import Path
    workflow = Path(".github/workflows/cpp-full-project-integration.yml").read_text()
    text = provision_script(workflow, "Provision exact tools without assessed source or runtime network")
    assert "docker build --network=none" in text
    assert "assessment-full-project-fuzz.Dockerfile" in text
    assert "qualification-input" not in text
    assert "git fetch" not in text
    assert "GITHUB_TOKEN" not in text


def test_missing_or_ambiguous_recipe_is_rejected():
    with pytest.raises(ValueError):
        provision_script("jobs: {}", "missing")


@pytest.mark.parametrize('metadata', ['', '        id: collection_image\n'])
def test_recipe_step_id_preserves_exact_script_and_step_boundary(metadata):
    workflow = ('  project-baseline-qualification:\n'
        '      - name: Provision\n' + metadata + '        run: |\n'
        '          set -euo pipefail\n'
        '          docker build --network=none .\n'
        '      - name: Next\n        run: |\n          echo excluded\n')
    assert provision_script(workflow, 'Provision') == (
        'set -euo pipefail\ndocker build --network=none .\n')
    with pytest.raises(ValueError, match='diagnostic_recipe_step_invalid'):
        provision_script(workflow + '      - name: Provision\n        run: |\n          echo duplicate\n', 'Provision')


@pytest.mark.parametrize('metadata', [
    '        id: ${{ inputs.id }}\n', '        id: collection image\n',
    '        id: one\n        id: two\n', '        if: always()\n',
    '        env:\n          KEY: value\n', '        uses: some/action\n',
])
def test_recipe_rejects_unsupported_step_metadata(metadata):
    workflow = ('  project-baseline-qualification:\n'
        '      - name: Provision\n' + metadata + '        run: |\n          echo recipe\n')
    with pytest.raises(ValueError, match='diagnostic_recipe_step_invalid'):
        provision_script(workflow, 'Provision')


@pytest.mark.parametrize('script', ['', '          echo ${{ secrets.TOKEN }}\n'])
def test_recipe_step_id_does_not_allow_empty_or_interpolated_script(script):
    workflow = ('  project-baseline-qualification:\n'
        '      - name: Provision\n        id: collection_image\n        run: |\n' + script)
    with pytest.raises(ValueError, match='diagnostic_recipe_interpolation_unsupported'):
        provision_script(workflow, 'Provision')


def test_malformed_unhashable_test_name_is_a_selection_error():
    with pytest.raises(ValueError, match='diagnostic_test_selection_invalid'):
        isolated_ctest_argv([{}], 'a', 300)


def test_isolated_fallback_changes_only_selected_population(tmp_path):
    from copy import deepcopy
    from scripts import native_timeout_diagnostic as diagnostic
    from tests.test_cpp_clang_fallback import primary_with_one_failure, api
    primary, proof = primary_with_one_failure(tmp_path)
    original = api().clang_fallback_request(primary, proof, extended_budget=True)
    preserved = deepcopy(original)
    selected = diagnostic.isolated_fallback_request(original, original['contexts'][0]['context_id'])
    assert original == preserved
    assert selected['contexts'] == [original['contexts'][0]]
    assert selected['limits'] == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 4}
    assert {k:v for k,v in selected.items() if k!='contexts'} == {k:v for k,v in original.items() if k!='contexts'}
    selected['contexts'][0]['invocation'].append('changed')
    assert original == preserved
    with pytest.raises(ValueError):
        diagnostic.isolated_fallback_request(original, 'unknown')


def _sandbox_fixture(tmp_path, fault=None):
    from scripts import native_timeout_diagnostic as diagnostic
    from tests.test_cpp_project_static_stage import StaticDocker, stage_inputs
    source, targets, *_ = stage_inputs(tmp_path)
    class Transport(StaticDocker):
        def __call__(self, argv, **kwargs):
            if diagnostic.RESOURCE_PROGRAM in argv:
                self.calls.append((argv,kwargs))
                value = {'scratch_capacity_bytes': 1 if fault=='scratch' else 9663676416,
                         'scratch_available_bytes': 9663676416, 'cpu':{},'memory_events':{}}
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':json.dumps(value).encode()}
            if argv[-1:] == ['owned-failure']:
                self.calls.append((argv,kwargs))
                return {'exit_code':7,'timed_out':False,'output_truncated':False,'output':b'preserved native failure'}
            if argv[-1:] == ['owned-transport-failure']:
                self.calls.append((argv,kwargs))
                raise OSError('owned transport unavailable')
            return super().__call__(argv, **kwargs)
    transport=Transport(targets, fault)
    return diagnostic.Sandbox(source, targets, 'sha256:'+'a'*64, tmp_path/'diagnostic',
        executable=False, seconds=60, command=transport), transport


def test_real_wrapper_enforces_boundary_and_retains_native_failure_before_raising(tmp_path):
    box, transport = _sandbox_fixture(tmp_path)
    with pytest.raises(ValueError, match='diagnostic_operation_failed:owned'):
        with box:
            box.exec('owned',['owned-failure'])
    assert box.receipt['cleanup_verified']
    assert box.receipt['boundary_verified'] and box.receipt['scratch_capacity_verified']
    assert box.receipt['production_qualified'] is False
    row = next(r for r in box.receipt['operations'] if r['id']=='owned')
    assert row['exit_code']==7
    assert (box.output/row['output_path']).read_bytes()==b'preserved native failure'
    create = next(a for a,k in transport.calls if a[1]=='create')
    assert '--network=none' in create and '--read-only' in create and '--cap-drop=ALL' in create
    assert '--memory=12g' in create and '--cpus=4' in create and '--memory-swap=12g' in create
    assert '--tmpfs=/work:rw,nosuid,nodev,noexec,size=9663676416,mode=1777' in create
    assert not any(a in create for a in ['-v','--mount','--privileged'])


def test_scratch_mismatch_blocks_native_execution_and_still_cleans_up(tmp_path):
    box, transport = _sandbox_fixture(tmp_path, 'scratch')
    with pytest.raises(ValueError, match='diagnostic_scratch_capacity_mismatch'):
        with box:
            box.exec('owned',['owned-failure'])
    assert box.receipt['cleanup_verified'] and not box.receipt['scratch_capacity_verified']
    assert not any(a[-1:] == ['owned-failure'] for a,k in transport.calls)


def test_transport_exception_is_retained_without_inventing_an_exit_status(tmp_path):
    box, transport = _sandbox_fixture(tmp_path)
    with pytest.raises(OSError):
        with box:
            box.exec('transport',['owned-transport-failure'])
    row=next(r for r in box.receipt['operations'] if r['id']=='transport')
    assert row['exit_code'] is None and row['error']=='OSError'
    assert box.receipt['cleanup_verified']


def test_bad_image_does_not_mask_identity_failure_with_cleanup_failure(tmp_path):
    box, transport = _sandbox_fixture(tmp_path, 'image')
    with pytest.raises(ValueError, match='diagnostic_image_mismatch'):
        with box: pass
    assert not any(a[1]=='create' for a,k in transport.calls)
    assert box.receipt['cleanup_required'] is False and box.receipt['cleanup_verified'] is True


def test_cleanup_executes_after_deadline_without_extending_native_budget(tmp_path):
    box, transport = _sandbox_fixture(tmp_path)
    with pytest.raises(ValueError, match='diagnostic_deadline'):
        with box:
            box.deadline=0
            box.exec('expired',['owned-failure'])
    assert box.receipt['cleanup_verified']
    assert not any(a[-1:] == ['owned-failure'] for a,k in transport.calls)
    assert any(a[1:3]==['rm','--force'] for a,k in transport.calls)


def test_cleanup_failure_keeps_existing_native_exception_and_failed_cleanup(tmp_path):
    box, transport = _sandbox_fixture(tmp_path, 'cleanup')
    with pytest.raises(ValueError, match='diagnostic_operation_failed:owned'):
        with box: box.exec('owned',['owned-failure'])
    assert box.receipt['cleanup_verified'] is False
    assert box.receipt['cleanup_error']=='diagnostic_cleanup_unproven'


def test_static_diagnostic_uses_unchanged_native_collector_and_keeps_full_scope_unqualified(tmp_path,monkeypatch):
    from scripts import native_timeout_diagnostic as diagnostic
    from tests.test_cpp_project_static_stage import stage_inputs, StaticDocker
    from tests.test_cpp_clang_fallback import primary_with_one_failure, fallback_native, api
    from nico.assessment_cpp_project_compiler import _canonical
    source,targets,_,snapshot,_=stage_inputs(tmp_path)
    independent=tmp_path/'independent'; independent.mkdir()
    primary,proof=primary_with_one_failure(independent)
    original=api().clang_fallback_request(primary,proof,extended_budget=True)
    context=original['contexts'][0]
    selected={'context':context,'fallback_request':diagnostic.isolated_fallback_request(original,context['context_id']),
              'primary_request':primary}
    class Transport(StaticDocker):
        def __call__(self,argv,**kwargs):
            if api().PROGRAM in argv:
                self.calls.append((argv,kwargs))
                assert '--user=1001:1001' in argv
                request=json.loads(kwargs['input_bytes'])
                assert request==selected['fallback_request']
                return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':_canonical(fallback_native(request))}
            if diagnostic.RESOURCE_PROGRAM in argv:
                self.calls.append((argv,kwargs))
                return {'exit_code':0,'timed_out':False,'output_truncated':False,
                    'output':_canonical({'cpu':{'usage_usec':1},'memory_events':{'oom_kill':0},'scratch_capacity_bytes':9663676416})}
            return super().__call__(argv,**kwargs)
    transport=Transport(targets)
    real=diagnostic.Sandbox
    monkeypatch.setattr(diagnostic,'Sandbox',lambda *a,**k:real(*a,**k,command=transport))
    result=diagnostic.run_static(source,targets,'sha256:'+'a'*64,tmp_path/'isolated',selected,snapshot)
    assert result['complete'] and result['cleanup_verified'] and result['boundary_verified']
    assert result['selected_contexts_count']==1
    assert result['retained_required_contexts_count']==len(original['required_contexts'])
    assert result['production_qualified'] is False and result['full_project_qualified'] is False
    assert result['exit_code']==0 and result['native_duration_ms'] is not None
    assert (tmp_path/'isolated/analysis.plist').exists()
    assert any(api().PROGRAM in argv for argv,k in transport.calls)
    assert not any(argv[-1:]==['clang++'] for argv,k in transport.calls)


def test_workflow_serializes_with_existing_native_run_and_has_no_write_permission():
    from pathlib import Path
    workflow=Path('.github/workflows/native-timeout-diagnostic.yml').read_text()
    assert 'group: cpp-full-project-integration-refs/pull/1722/merge' in workflow
    qualification=Path('.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'group: cpp-full-project-integration-${{ github.ref }}' in qualification
    assert 'queue: max' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert 'actions: read' in workflow and 'contents: read' in workflow
    import re
    assert not re.search(r'^\s+[a-z-]+:\s*write\s*$',workflow,re.M) and 'secrets.' not in workflow
    assert 'timeout-minutes: 55' in workflow
    assert '38380333159' in workflow and 'case "$conclusion"' in workflow
    assert 'success)' in workflow and 'failure)' in workflow
    assert '11811288494' in workflow
    assert 'dbf890120e44a7d0f99133d69f316c9e8d7dce0210f3ae627e248ffa1c4e7e92' in workflow
    assert '--mode current-primary-budget-v1' in workflow
    assert '--mode current-primary\n' not in workflow
    assert 'types: [synchronize]' in workflow and 'github.run_attempt == 1' in workflow
    assert '--execution-policy-sha256' in workflow
    assert 'owned_primary_control' in workflow
    assert workflow.index('Exercise the owned static-only boundary first') < workflow.index('Measure only basic.cpp under the declared 180-second case policy')
    assert '--test cluster_linearize_tests' not in workflow
    assert 'diagnostic/current-primary-38380333159' in workflow


def _current_selection_fixture():
    from scripts import native_timeout_diagnostic as d
    contexts=[{} for _ in range(577)]; records=[{} for _ in range(577)]
    for index,path in d.CURRENT_CASES.items():
        argv=['/usr/local/bin/cppcheck','--xml','-j1','--project=/work/analysis/static-baseline/u'+str(index)+'.json']
        contexts[index]={'index':index,'path':path,'context_id':str(index),'analyzer_invocation':argv,
                         'analyzer_database_sha256':'a'*64}
        records[index]={'context_id':str(index),'invocation':argv,
                        'execution':{'exit_code':None if index!=10 else 0,
                                     'timed_out':index!=10,'output_truncated':False,'duration_ms':114}}
    return {'primary_request':{'schema':'nico.cpp-project-static-request.v4','contexts':contexts,
            'limits':{'wall_seconds':540,'case_seconds':90,'parallel':2}},'primary_raw':{'records':records}}


def test_current_selection_retains_original_commands_population_and_evidence():
    from copy import deepcopy
    from scripts import native_timeout_diagnostic as d
    retained=_current_selection_fixture(); before=deepcopy(retained)
    selected=d.select_primary_cases(retained)
    assert retained==before
    assert [r['index'] for r in selected]==[2,4,10]
    for row in selected:
        assert row['invocation']==before['primary_request']['contexts'][row['index']]['analyzer_invocation']+['--showtime=file','--report-progress=1']


@pytest.mark.parametrize('fault',['population','path','timeout','command','budget'])
def test_current_selection_rejects_drift_before_dispatch(fault):
    from scripts import native_timeout_diagnostic as d
    retained=_current_selection_fixture()
    if fault=='population':retained['primary_request']['contexts'].pop()
    if fault=='path':retained['primary_request']['contexts'][2]['path']='different.cpp'
    if fault=='timeout':retained['primary_raw']['records'][4]['execution']['timed_out']=False
    if fault=='command':retained['primary_raw']['records'][10]['invocation']=['different']
    if fault=='budget':retained['primary_request']['limits']['case_seconds']=91
    with pytest.raises(ValueError,match='diagnostic_current_'):
        d.select_primary_cases(retained)


def _primary_adapter_namespace():
    import ast,time
    from scripts import native_timeout_diagnostic as d
    program=ast.parse(d.primary_program())
    compile(program,'current-primary-program','exec')
    nodes=[n for n in program.body if (
        isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'original_run','stage_counters_enabled','stage_allowed_commands'} for t in n.targets))
        or isinstance(n,ast.ClassDef) and n.name=='ThreadPoolExecutor']
    # Only the final diagnostic _run adapter, not the production collector runner.
    nodes.insert(0,[n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='analyzer_environment'][0])
    nodes.append([n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='_run'][-1])
    calls=[]
    def fake_run(argv,stem,deadline,environment):
        calls.append((argv,stem,deadline,environment));return {'owned':True}
    ns={'_run':fake_run,'time':time,'_canonical':lambda x:json.dumps(x).encode()}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'owned-adapter','exec'),ns)
    return ns,calls


def test_diagnostic_scheduler_runs_only_reviewed_indices_and_retains_partial_records(capsys):
    ns,_=_primary_adapter_namespace(); retained=_current_selection_fixture(); seen=[]
    with ns['ThreadPoolExecutor'](2) as pool:
        result=list(pool.map(lambda c:seen.append(c['index']) or {'context_id':c['context_id']},retained['primary_request']['contexts']))
    assert seen==[2,4,10] and len(result)==3
    assert len(capsys.readouterr().out.splitlines())==3
    with pytest.raises(ValueError,match='diagnostic_parallel_contract'): ns['ThreadPoolExecutor'](4)
    with pytest.raises(ValueError,match='diagnostic_population'):
        list(ns['ThreadPoolExecutor'](2).map(lambda c:pytest.fail('must not dispatch'),[{}]*475))


def test_diagnostic_instrumentation_only_appends_flags_and_never_extends_deadline():
    import time
    ns,calls=_primary_adapter_namespace()
    argv=['/usr/local/bin/cppcheck','--xml','--enable=warning','-j1']
    deadline=time.monotonic()+20;env={'EXACT':'retained'}
    ns['_run'](argv,'stem',deadline,env)
    assert calls[0]==(argv+['--showtime=file','--report-progress=1'],'stem',deadline,env)
    ns['_run'](['/usr/local/bin/cppcheck','--version'],'v',deadline,env)
    assert calls[1][0]==['/usr/local/bin/cppcheck','--version']
    assert argv==['/usr/local/bin/cppcheck','--xml','--enable=warning','-j1']


def test_partial_timeout_and_findings_are_retained_with_executed_argv(capsys):
    ns,_=_primary_adapter_namespace(); retained=_current_selection_fixture()
    def failed(context):
        return {'context_id':context['context_id'],'invocation':context['analyzer_invocation'],
                'execution':{'timed_out':True,'exit_code':None,'output':'retained phase output'},
                'xml':'partial XML with target findings','error':'worker_project_static_unavailable'}
    records=list(ns['ThreadPoolExecutor'](2).map(failed,retained['primary_request']['contexts']))
    partial=[json.loads(line)['diagnostic_partial_record'] for line in capsys.readouterr().out.splitlines()]
    assert records==partial and len(partial)==3
    for row in partial:
        assert row['execution']['timed_out'] is True
        assert row['execution']['output']=='retained phase output'
        assert row['xml']=='partial XML with target findings'
        assert row['executed_invocation']==row['invocation']+['--showtime=file','--report-progress=1']


def test_owned_control_is_static_only_and_uses_existing_noexec_boundary(tmp_path,monkeypatch):
    from scripts import native_timeout_diagnostic as d
    calls=[]
    class OwnedBox:
        def __init__(self,source,targets,image,output,**kwargs):
            assert kwargs=={'executable':False,'seconds':60}
            assert set(targets)=={'owned.cpp'}
            self.receipt={'cleanup_verified':True}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def exec(self,key,argv,**kwargs):calls.append((key,argv,kwargs))
    monkeypatch.setattr(d,'Sandbox',OwnedBox)
    d.owned_primary_control('sha256:'+'a'*64,tmp_path/'control')
    assert len(calls)==1 and calls[0][1][0]=='/usr/local/bin/cppcheck'
    assert calls[0][2]=={'user':'1001:1001','seconds':30}
    assert '--showtime=file' in calls[0][1] and '--report-progress=1' in calls[0][1]


def test_current_export_hashes_every_member_and_rejects_tool_or_path_drift(tmp_path,monkeypatch):
    import zipfile,hashlib
    from scripts import native_timeout_diagnostic as d
    files={'cppcheck':b'owned executable bytes','nico-clang-header-observer.so':b'owned observer',
           'image-config-digest.txt':d.CURRENT_IMAGE.encode(),
           'image.json':json.dumps([{'Id':d.CURRENT_IMAGE}]).encode()}
    files.update({'cfg/model'+str(i):b'owned' for i in range(70)})
    hashes={k:{'size_bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in files.items()}
    monkeypatch.setattr(d,'CURRENT_TOOLS',{k:hashes[k]['sha256'] for k in d.CURRENT_TOOLS})
    def archive(tamper=False):
        target=tmp_path/('bad.zip' if tamper else 'good.zip')
        with zipfile.ZipFile(target,'w') as z:
            z.writestr('cpp-collection-toolchain-manifest.json',json.dumps({'schema':'nico.cpp-collection-tool-export.v1','image_config_digest':d.CURRENT_IMAGE,'files':hashes}))
            for name,raw in files.items():z.writestr('cpp-collection-toolchain/'+name,raw+b'changed' if tamper and name=='cfg/model69' else raw)
        return zipfile.ZipFile(target)
    receipt={'producer_source_sha':d.CURRENT_PRODUCER,'probe':{'image_config_digest':d.CURRENT_IMAGE}}
    with archive() as z:d.verify_current_export(z,receipt)
    with archive(True) as z,pytest.raises(ValueError,match='diagnostic_current_export_digest'):d.verify_current_export(z,receipt)


@pytest.mark.parametrize('native_timeout',[False,True])
@pytest.mark.parametrize('resource_deadline',[False,True])
def test_primary_controller_restores_and_matches_environment_and_retains_failure(tmp_path,monkeypatch,native_timeout,resource_deadline):
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_cpp_static_environment as env
    retained=_current_selection_fixture()
    retained.update(snapshot={'files':{},'file_population_sha256':'b'*64},
                    compiler_request={'generated_files':{}},compiler_raw=b'owned',environment={'models':'owned'})
    monkeypatch.setattr(env,'environment_request',lambda *a,**k:{'owned':True})
    monkeypatch.setattr(env,'validate_environment',lambda *a:{'models':'owned'})
    calls=[]
    class Box:
        def __init__(self,*a,**k):
            assert k=={'executable':False,'seconds':540}
            self.receipt={'boundary_verified':True,'cleanup_verified':False}
        def __enter__(self):return self
        def __exit__(self,*a):self.receipt['cleanup_verified']=True
        def save(self):pass
        def resources(self,key):
            if key=='resources-after' and resource_deadline:
                # Native outcome must already be retained before this checkpoint.
                assert self.receipt['result']['timed_out'] is native_timeout
                assert self.receipt['result']['exit_code'] == (None if native_timeout else 0)
                raise ValueError('diagnostic_deadline')
            return {'cpu':{},'memory_events':{}}
        def exec(self,key,argv,**kwargs):
            calls.append((key,argv,kwargs))
            assert kwargs['user']=='1001:1001'
            if key=='tool-identity':value={'/usr/local/bin/cppcheck':d.CURRENT_TOOLS['cppcheck'],'/opt/nico-clang-header-observer.so':d.CURRENT_TOOLS['nico-clang-header-observer.so']}
            elif key=='generated-restore':value={'files':{},'file_population_sha256':'b'*64}
            elif key=='environment':value={}
            else:
                assert key=='current-primary' and kwargs['seconds']==540 and kwargs['require'] is False
                assert json.loads(kwargs['data'])==retained['primary_request']
                rows=[{'context_id':str(i),'execution':{'exit_code':0,'timed_out':False,'output_truncated':False},'error':None} for i in (2,4,10)]
                value={'schema':'nico.current-primary-diagnostic.v1','records':rows}
                return {'output':json.dumps(value).encode(),'exit_code':None if native_timeout else 0,'timed_out':native_timeout,'output_truncated':False}
            return {'output':json.dumps(value).encode()}
    monkeypatch.setattr(d,'Sandbox',Box)
    result=d.run_primary(tmp_path,{},'sha256:'+'c'*64,tmp_path/'output',retained)
    assert result['complete'] is (not native_timeout and not resource_deadline)
    assert result['timed_out'] is native_timeout
    assert result['output_truncated'] is False
    if resource_deadline:
        assert result['resources_after_unavailable']=='diagnostic_deadline'
        assert result['resources_delta'] is None
    assert result['cleanup_verified'] and result['production_qualified'] is False
    assert result['unselected_contexts']==574 and result['original_image_replay'] is False
    assert [r[0] for r in calls]==['tool-identity','generated-restore','environment','current-primary']


@pytest.mark.parametrize('close_streams', [False, True])
@pytest.mark.parametrize('require', [False, True])
def test_outer_deadline_preserves_real_command_output_before_error(tmp_path, close_streams, require):
    import hashlib
    import os
    import sys
    import time
    from scripts.native_timeout_diagnostic import Sandbox

    box = Sandbox(tmp_path, {}, 'sha256:'+'a'*64, tmp_path/'deadline',
                  executable=False, seconds=540)
    # Exercise the real command boundary at an abbreviated outer deadline.
    # Only this owned Python child runs; no container or assessed input is used.
    box.deadline = time.monotonic() + 0.5
    program = ("import os,time; print('owned partial finding pid='+str(os.getpid()),flush=True); "
               + ('os.close(1); os.close(2); ' if close_streams else '')
               + 'time.sleep(30)')
    argv = [sys.executable, '-I', '-S', '-c', program]
    if require:
        with pytest.raises(ValueError, match='^diagnostic_deadline$'):
            box.call('owned-deadline', argv, seconds=540, limit=1024)
    else:
        native = box.call('owned-deadline', argv, seconds=540, limit=1024, require=False)
        assert native['timed_out'] and native['exit_code'] == 124
    receipt = json.loads((box.output/'receipt.json').read_bytes())
    row = receipt['operations'][-1]
    assert receipt['budget_seconds'] == 540
    assert row['timed_out'] is True and row['exit_code'] == 124
    assert row['output_truncated'] is False
    raw = (box.output/row['output_path']).read_bytes()
    assert raw.startswith(b'owned partial finding pid=') and raw.endswith(b'\n')
    assert row['output_bytes'] == len(raw) <= 1024
    assert row['output_sha256'] == hashlib.sha256(raw).hexdigest()
    pid = int(raw.split(b'=')[1])
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    # A spent budget cannot start another operation, but cleanup remains allowed.
    with pytest.raises(ValueError, match='^diagnostic_deadline$'):
        box.call('must-not-start', [sys.executable, '-c', 'raise SystemExit(99)'])
    assert len(box.receipt['operations']) == 1
    cleaned = box.call('owned-cleanup', [sys.executable, '-I', '-S', '-c', "print('cleanup')"],
                       cleanup=True, seconds=5)
    assert cleaned['exit_code'] == 0 and cleaned['output'] == b'cleanup\n'


@pytest.mark.parametrize('projected_receipt', [False, True])
def test_retained_native_database_reconstructs_snapshot_population_without_replacing_original(tmp_path, projected_receipt):
    import base64
    from copy import deepcopy
    from scripts import native_timeout_diagnostic as d
    from tests.test_cpp_native_command_transport import run_case
    from nico.assessment_cpp_project_compiler import project_compiler_request
    from scripts.qualify_cpp_project_configuration import qualification_probe_receipt
    probe,targets,docker,out,_ = run_case(tmp_path)
    if projected_receipt:
        probe = qualification_probe_receipt(probe)
        assert 'analysis_compilation_database' not in probe
    original = base64.b64decode(probe['compilation_database'], validate=True)
    artifacts = {row['id']:(out/row['output_artifact']['path']).read_bytes()
                 for row in probe['operations'] if row.get('output_artifact')}
    snapshot = json.loads(artifacts['project-generated-context'])
    before = deepcopy(probe)
    with pytest.raises(ValueError, match='worker_generated_project_snapshot_invalid'):
        project_compiler_request(original,targets,snapshot,extended_budget=True)
    analysis = d.reconstruct_current_database(probe,targets,original,artifacts)
    request = project_compiler_request(analysis,targets,snapshot,extended_budget=True)
    assert probe == before and original == docker.database
    assert analysis != original and len(request['contexts']) == 2
    assert request['database_sha256'] == probe['analysis_compilation_database_sha256']
    # The owned transport uses the standard compiler budget; compare every
    # identity/input/command field with the extended-budget reconstruction.
    assert {k:v for k,v in request.items() if k not in {'schema','limits'}} == {
        k:v for k,v in docker.compiler_request.items() if k not in {'schema','limits'}}
    for fault in ('database','analysis_digest','plan','freeze','cache','membership','membership_summary','native_post'):
        changed=deepcopy(probe); retained=dict(artifacts); raw=original
        if fault=='database': raw += b' '
        if fault=='analysis_digest': changed['analysis_compilation_database_sha256']='0'*64
        if fault=='plan': changed['native_command_plan']['context_count']=1
        if fault=='freeze': changed['native_command_freeze']={}
        if fault=='cache': changed['configuration_cache_sha256']='0'*64
        if fault=='membership': retained['project-enabled-targets-post-build'] += b' '
        if fault=='membership_summary': changed['enabled_target_membership']['configured_context_count']=1
        if fault=='native_post': retained['project-native-commands-post-build']=b'{}'
        with pytest.raises(ValueError):
            d.reconstruct_current_database(changed,targets,raw,retained)


def test_exact_receipt_artifact_lookup_separates_pre_and_post_build(tmp_path):
    import zipfile
    from scripts import native_timeout_diagnostic as d
    keys = ['project-native-commands','project-native-commands-post-build']
    rows = []
    path = tmp_path/'owned.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        for key in keys:
            raw = key.encode()
            ref = {'path':'artifacts/'+key+'-'+d.sha(raw)+'.json','bytes':len(raw),'sha256':d.sha(raw)}
            rows.append({'id':key,'output_artifact':ref})
            archive.writestr('cpp-baseline-qualification/'+ref['path'],raw)
        # An unrelated same-prefix member must not win selection.
        archive.writestr('cpp-baseline-qualification/artifacts/project-native-commands-unbound.json',b'{}')
    receipt = {'probe':{'operations':rows,'native_command_capture':rows[0]['output_artifact'],
                       'native_command_plan':{'artifact':rows[0]['output_artifact']}}}
    with zipfile.ZipFile(path) as archive:
        for key in keys:
            assert d.retained_operation_artifact(archive,receipt,key) == key.encode()
        rows[0]['output_artifact'] = rows[1]['output_artifact']
        with pytest.raises(ValueError,match='diagnostic_artifact_operation_binding'):
            d.retained_operation_artifact(archive,receipt,keys[0])
        rows.append(rows[1])
        with pytest.raises(ValueError,match='diagnostic_artifact_operation_binding'):
            d.retained_operation_artifact(archive,receipt,keys[1])


def test_475_original_contexts_reconstruct_577_for_compiler_and_primary(tmp_path, monkeypatch):
    import base64
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_cpp_native_commands as native
    from nico import assessment_cpp_fileapi_membership as fileapi
    from nico import assessment_cpp_project_snapshot as snapshot
    from nico.assessment_cpp_full_project import compilation_contexts
    from nico.assessment_cpp_project_compiler import project_compiler_request
    from nico.assessment_cpp_project_static import project_static_request
    from scripts.qualify_cpp_project_configuration import qualification_probe_receipt
    from tests.test_cpp_project_compiler import inputs, result_for
    _, targets, _, _ = inputs(tmp_path)
    rows = [{'directory':'/work/build','file':'/work/source/main.cpp',
             'arguments':['/usr/local/bin/g++','-DVALUE='+str(i),'-I/work/source',
                          '-std=c++20','-c','/work/source/main.cpp','-o',str(i)+'.o']}
            for i in range(577)]
    original=d.canonical_bytes(rows[:475]); analysis=d.canonical_bytes(rows)
    contexts=compilation_contexts(analysis,targets,'/work/build')
    captured=snapshot.capture_project_snapshot(tmp_path/'build',tmp_path/'private'/'synthetic-577',
        snapshot.project_snapshot_request(contexts))
    plan={'contexts':rows,'context_count':577,'analysis_database':base64.b64encode(analysis).decode(),
          'analysis_database_sha256':d.sha(analysis)}
    # Synthetic population expansion only; the separate owned native-capture
    # regression exercises the actual reconstruction and freeze validators.
    def configured(native_raw,membership,raw,observed_targets,**kwargs):
        assert raw==original and observed_targets==targets
        return plan
    monkeypatch.setattr(native,'configured_native_commands',configured)
    monkeypatch.setattr(native,'validate_native_plan_freeze',lambda *a,**k:{'owned_freeze':True})
    membership={'contexts':rows,'missing_database_contexts':rows[475:],
                'source_represented_contexts':rows[:475],'configured_context_count':577}
    monkeypatch.setattr(fileapi,'configured_target_membership',lambda *a,**k:membership)
    probe=qualification_probe_receipt({'native_command_plan':plan,'native_command_freeze':{'owned_freeze':True},
        'enabled_target_membership':membership,
        'analysis_invocations':577,'analysis_compilation_database_sha256':d.sha(analysis),
        'compilation_database_sha256':d.sha(original),'configuration_cache':base64.b64encode(b'owned').decode(),
        'configuration_cache_sha256':d.sha(b'owned'),'fileapi_client':'owned'})
    artifacts={'project-enabled-targets':b'owned','project-enabled-targets-post-build':b'owned',
               'project-native-commands':b'owned','project-native-commands-post-build':b'owned'}
    with pytest.raises(ValueError,match='worker_generated_project_snapshot_invalid'):
        project_compiler_request(original,targets,captured,extended_budget=True)
    restored=d.reconstruct_current_database(probe,targets,original,artifacts)
    compiler=project_compiler_request(restored,targets,captured,extended_budget=True)
    evidence=result_for(compiler)
    evidence['schema']='nico.cpp-project-compiler-evidence.v2'
    primary=project_static_request(restored,targets,captured,d.canonical_bytes(evidence),
                                   extended_compiler_budget=True)
    assert len(json.loads(original))==475
    assert len(compiler['contexts'])==len(primary['contexts'])==577
    assert compiler['database_sha256']==primary['database_sha256']==d.sha(analysis)
    assert compiler['context_membership_sha256']==primary['context_membership_sha256']==contexts['context_membership_sha256']


def test_current_loader_reads_projected_receipt_owners_and_analysis_database(tmp_path, monkeypatch):
    import base64
    import zipfile
    from scripts import native_timeout_diagnostic as d
    from scripts.qualify_cpp_project_configuration import qualification_probe_receipt
    from tests.test_cpp_native_command_transport import run_case
    from nico import assessment_cpp_static_environment as environment
    from nico import assessment_cpp_project_static as primary
    probe,targets,docker,out,_=run_case(tmp_path)
    expected=base64.b64decode(probe['analysis_compilation_database'])
    probe=qualification_probe_receipt(probe)
    members={}
    for row in probe['operations']:
        if row.get('output_artifact'):
            ref=row['output_artifact'];members['cpp-baseline-qualification/'+ref['path']]=(out/ref['path']).read_bytes()
    def artifact(key):
        raw=b'{}';ref={'path':'artifacts/'+key+'-'+d.sha(raw)+'.json','bytes':len(raw),'sha256':d.sha(raw)}
        members['cpp-baseline-qualification/'+ref['path']]=raw
        return ref
    # These artifacts are not probe.operations entries in production receipts.
    probe['project_static_stage']={'operations':[
        {'id':key,'output_artifact':artifact(key)} for key in ('project-static-environment','project-static-evidence')]}
    manifest={'repository':'owned','commit_sha':'a'*40,'tree_sha':'b'*40}
    manifest_raw=d.canonical_bytes(manifest)
    receipt={'probe':probe,'runtime':{'artifact':artifact('project-runtime-evidence')},
             'source':dict(manifest,targets=targets,inventory_complete=True),
             'benchmark_sha256':d.sha(manifest_raw)}
    members['cpp-baseline-qualification/receipt.json']=d.canonical_bytes(receipt)
    while len(members)<107:members['owned-padding-'+str(len(members))]=b''
    members['owned-size-padding']=b''
    path=tmp_path/'owned-current.zip'
    def write():
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED) as archive:
            for name,raw in members.items():archive.writestr(name,raw)
    write()
    members['owned-size-padding']=b'\0'*(22698583-path.stat().st_size)
    write()
    assert path.stat().st_size==22698583
    monkeypatch.setattr(d,'CURRENT_ARCHIVE_SHA',d.sha(path.read_bytes()))
    # Separate export tests cover all tool bytes; this owned ZIP targets loader
    # receipt ownership/reconstruction without claiming native tool equivalence.
    monkeypatch.setattr(d,'verify_current_export',lambda *a:None)
    monkeypatch.setattr(environment,'environment_request',lambda *a,**k:{})
    monkeypatch.setattr(environment,'validate_environment',lambda *a:{})
    seen=[]
    def static_request(database,*args,**kwargs):
        seen.append(database);assert database==expected
        return {'owned':True}
    monkeypatch.setattr(primary,'project_static_request',static_request)
    monkeypatch.setattr(primary,'validate_project_static',lambda *a:{})
    retained=d.load_retained(path,d.CURRENT_ARCHIVE_SHA,manifest_raw,current_primary=True)
    assert seen==[expected]
    assert retained['compiler_request']['database_sha256']==d.sha(expected)
    assert len(retained['compiler_request']['contexts'])==2
    assert retained['receipt']['probe']['compilation_database_sha256']==d.sha(docker.database)


def _budget_policy_fixture():
    from scripts import native_timeout_diagnostic as d
    from tests.test_native_stage_counters import runtime_binding
    from scripts.native_stage_counters.binding import binding_digest
    retained = _current_selection_fixture()
    binding = runtime_binding()
    digest = binding_digest(binding)
    policy = d.create_budget_policy(retained,binding,binding['image'],digest,binding['original_image'])
    return retained,binding,digest,policy


def test_budget_policy_binds_one_context_without_mutating_original_request():
    from copy import deepcopy
    from scripts import native_timeout_diagnostic as d
    retained,binding,digest,policy=_budget_policy_fixture(); before=deepcopy(retained)
    assert d.validate_budget_policy(policy,d.sha(d.canonical_bytes(policy)),retained,
        binding,binding['image'],digest,binding['original_image']) == policy
    assert retained == before and retained['primary_request']['limits']['case_seconds']==90
    assert policy['selected_index']==2 and policy['limits']=={'case_seconds':180,'wall_seconds':540,'parallel':1}
    assert policy['program_sha256']==d.sha(d.budget_program([d.select_primary_cases(retained)[0]['invocation']]).encode())
    assert policy['analyzer_source_revision']=='ac4d82c590588700a462c4b7b3f5ea5acd8cfcfb'
    assert policy['production_qualified'] is False


@pytest.mark.parametrize('fault',['index','path','case','aggregate','parallel','resource','image','original',
    'request','program','controller','binding','population','qualified','hash'])
def test_budget_policy_rejects_rehashed_deviations(fault):
    from scripts import native_timeout_diagnostic as d
    retained,binding,digest,policy=_budget_policy_fixture()
    if fault=='index':policy['selected_index']=4
    elif fault=='path':policy['selected_path']='src/init/bitcoin-node.cpp'
    elif fault=='case':policy['limits']['case_seconds']=181
    elif fault=='aggregate':policy['limits']['wall_seconds']=541
    elif fault=='parallel':policy['limits']['parallel']=2
    elif fault=='resource':policy['resource_args'][0]='--cpus=8'
    elif fault=='image':policy['image']='sha256:'+'f'*64
    elif fault=='original':policy['original_image']=policy['image']
    elif fault=='request':policy['parent_request_sha256']='f'*64
    elif fault=='program':policy['program_sha256']='f'*64
    elif fault=='controller':policy['controller_source_sha256']='f'*64
    elif fault=='binding':policy['runtime_binding_sha256']='f'*64
    elif fault=='population':policy['retained_population']=576
    elif fault=='qualified':policy['production_qualified']=True
    expected=d.sha(d.canonical_bytes(policy)) if fault!='hash' else 'f'*64
    with pytest.raises(ValueError,match='diagnostic_budget_policy'):
        d.validate_budget_policy(policy,expected,retained,binding,binding['image'],digest,binding['original_image'])


def _budget_adapter():
    import types
    from scripts import native_timeout_diagnostic as d
    retained,_,_,policy=_budget_policy_fixture()
    program=d.budget_program([d.select_primary_cases(retained)[0]['invocation']])
    prefix=program.split('raw = sys.stdin.buffer.read(REQUEST_LIMIT+1)',1)[0]
    ns={'__name__':'owned_budget'};exec(prefix,ns)
    calls=[]
    clock=types.SimpleNamespace(monotonic=lambda:100.)
    ns['time']=clock;ns['sys']=types.SimpleNamespace(argv=['-c',d.sha(d.canonical_bytes(policy))])
    def fake(argv,stem,deadline,env):
        calls.append((argv,stem,deadline,env));return {'owned':True}
    ns['original_run']=fake
    return ns,calls,retained,program


def test_budget_wrapper_extends_selected_command_and_preserves_aggregate_clipping():
    ns,calls,retained,_=_budget_adapter()
    argv=retained['primary_request']['contexts'][2]['analyzer_invocation']
    ns['_run'](argv,'u2',640,{'EXACT':'owned'})
    assert calls[-1][2]==280 and calls[-1][0]==argv+['--showtime=file','--report-progress=1']
    ns['_run'](argv,'u2',150,{'EXACT':'owned'})
    assert calls[-1][2]==150
    ns['_run'](['/usr/local/bin/cppcheck','--version'],'version',105,{'EXACT':'owned'})
    assert calls[-1][2]==105 and calls[-1][0]==['/usr/local/bin/cppcheck','--version']
    with pytest.raises(ValueError):
        ns['_run'](retained['primary_request']['contexts'][4]['analyzer_invocation'],'u4',640,{})


def test_budget_scheduler_dispatches_exactly_context2_and_flushes_its_record(capsys):
    ns,_,retained,program=_budget_adapter();seen=[]
    with ns['ThreadPoolExecutor'](2) as pool:
        records=list(pool.map(lambda c:seen.append(c['index']) or {'context_id':c['context_id']},retained['primary_request']['contexts']))
    assert seen==[2] and len(records)==1
    assert json.loads(capsys.readouterr().out)['execution_policy_sha256']
    assert 'min(deadline, dispatch_start + 180)' in program
    assert "limits = _request_limits(request)" in program
    assert "start + 5" in program
    assert ns['PHYSICAL_LIMITS']=={'wall_seconds':540,'case_seconds':90,'parallel':2}
    with pytest.raises(ValueError):ns['ThreadPoolExecutor'](4)


def test_budget_fails_closed_if_pinned_collector_changes(monkeypatch):
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_cpp_project_static as static
    monkeypatch.setattr(static,'PROGRAM',static.PROGRAM+'\n# drift')
    with pytest.raises(ValueError,match='collector_identity'):
        d.budget_program([['--project=/work/analysis/static-baseline/u2.json']])


def test_workflow_budget_is_explicit_once_after_contracts_controls_and_policy():
    import yaml
    from pathlib import Path
    w=yaml.safe_load(Path('.github/workflows/native-timeout-diagnostic.yml').read_text())
    events=w.get('on',w.get(True));assert events['pull_request']['types']==['synchronize']
    job=w['jobs']['isolated-diagnostic'];assert 'github.run_attempt == 1' in job['if']
    steps=job['steps'];run=[s for s in steps if '--mode current-primary-budget-v1' in s.get('run','')]
    assert len(run)==1
    assert '--execution-policy ' in run[0]['run'] and '--execution-policy-sha256 ' in run[0]['run']
    contracts=next(n for n,s in enumerate(steps) if s.get('name')=='Verify diagnostic contracts')
    control=next(n for n,s in enumerate(steps) if s.get('name')=='Prove analyzer opt-in and absence on owned source before acquisition')
    policy=next(n for n,s in enumerate(steps) if s.get('name')=='Bind the explicit context-2 budget policy to fresh image identities')
    assert contracts<control<policy<steps.index(run[0])
    assert not any('--mode current-primary\n' in s.get('run','') for s in steps)


def _budget_native_fixture(tmp_path):
    """Relabel owned receipt controls; these are never native qualification proof."""
    import base64
    from copy import deepcopy
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_cpp_project_static as static
    from tests.test_cpp_completed_static_collection import fixture
    request,_,raw,_=fixture(tmp_path,failing=False,physical=True)
    request=json.loads(json.dumps(request).replace('unit.cpp','src/init/basic.cpp'))
    output=json.loads(raw);row=deepcopy(output['records'][0])
    request['contexts'][2]=deepcopy(request['contexts'][0])
    request['contexts'][2]['analyzer_invocation']=[a.replace('/u0.json','/u2.json') for a in request['contexts'][2]['analyzer_invocation']]
    row['invocation']=[a.replace('unit.cpp','src/init/basic.cpp').replace('/u0.json','/u2.json') for a in row['invocation']]
    for field,hashfield in [('xml','xml_sha256'),('header_trace','header_trace_sha256')]:
        content=static._decode_xml(row[field],row[hashfield],row.get(field+'_encoding','identity'))
        content=content.replace(b'unit.cpp',b'src/init/basic.cpp')
        encoded,digest,encoding=static._encode_xml(content,compact=field=='header_trace')
        row[field]=encoded;row[hashfield]=digest
        if field=='header_trace':row['header_trace_encoding']=encoding
    execution=row['execution'];progress=base64.b64decode(execution['output']).replace(b'unit.cpp',b'src/init/basic.cpp')
    execution.update(output=base64.b64encode(progress).decode(),output_sha256=d.sha(progress),duration_ms=150000)
    request['contexts'] += [deepcopy(request['contexts'][0]) for _ in range(573)]
    for c in request['contexts']:
        c['analyzer_database_sha256']=d.sha(c['analyzer_database'].encode())
    row['database_sha256']=request['contexts'][2]['analyzer_database_sha256']
    retained=_current_selection_fixture();retained['primary_request']=request
    for index,path in d.CURRENT_CASES.items():
        request['contexts'][index]['index']=index;request['contexts'][index]['path']=path
        c=request['contexts'][index]
        retained['primary_raw']['records'][index].update(context_id=c['context_id'],invocation=c['analyzer_invocation'])
    _,binding,digest,_=_budget_policy_fixture()
    policy=d.create_budget_policy(retained,binding,binding['image'],digest,binding['original_image'])
    policy_sha=d.sha(d.canonical_bytes(policy))
    row['executed_invocation']=row['invocation']+d.DIAGNOSTIC_FLAGS
    output.update(schema=d.BUDGET_EVIDENCE_SCHEMA,request_sha256=d.sha(d.canonical_bytes(request)),records=[row],
        duration_ms=150005,execution_policy_sha256=policy_sha,production_qualified=False,
        assessment_completed=False,full_project_qualified=False,dispatched_indices=[2],diagnostic_parallel=1,
        retained_population=577,diagnostic_flags=d.DIAGNOSTIC_FLAGS)
    return request,policy,policy_sha,output


def test_budget_accepts_completed_150second_owned_case_and_keeps_qualification_false(tmp_path):
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_cpp_project_static as static
    req,policy,digest,native=_budget_native_fixture(tmp_path)
    raw=d.canonical_bytes(native)
    checked=d.validate_budget_evidence(raw,req,policy,digest)
    assert checked['case_complete'] and checked['complete'] is False
    assert checked['native_evidence_sha256']==d.sha(raw)
    assert checked['header_context_evidence_complete']
    assert checked['assessment_completed'] is False and checked['production_qualified'] is False
    with pytest.raises(ValueError):static.validate_project_static(raw,req)
    native['records'][0]['execution']['duration_ms']=1;native['duration_ms']=10
    with pytest.raises(ValueError):static.validate_project_static(d.canonical_bytes(native),req)


@pytest.mark.parametrize('fault',['header','xml','duration','record','command','policy','qualification','schema'])
def test_budget_correctness_gates_remain_mandatory(tmp_path,fault):
    from scripts import native_timeout_diagnostic as d
    req,policy,digest,native=_budget_native_fixture(tmp_path)
    row=native['records'][0]
    if fault=='header':row['header_trace']='';row['header_trace_sha256']=None
    elif fault=='xml':row['xml']='';row['xml_sha256']=None
    elif fault=='duration':row['execution']['duration_ms']=183001
    elif fault=='record':native['records'].append(dict(row))
    elif fault=='command':row['executed_invocation'].append('--suppress=all')
    elif fault=='policy':native['execution_policy_sha256']='f'*64
    elif fault=='qualification':native['production_qualified']=True
    elif fault=='schema':native['schema']='nico.cpp-project-static-evidence.v4'
    with pytest.raises(ValueError):d.validate_budget_evidence(d.canonical_bytes(native),req,policy,digest)


def test_budget_retains_timeout_with_actual_xml_and_unknown_completion(tmp_path):
    from scripts import native_timeout_diagnostic as d
    req,policy,digest,native=_budget_native_fixture(tmp_path)
    native['records'][0]['execution'].update(exit_code=124,timed_out=True,duration_ms=180001)
    native['duration_ms']=180010
    raw=d.canonical_bytes(native)
    checked=d.validate_budget_evidence(raw,req,policy,digest)
    assert not checked['case_complete'] and not checked['complete']
    assert checked['native_evidence_sha256']==d.sha(raw)
    assert checked['limitations'] and checked['attempted_contexts']==[req['contexts'][2]['context_id']]


@pytest.mark.parametrize('fault',['profile','generator'])
def test_budget_rejects_actual_resource_drift_before_container_creation(tmp_path,monkeypatch,fault):
    from scripts import native_timeout_diagnostic as d
    from nico import assessment_worker_capacity_v1 as capacity
    box,transport=_sandbox_fixture(tmp_path)
    box.expected_resource_args=list(d.BUDGET_RESOURCE_ARGS)
    if fault=='profile':monkeypatch.setitem(capacity.BASELINE_QUALIFICATION_RESOURCES,'cpus','8')
    else:monkeypatch.setattr(capacity,'docker_resource_args',lambda *a,**k:['--cpus=8'])
    with pytest.raises(ValueError,match='diagnostic_budget_resource_mismatch'):
        with box:pytest.fail('must not enter')
    assert not any(argv[1]=='create' for argv,_ in transport.calls)
    assert box.receipt['cleanup_verified'] and not box.receipt['cleanup_required']


def test_budget_rejects_impossible_serial_duration(tmp_path):
    from scripts import native_timeout_diagnostic as d
    req,policy,digest,native=_budget_native_fixture(tmp_path)
    native['duration_ms']=80000
    with pytest.raises(ValueError,match='duration_invalid'):
        d.validate_budget_evidence(d.canonical_bytes(native),req,policy,digest)


def test_cli_explicit_budget_mode_runs_once_and_never_claims_assessment(tmp_path,monkeypatch):
    from scripts import native_timeout_diagnostic as d
    from scripts.native_stage_counters import binding as b
    from scripts import qualify_cpp_project_configuration as qualification
    retained,binding,digest,policy=_budget_policy_fixture()
    retained.update(manifest={},receipt={'source':{'targets':{}}})
    policy_file=tmp_path/'policy.json';policy_file.write_bytes(d.canonical_bytes(policy))
    manifest=tmp_path/'manifest.json';manifest.write_bytes(b'{}')
    monkeypatch.setattr(b,'load_binding',lambda *a:binding)
    monkeypatch.setattr(d,'load_retained',lambda *a,**k:retained)
    monkeypatch.setattr(qualification,'freeze_configuration_checkout',lambda *a:{'targets':{}})
    calls=[]
    def run(*a,**kwargs):
        calls.append(kwargs)
        return {'case_complete':True,'complete':False,'boundary_verified':True,'cleanup_verified':True}
    monkeypatch.setattr(d,'run_primary',run)
    monkeypatch.setattr('sys.argv',['owned','--mode',d.BUDGET_MODE,'--archive','owned.zip',
        '--archive-sha256',d.CURRENT_ARCHIVE_SHA,'--qualification-source',str(tmp_path),
        '--qualification-manifest',str(manifest),'--image',binding['image'],'--original-image',binding['original_image'],
        '--stage-runtime-binding','owned-binding.json','--stage-runtime-binding-sha256',digest,
        '--execution-policy',str(policy_file),'--execution-policy-sha256',d.sha(d.canonical_bytes(policy)),
        '--output',str(tmp_path/'output')])
    d.main()
    assert len(calls)==1 and calls[0]['execution_policy']==policy
    outcome=json.loads((tmp_path/'output/diagnostic.json').read_bytes())
    assert outcome['schema']=='nico.current-primary-budget-controller.v1'
    assert outcome['status']=='ISOLATED_CASES_COMPLETED'
    assert outcome['assessment_completed'] is False and outcome['production_qualified'] is False
    assert outcome['static']['complete'] is False


def test_full_generated_budget_program_uses_180_deadline_and_emits_only_new_schema(tmp_path,capsys,monkeypatch):
    import base64,io,types,hashlib
    from pathlib import Path
    from scripts import native_timeout_diagnostic as d
    from tests.test_native_stage_counters import runtime_binding
    from scripts.native_stage_counters.binding import binding_digest
    retained=_current_selection_fixture();request=retained['primary_request']
    for index,c in enumerate(request['contexts']):
        c.update(index=index,origin='original',path=c.get('path','owned.cpp'),
            analysis_file='/work/source/'+c.get('path','owned.cpp'),invocation=['/usr/local/bin/g++','owned.cpp'],
            analyzer_database='[]',analyzer_database_sha256=d.sha(b'[]'),source_dependencies={},generated_dependencies={})
        c.setdefault('context_id','owned-'+str(index));c.setdefault('analyzer_invocation',['owned'])
    request.update(tool_version='2.17.1',compiler_environment={'physical_header_inputs':True},
        header_trace_schema='owned',header_tool_manifest_sha256='owned',
        targets={path:d.sha(b'owned') for path in d.CURRENT_CASES.values()},generated_files={})
    binding=runtime_binding();digest=binding_digest(binding)
    policy=d.create_budget_policy(retained,binding,binding['image'],digest,binding['original_image'])
    program=d.budget_program([d.select_primary_cases(retained)[0]['invocation']])
    prefix,suffix=program.split('raw = sys.stdin.buffer.read(REQUEST_LIMIT+1)',1)
    ns={'__name__':'owned_budget'};exec(prefix,ns)
    calls=[]
    def run(argv,stem,deadline,environment):
        calls.append((argv,deadline))
        content=b'Cppcheck 2.17.1\n' if '--version' in argv else b'Checking owned ...\n'
        return {'exit_code':0,'timed_out':False,'output_truncated':False,'duration_ms':1,
            'output':base64.b64encode(content).decode(),'output_sha256':hashlib.sha256(content).hexdigest()}
    ns['original_run']=run;ns['time']=types.SimpleNamespace(monotonic=lambda:100.)
    ns['sys']=types.SimpleNamespace(argv=['-c',d.sha(d.canonical_bytes(policy))],
        stdin=types.SimpleNamespace(buffer=io.BytesIO(d.canonical_bytes({'request':request,'policy':policy}))))
    ns['HEADER_SCHEMA']='owned';ns['HEADER_TOOL_MANIFEST_SHA256']='owned'
    ns['os']=types.SimpleNamespace(getuid=lambda:1001,getgid=lambda:1001,open=__import__('os').open,
        close=__import__('os').close,O_CREAT=__import__('os').O_CREAT,O_EXCL=__import__('os').O_EXCL,
        O_WRONLY=__import__('os').O_WRONLY,O_NOFOLLOW=__import__('os').O_NOFOLLOW)
    ns['resource']=types.SimpleNamespace(setrlimit=lambda *a:None,RLIMIT_FSIZE=1)
    ns['verify_environment_inputs']=lambda *a:None;ns['validate_header_tool_receipt']=lambda *a:None
    ns['_verify_input']=lambda *a:None
    ns['_syntax_argv']=lambda c,g:(c['invocation'],c['analysis_file'])
    ns['_static_plan']=lambda c,*a,**k:(c['analyzer_database'],c['analyzer_invocation'])
    class OwnedPath(type(Path())):
        def stat(self, *args, **kwargs):
            actual=super().stat(*args, **kwargs)
            if str(self)==str(tmp_path/'analysis'):
                return types.SimpleNamespace(st_uid=1001,st_mode=0o40700)
            return actual
    ns['Path']=lambda value:OwnedPath(str(value).replace('/work/analysis',str(tmp_path/'analysis')))
    (tmp_path/'analysis').mkdir(mode=0o700)
    def regular(path,limit):
        if str(path).endswith('.json') and not str(path).startswith('/opt/'):
            return Path(path).read_bytes()
        return b'<owned/>'
    ns['_regular_bytes']=regular
    # The collector's local import uses the same owned fake as its globals.
    monkeypatch.setitem(__import__('sys').modules,'resource',ns['resource'])
    exec('raw = sys.stdin.buffer.read(REQUEST_LIMIT+1)'+suffix,ns)
    frames=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(calls)==2 and calls[0][1]==105 and calls[1][1]==280
    assert len(frames)==2 and frames[-1]['schema']==d.BUDGET_EVIDENCE_SCHEMA
    assert frames[-1]['dispatched_indices']==[2] and len(frames[-1]['records'])==1
    assert request['limits']=={'wall_seconds':540,'case_seconds':90,'parallel':2}
    assert frames[-1]['request_sha256']==d.sha(d.canonical_bytes(request))


def test_budget_completed_case_preserves_genuine_source_bound_findings(tmp_path):
    import base64
    from xml.etree import ElementTree as ET
    from scripts import native_timeout_diagnostic as d
    req,policy,digest,native=_budget_native_fixture(tmp_path)
    row=native['records'][0];document=ET.fromstring(base64.b64decode(row['xml']))
    error=ET.SubElement(document.find('errors'),'error',id='nullPointer',severity='error',msg='Owned finding')
    ET.SubElement(error,'location',file=req['contexts'][2]['analysis_file'],line='1',column='1')
    raw=ET.tostring(document);row['xml']=base64.b64encode(raw).decode();row['xml_sha256']=d.sha(raw)
    checked=d.validate_budget_evidence(d.canonical_bytes(native),req,policy,digest)
    assert checked['case_complete'] and checked['findings']
    assert checked['findings'][0]['rule_id']=='nullPointer'
    assert checked['findings'][0]['source_sha256']==req['targets']['src/init/basic.cpp']
    assert checked['production_qualified'] is False
