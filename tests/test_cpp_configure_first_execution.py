from copy import deepcopy
import hashlib
from nico.assessment_worker_receipts import canonical_bytes
from nico.assessment_cpp_configure_first_execution import summarize_probe

def ref(key, raw=b"x"):
    return {"artifact_id":"scanartifact_"+"a"*64,"key":key,"sha256":hashlib.sha256(raw).hexdigest(),
        "gzip_sha256":"b"*64,"retained_bytes":len(raw),"gzip_bytes":1,"storage_backend":"postgres"}

def proof():
    ids=["c1","c2"]
    return {"status":"BASELINE_EXECUTED","error":None,"compiled":True,"tests_executed":True,"tests_passed":True,
        "tests_discovered":["a","b"],"tests_result":{"executed":["a","b"],"passed":["a","b"],"skipped":[]},
        "generated_context_verified":True,"boundary_verified":True,"cleanup_verified":True,"scratch_capacity_verified":True,
        "memory_peak_bytes":123,"duration_ms":10,"aggregate_duration_ms":20,
        "compilation_database_sha256":"c"*64,"configured_invocations":2,
        "baseline_execution_frozen":{"schema":"nico.cpp-baseline-execution-freeze.v1"},
        "project_compiler":{"required_contexts":ids,"checked_contexts":ids,"complete":True},
        "project_static":{"required_contexts":ids,"analyzed_contexts":ids,"complete":True,
            "findings":[{"id":"f1"}],"limitations":[],"modeled_inputs":[]},
        "project_static_stage":{"complete":True,"memory_peak_bytes":456}}

def test_summary_is_hash_bound_and_keeps_canonical_projection_pending():
    targets={"CMakeLists.txt":"d"*64,"src/a.cpp":"e"*64}
    artifacts={k:ref(k) for k in ("project-compilation-database","project-generated-context",
        "project-compiler-evidence","project-static-environment","project-static-evidence")}
    result=summarize_probe(proof(),targets,artifacts)
    assert result["complete_execution"] is True
    assert result["canonical_findings_projected"] is False
    assert result["source_population_sha256"]==hashlib.sha256(canonical_bytes(targets)).hexdigest()
    assert result["project_static_findings_count"]==1
    assert result["project_compiler_required_count"]==result["project_compiler_checked_count"]==2

def test_summary_never_claims_complete_without_every_required_artifact():
    targets={"CMakeLists.txt":"d"*64}
    artifacts={k:ref(k) for k in ("project-generated-context","project-compiler-evidence","project-static-evidence")}
    result=summarize_probe(proof(),targets,artifacts)
    assert result["complete_execution"] is False

def test_summary_rejects_artifact_identity_substitution():
    targets={"CMakeLists.txt":"d"*64}
    artifacts={k:ref(k) for k in ("project-generated-context","project-compiler-evidence",
        "project-static-environment","project-static-evidence")}
    artifacts["project-static-evidence"]={**artifacts["project-static-evidence"],"key":"project-static-environment"}
    import pytest
    with pytest.raises(ValueError,match="artifact_reference"):
        summarize_probe(proof(),targets,artifacts)


