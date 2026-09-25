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
            'schema':'nico.cpp-runtime-scope.v1','functional_policy':'source-declared-functional-v1',
            'functional_seconds':900,'sanitizers':['address','undefined'],'sanitizer_build_seconds':1200,
            'sanitizer_test_seconds':600,'sanitizer_test_case_seconds':120,
            'fuzz_policy':'source-declared-libfuzzer-v1','fuzz_replay_runs':1,
            'fuzz_campaign_runs':256,'fuzz_campaign_seconds':300,'parallel':4})
    plan['limits']={'max_attempts':1,'wall_seconds':9000,'lease_seconds':300}
    root=tmp_path/'source'; root.mkdir()
    cmake=b'option(BUILD_TESTS "tests" OFF)\\noption(BUILD_GUI "gui" ON)\\n'
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
