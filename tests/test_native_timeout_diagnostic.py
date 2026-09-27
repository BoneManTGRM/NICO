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
    assert 'group: cpp-full-project-integration-${{ github.ref }}' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert 'actions: read' in workflow and 'contents: read' in workflow
    import re
    assert not re.search(r'^\s+[a-z-]+:\s*write\s*$',workflow,re.M) and 'secrets.' not in workflow
    assert 'timeout-minutes: 55' in workflow
    assert '36177497388' in workflow and 'case "$conclusion"' in workflow
    assert 'success)' in workflow and 'failure)' in workflow
    assert '10883294546' in workflow
    assert 'd4933e0120105b8427ebe813cfec2f8487e5d801b980e7cbfbc942adc0ffd41e' in workflow
    assert 'owned_control' in workflow