def test_configure_first_v2_derives_options_before_probe(tmp_path, monkeypatch):
    from nico.assessment_cpp_configure_first_execution import run_configure_first
    from tests.test_cpp_configure_first_contract import contract
    import base64
    plan=contract(); plan['configuration'].pop('project_options')
    plan['configuration'].update(schema='nico.cpp-configure-first-contract.v2',
        project_option_policy='conservative-cmake-v1')
    root=tmp_path/'source'; root.mkdir()
    cmake=b'option(BUILD_TESTS "tests" OFF)\noption(BUILD_GUI "gui" ON)\n'
    (root/'CMakeLists.txt').write_bytes(cmake)
    targets={'CMakeLists.txt':hashlib.sha256(cmake).hexdigest()}
    acquisition={'schema':'nico.github_https_tree_materialization.v2','tree_sha':plan['configuration']['expected_tree_sha'],
        'inputs':targets,'population_sha256':hashlib.sha256(canonical_bytes(targets)).hexdigest()}
    observed={}
    def fake_probe(source, actual_targets, image, **kwargs):
        observed['options']=kwargs['project_options']
        value=proof(); value['compilation_database']=base64.b64encode(b'[]').decode()
        value['compilation_database_sha256']=hashlib.sha256(b'[]').hexdigest()
        return value
    monkeypatch.setattr('nico.assessment_cpp_configuration_probe.probe_project_configuration',fake_probe)
    result=run_configure_first(plan,root,acquisition,checkpoint=lambda:None,timeout_seconds=60,
        retain_artifact=lambda key,raw:ref(key,raw))
    assert observed['options']=={'BUILD_GUI':'OFF','BUILD_TESTS':'ON'}
    assert result['native']['project_option_policy']=='conservative-cmake-v1'
    assert result['native']['project_options']==observed['options']


def test_configure_first_v3_derives_release_options_before_probe(tmp_path, monkeypatch):
    from nico.assessment_cpp_configure_first_execution import run_configure_first
    from tests.test_cpp_configure_first_contract import contract
    import base64
    plan=contract(); plan['configuration'].pop('project_options')
    plan['configuration'].update(schema='nico.cpp-configure-first-contract.v3',
        project_option_policy='conservative-cmake-v1', runtime_scope={
            'schema':'nico.cpp-runtime-scope.v1','total_seconds':6000,'functional_policy':'source-declared-functional-v1',
            'functional_seconds':900,'sanitizers':['address','undefined'],'sanitizer_build_seconds':1200,
            'sanitizer_test_seconds':600,'sanitizer_test_case_seconds':120,
            'fuzz_policy':'source-declared-libfuzzer-v1','fuzz_replay_runs':1,
            'fuzz_campaign_runs':256,'fuzz_campaign_seconds':300,'parallel':4})
    plan['limits']={'max_attempts':1,'wall_seconds':9000,'lease_seconds':300}
    root=tmp_path/'source'; root.mkdir()
    cmake=b'option(BUILD_TESTS "tests" OFF)\noption(BUILD_GUI "gui" ON)\n'
    (root/'CMakeLists.txt').write_bytes(cmake)
    targets={'CMakeLists.txt':hashlib.sha256(cmake).hexdigest()}
    acquisition={'schema':'nico.github_https_tree_materialization.v2','tree_sha':plan['configuration']['expected_tree_sha'],
        'inputs':targets,'population_sha256':hashlib.sha256(canonical_bytes(targets)).hexdigest()}
    observed={}
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.capture_runtime_interfaces',
        lambda source,actual_targets:{'interfaces':True})
    runtime_plan={'schema':'nico.cpp-runtime-plan.v1','total_seconds':6000,'unit_test_data':None}
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.derive_runtime_plan_from_interfaces',
        lambda interfaces,actual_targets,options,scope:runtime_plan)
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.acquire_unit_test_data',lambda plan,checkpoint:None)
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.retained_runtime_bytes',
        lambda interfaces,actual_plan,evidence:b'{"runtime":true}')
    def fake_probe(source, actual_targets, image, **kwargs):
        observed['options']=kwargs['project_options']; observed['runtime_plan']=kwargs['runtime_plan']
        value=proof(); value['compilation_database']=base64.b64encode(b'[]').decode()
        value['compilation_database_sha256']=hashlib.sha256(b'[]').hexdigest()
        value['runtime_evidence']={'schema':'nico.cpp-runtime-evidence.v1','duration_ms':7}
        value['runtime_summary']={'complete':True}
        return value
    monkeypatch.setattr('nico.assessment_cpp_configuration_probe.probe_project_configuration',fake_probe)
    result=run_configure_first(plan,root,acquisition,checkpoint=lambda:None,timeout_seconds=8980,
        retain_artifact=lambda key,raw:ref(key,raw))
    assert observed['options']=={'BUILD_GUI':'OFF','BUILD_TESTS':'ON'}
    assert observed['runtime_plan']==runtime_plan
    assert result['native']['schema']=='nico.cpp-configure-first-native.v2'
    assert result['native']['runtime_complete'] is True
    assert result['native']['project_option_policy']=='conservative-cmake-v1'
    assert result['native']['project_options']==observed['options']
    assert 'project-runtime-evidence' in result['native']['artifacts']


