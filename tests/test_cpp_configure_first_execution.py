from copy import deepcopy
from dataclasses import asdict
import hashlib
import pytest

from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import canonical_bytes, publish_receipt, validate_receipt
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


def incomplete_receipt(*, runtime=False):
    from tests.test_cpp_configure_first_contract import contract

    plan=contract()
    if runtime:
        plan['configuration'].pop('project_options')
        plan['configuration'].update(schema='nico.cpp-configure-first-contract.v3',
            project_option_policy='conservative-cmake-v1',runtime_scope={
                'schema':'nico.cpp-runtime-scope.v1','total_seconds':6000,
                'functional_policy':'source-declared-functional-v1','functional_seconds':900,
                'sanitizers':['address','undefined'],'sanitizer_build_seconds':1200,
                'sanitizer_test_seconds':600,'sanitizer_test_case_seconds':120,
                'fuzz_policy':'source-declared-libfuzzer-v1','fuzz_replay_runs':1,
                'fuzz_campaign_runs':256,'fuzz_campaign_seconds':300,'parallel':4})
        plan['limits']={'max_attempts':1,'wall_seconds':9000,'lease_seconds':300}
    identity=JobIdentity('customer','project','run','scan','owner/repo','a'*40,_digest(plan),'c'*40)
    targets={'CMakeLists.txt':'d'*64,'src/a.cpp':'e'*64}
    failed=proof()
    failed.update(status='UNPROVEN',error='worker_configuration_probe_compiler_incomplete')
    failed['project_compiler'].update(checked_contexts=['c1'],complete=False)
    failed['project_static']={}
    failed['project_static_stage']={}
    artifacts={key:ref(key) for key in (
        'project-compilation-database','project-generated-context','project-compiler-evidence')}
    native=summarize_probe(failed,targets,artifacts)
    native.update(project_option_policy='conservative-cmake-v1' if runtime else 'explicit-v1',
        project_options={},project_options_sha256=_digest({}))
    if runtime:
        native.update(schema='nico.cpp-configure-first-native.v2',runtime_complete=False,
            runtime_plan_sha256='f'*64,runtime_summary_sha256=_digest({}),runtime_duration_ms=0)
    receipt={'schema':'nico.worker-native-receipt.v7','identity':asdict(identity),'lease_id':'e'*32,
        'worker_id':'github:1:2:3','image_digest':plan['image_digest'],'tool_version':plan['tool_version'],
        'configuration_sha256':_digest(plan['configuration']),'target_hashes':targets,'native':native,
        'native_sha256':_digest(native)}
    return identity,plan,receipt


@pytest.mark.parametrize('runtime',[False,True])
def test_incomplete_configure_first_receipt_retains_available_artifacts_and_exact_probe_failure(runtime):
    identity,plan,receipt=incomplete_receipt(runtime=runtime)
    _,record,_=validate_receipt(identity,plan,'e'*32,'github:1:2:3',receipt)
    assert record['status']=='failed' and record['completed'] is False
    assert record['canonical_findings_projected'] is False
    assert record['worker_provenance']['native_artifacts']==receipt['native']['artifacts']
    assert record['cpp_build_evidence']['configure_error']=='worker_configuration_probe_compiler_incomplete'
    assert record['cpp_build_evidence']['configure_status']=='UNPROVEN'
    assert record['reason']=='Configure-first execution is incomplete; retained native evidence requires repair.'


def test_capacity_limit_is_reported_without_scanner_completion_credit():
    identity,plan,receipt=incomplete_receipt(runtime=True)
    receipt['native']['error']='worker_configuration_probe_snapshot_capacity_exceeded'
    receipt['native_sha256']=_digest(receipt['native'])
    _,record,_=validate_receipt(identity,plan,'e'*32,'github:1:2:3',receipt)
    assert record['status']=='failed'
    assert record['completed'] is False and record['verified_for_this_report'] is False
    assert record['canonical_findings_projected'] is False and record['findings']==[]
    assert 'bounded capacity' in record['reason'] and 'no completion credit' in record['reason']
    assert record['cpp_build_evidence']['configure_error']==receipt['native']['error']


def test_incomplete_artifact_population_cannot_claim_complete_execution():
    identity,plan,receipt=incomplete_receipt()
    receipt['native']['complete_execution']=True
    receipt['native_sha256']=_digest(receipt['native'])
    with pytest.raises(ValueError,match='worker_configure_first_native_invalid'):
        validate_receipt(identity,plan,'e'*32,'github:1:2:3',receipt)


def test_incomplete_receipt_still_requires_retained_compilation_database():
    identity,plan,receipt=incomplete_receipt()
    receipt['native']['artifacts'].pop('project-compilation-database')
    receipt['native_sha256']=_digest(receipt['native'])
    with pytest.raises(ValueError,match='worker_configure_first_native_invalid'):
        validate_receipt(identity,plan,'e'*32,'github:1:2:3',receipt)


def test_incomplete_probe_error_is_bounded_before_retention():
    identity,plan,receipt=incomplete_receipt()
    receipt['native']['error']='unbounded diagnostic text'
    receipt['native_sha256']=_digest(receipt['native'])
    with pytest.raises(ValueError,match='worker_configure_first_native_invalid'):
        validate_receipt(identity,plan,'e'*32,'github:1:2:3',receipt)


def test_partial_configure_first_publication_skips_full_reconstruction():
    identity,plan,receipt=incomplete_receipt()

    class Adapter:
        _connect=lambda self: (_ for _ in ()).throw(AssertionError('partial receipt must not read missing artifacts'))

    class Jobs:
        adapter=Adapter()
        def get(self, actual):
            assert actual==identity
            return {'contract':plan,'native_artifacts':deepcopy(receipt['native']['artifacts'])}
        def complete(self, actual, lease, receipt_sha256, **kwargs):
            assert actual==identity and lease=='e'*32
            assert kwargs['worker_id']=='github:1:2:3' and callable(kwargs['publish'])
            return {'status':'completed','receipt_sha256':receipt_sha256}

    result=publish_receipt(Jobs(),identity,'e'*32,'github:1:2:3',receipt)
    assert result['status']=='completed'


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


def test_missing_database_preserves_only_bounded_probe_error(tmp_path, monkeypatch):
    import pytest
    from nico.assessment_cpp_configure_first_execution import run_configure_first
    from tests.test_cpp_configure_first_contract import contract
    plan = contract()
    root = tmp_path/'source'; root.mkdir()
    cmake = b'project(test)\n'
    (root/'CMakeLists.txt').write_bytes(cmake)
    targets = {'CMakeLists.txt': hashlib.sha256(cmake).hexdigest()}
    acquisition = {'schema':'nico.github_https_tree_materialization.v2',
        'tree_sha':plan['configuration']['expected_tree_sha'], 'inputs':targets,
        'population_sha256':hashlib.sha256(canonical_bytes(targets)).hexdigest()}
    for error, expected in [
        ('worker_configuration_probe_option_unverified', 'worker_configuration_probe_option_unverified'),
        ('private source or credential text', 'worker_configure_first_database_missing'),
        (None, 'worker_configure_first_database_missing'),
    ]:
        monkeypatch.setattr('nico.assessment_cpp_configuration_probe.probe_project_configuration',
            lambda *args, **kwargs: {'error':error})
        with pytest.raises(ValueError, match='^'+expected+'$'):
            run_configure_first(plan, root, acquisition, checkpoint=lambda:None,
                timeout_seconds=60, retain_artifact=lambda key,raw:ref(key,raw))


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
