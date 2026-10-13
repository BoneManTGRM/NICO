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
    assert '--mode current-primary' in workflow
    assert 'owned_primary_control' in workflow
    assert workflow.index('Exercise the owned static-only boundary first') < workflow.index('Measure only the three current primary contexts')
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
        isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='original_run' for t in n.targets))
        or isinstance(n,ast.ClassDef) and n.name=='ThreadPoolExecutor']
    # Only the final diagnostic _run adapter, not the production collector runner.
    nodes.insert(1,[n for n in program.body if isinstance(n,ast.FunctionDef) and n.name=='_run'][-1])
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