def _run_real_configure_first_with_build_polls(tmp_path, monkeypatch, *, cancel=False,
                                               expire=False):
    """Only Docker is substituted; exercise the real configure-first/probe seam."""
    from types import SimpleNamespace
    import pytest
    from nico import assessment_cpp_configure_first_execution as execution
    from nico import assessment_cpp_configuration_probe as probe
    from tests.test_cpp_baseline_execution import Native, source
    from tests.test_cpp_configure_first_contract import contract

    root, targets = source(tmp_path)
    plan = contract()
    plan['image_digest'] = 'sha256:'+'a'*64
    plan['configuration']['project_options'] = {'BUILD_TESTS': 'ON'}
    acquisition = {'schema': 'nico.github_https_tree_materialization.v2',
        'tree_sha': plan['configuration']['expected_tree_sha'], 'inputs': targets,
        'population_sha256': hashlib.sha256(canonical_bytes(targets)).hexdigest()}
    docker = Native(targets)
    state = {'calls': [], 'owner_polls': 0, 'in_build': False, 'clock': 0,
             'build_poll_count': 0, 'cancelled': False, 'build_delta': None}
    monkeypatch.setattr(execution, 'time', SimpleNamespace(monotonic=lambda: state['clock']), raising=False)
    def owner_checkpoint():
        state['owner_polls'] += 1
        if state['in_build']:
            state['build_poll_count'] += 1
            if cancel and state['build_poll_count'] >= 2:
                state['cancelled'] = True
        if state['cancelled']:
            raise ValueError('owner_cancelled')
    def command(argv, **kwargs):
        state['calls'].append(argv)
        if '--build' in argv:
            before = state['owner_polls']; state['in_build'] = True
            try:
                for _ in range(3):
                    if expire: state['clock'] = 61
                    kwargs['checkpoint']()
            finally:
                state['in_build'] = False
                state['build_delta'] = state['owner_polls'] - before
        return docker(argv, **kwargs)
    monkeypatch.setattr(probe, '_command', command)
    run = lambda: execution.run_configure_first(plan, root, acquisition,
        checkpoint=owner_checkpoint, timeout_seconds=60,
        retain_artifact=lambda key, raw: ref(key, raw))
    if cancel or expire:
        with pytest.raises(ValueError, match='owner_cancelled' if cancel else 'worker_configure_first_execution_deadline'):
            run()
    else:
        run()
    return state


def test_real_configure_first_renews_owner_lease_inside_long_build(tmp_path, monkeypatch):
    state = _run_real_configure_first_with_build_polls(tmp_path, monkeypatch)
    assert state['build_delta'] == 3, 'the running native command lost the durable owner checkpoint'


def test_real_configure_first_cancellation_stops_before_tests_and_still_cleans_up(tmp_path, monkeypatch):
    state = _run_real_configure_first_with_build_polls(tmp_path, monkeypatch, cancel=True)
    assert state['cancelled'] and state['build_poll_count'] == 2
    assert not any('ctest' in argv for argv in state['calls'])
    assert any(argv[1:3] == ['rm', '--force'] for argv in state['calls'])


def test_real_configure_first_enforces_supplied_remaining_time_during_build(tmp_path, monkeypatch):
    state = _run_real_configure_first_with_build_polls(tmp_path, monkeypatch, expire=True)
    assert not any('ctest' in argv for argv in state['calls'])
    assert any(argv[1:3] == ['rm', '--force'] for argv in state['calls'])
