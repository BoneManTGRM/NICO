"""Bounded producer/receipt controls; synthetic proofs do not qualify execution.

The backend must independently rebuild each proof from retained raw artifacts.
These controls exercise only summary transport, typed contracts and rejection.
"""
from copy import deepcopy
from dataclasses import asdict
import inspect

import pytest

from nico.assessment_cpp_compiler_collection import collection_summary
from nico.assessment_cpp_configure_first_execution import summarize_probe
from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import validate_receipt
from tests.test_cpp_configure_first_execution import incomplete_receipt, proof, ref


def owned_projection():
    value=proof()
    value.update(schema='nico.cpp-project-configuration-probe.v11', status='UNPROVEN',
        error='worker_configuration_probe_compiler_incomplete', independent_collection_error=None)
    value['project_compiler'].update(attempted_contexts=['c1','c2'], checked_contexts=['c1'], complete=False)
    value['project_static'].update(attempted_contexts=['c1','c2'], analyzed_contexts=['c1'], complete=False,
        header_context_evidence_complete=False, header_population_complete=False,
        header_unvisited_files=['include/unvisited.h'])
    keys=['project-compilation-database','project-generated-context','project-compiler-evidence',
        'project-static-environment','project-static-evidence','project-baseline-evidence',
        'project-enabled-targets','project-native-commands','project-native-commands-post-build',
        'project-enabled-targets-post-build','project-generation-evidence','project-static-clang-fallback']
    artifacts={key:ref(key, ('synthetic '+key).encode()) for key in keys}
    compiler={'schema':'nico.cpp-project-compiler-collection.v1','collection_complete':True,
        'compiler':deepcopy(value['project_compiler']), 'failed_contexts':['c2'],
        'unparsed_contexts':['c2'], 'native_evidence_sha256':artifacts['project-compiler-evidence']['sha256']}
    static={'schema':'nico.cpp-project-static-collection.v1','collection_complete':True,
        'required_contexts':['c1','c2'],'attempted_contexts':['c1','c2'],'analyzed_contexts':['c1'],
        'failed_contexts':['c2'],'unparsed_contexts':['c2'],
        'native_evidence_sha256':artifacts['project-static-evidence']['sha256'],
        'fallback_evidence_sha256':artifacts['project-static-clang-fallback']['sha256']}
    value['project_compiler_collection']=compiler
    value['project_static_stage'].update(schema='nico.cpp-project-static-stage.v4', complete=False,
        collection_complete=True, static_collection=static, boundary_verified=True, cleanup_verified=True)
    value['enabled_target_membership']={'configured_context_count':2,'contexts':['c1','c2'],
        'missing_database_contexts':['c2'],'database_membership_complete':False}
    value['native_command_plan']={'context_argv_binding_verified':True,'analysis_executed':False,
        'execution_authorized':False,'context_count':2,'contexts':['c1','c2']}
    value['native_command_freeze']={'verified':True}
    value['analysis_compilation_database_sha256']='a'*64
    value['analysis_invocations']=2
    value['generated_input_materialization']={'complete':True,'plan':{'selected_targets':[]}}
    return value, {'CMakeLists.txt':'d'*64,'src/a.cpp':'e'*64}, artifacts


def current_summary(value, targets, artifacts):
    kwargs={}
    # Original source can exercise the intended behavior without a missing API
    # import or unexpected-keyword failure hiding the policy regression.
    if 'collect_completed_compiler_failures' in inspect.signature(summarize_probe).parameters:
        kwargs['collect_completed_compiler_failures']=True
    return summarize_probe(value, targets, artifacts, **kwargs)


def current_receipt(runtime=False):
    identity, plan, receipt=incomplete_receipt(runtime=runtime)
    cfg=plan['configuration']
    cfg.pop('project_options', None)
    cfg.update(schema='nico.cpp-configure-first-contract.v'+('10' if runtime else '11'),
        project_option_policy='conservative-cmake-v1')
    cfg['capabilities'].update(capture_enabled_targets=True, capture_native_commands=True,
        materialize_generated_inputs=True, collect_completed_compiler_failures=True)
    value, targets, artifacts=owned_projection()
    native=current_summary(value, targets, artifacts)
    # Construct the new native envelope independently for original validator
    # rejection evidence; the synthetic proof is explicitly not raw validation.
    native.update(schema='nico.cpp-configure-first-native.v'+('10' if runtime else '9'),
        collection_complete=True, independent_collection_error=None,
        project_compiler_collection=collection_summary(value['project_compiler_collection']),
        project_static_collection=collection_summary(value['project_static_stage']['static_collection']),
        project_option_policy='conservative-cmake-v1', project_options={}, project_options_sha256=_digest({}))
    if runtime:
        native['artifacts']['project-runtime-evidence']=ref('project-runtime-evidence', b'synthetic failed runtime')
        native.update(runtime_complete=False, runtime_plan_sha256='f'*64,
            runtime_summary_sha256=_digest({'complete':False}), runtime_duration_ms=7)
    identity=JobIdentity(identity.customer_id,identity.project_id,identity.run_id,identity.scan_id,
        identity.repository_id,identity.revision,_digest(plan),identity.release_revision)
    receipt.update(identity=asdict(identity), configuration_sha256=_digest(cfg), target_hashes=targets,
        native=native, native_sha256=_digest(native))
    return identity, plan, receipt


def check(identity, plan, receipt):
    receipt['native_sha256']=_digest(receipt['native'])
    return validate_receipt(identity, plan, 'e'*32, 'github:1:2:3', receipt)


def test_collected_generated_failure_is_transported_without_execution_or_header_success():
    value, targets, artifacts=owned_projection()
    native=current_summary(value, targets, artifacts)
    assert native.get('collection_complete') is True
    assert native['schema']=='nico.cpp-configure-first-native.v9'
    assert native['complete_execution'] is False
    assert native['project_compiler_complete'] is False and native['project_compiler_checked_count']==1
    assert native['project_static_complete'] is False and native['project_static_analyzed_count']==1
    assert native['header_context_evidence_complete'] is False
    assert native['header_unvisited_files_count']==1
    assert native['project_compiler_collection']==collection_summary(value['project_compiler_collection'])
    assert native['project_static_collection']==collection_summary(value['project_static_stage']['static_collection'])


def test_receipt_envelope_does_not_grant_canonical_collection_before_raw_reconstruction():
    identity,plan,receipt=current_receipt()
    _,record,_=check(identity,plan,receipt)
    assert record['cpp_build_evidence']['collection_complete'] is False
    assert record['cpp_build_evidence']['collection_claimed_complete'] is True


@pytest.mark.parametrize('locale,compiler,analyzer',[
    ('en','Compiler contexts: attempted=2/2; verified syntax=1/2; failed=1; unparsed=1.',
          'Analyzer contexts: attempted=2/2; normal pass completed=1/2; failed=1; unparsed=1.'),
    ('es-MX','Contextos del compilador: intentados=2/2; sintaxis verificada=1/2; fallidos=1; sin analizar=1.',
             'Contextos del analizador: intentados=2/2; pase normal completado=1/2; fallidos=1; sin analizar=1.')])
def test_report_collection_counts_preserve_failed_unparsed_outcomes_and_require_reconstruction(locale,compiler,analyzer):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    identity,plan,receipt=current_receipt();_,record,_=check(identity,plan,receipt)
    sha='a'*64
    record.update(raw_artifact_retention_complete=True,raw_artifact_sha256=sha,
        execution_observed_for_this_report=True,commit_sha=identity.revision,
        worker_provenance={'profile':'cpp-configure-first-v2','receipt_sha256':sha,
            'identity':{'run_id':identity.run_id,'revision':identity.revision}})
    canonical={'report_language':locale,'identity':{'run_id':identity.run_id,'commit_sha':identity.revision},
        'scanner_execution_records':[record]}
    stage={'summary':'','evidence':[],'unavailable':[]}
    assert compiler not in enrich_scanner_stage(canonical,stage)['summary']
    # Rendering input is a synthetic canonical control; raw reconstruction is
    # tested independently. A transported claim alone never reaches this state.
    record['cpp_build_evidence']['collection_complete']=True
    result=enrich_scanner_stage(canonical,stage)
    assert compiler in result['summary'] and analyzer in result['summary']
    assert result['unavailable'] and record['completed'] is False


@pytest.mark.parametrize('runtime', [False, True])
def test_current_receipt_retains_target_failure_and_collection_without_scanner_approval(runtime):
    identity, plan, receipt=current_receipt(runtime)
    _, record, _=check(identity,plan,receipt)
    assert record['status']=='failed' and record['completed'] is False
    assert record['verified_complete'] is False and record['verified_for_this_report'] is False
    assert record['client_delivery_allowed'] is False and record['human_review_required'] is True
    assert record['cpp_build_evidence']['collection_complete'] is False
    assert record['cpp_build_evidence']['collection_claimed_complete'] is True
    assert record['cpp_build_evidence']['configure_error']=='worker_configuration_probe_compiler_incomplete'
    assert record['cppcheck_source_coverage']['header_context_verified'] is False
    if runtime:
        assert record['cpp_build_evidence']['runtime_complete'] is False


@pytest.mark.parametrize('fault', ['legacy_probe','missing_compiler_proof','missing_static_proof',
    'missing_artifact','partial_tests','skipped_tests','boundary','cleanup','generation','native_mapping',
    'static_boundary','static_cleanup','independent_error'])
def test_producer_missing_ready_dependency_cannot_claim_complete_collection(fault):
    value, targets, artifacts=owned_projection()
    if fault=='legacy_probe':value['schema']='nico.cpp-project-configuration-probe.v10'
    elif fault=='missing_compiler_proof':value['project_compiler_collection']=None
    elif fault=='missing_static_proof':value['project_static_stage']['static_collection']=None
    elif fault=='missing_artifact':artifacts.pop('project-baseline-evidence')
    elif fault=='partial_tests':value['tests_result']['executed']=['a']
    elif fault=='skipped_tests':value['tests_result']['skipped']=['b']
    elif fault=='boundary':value['boundary_verified']=False
    elif fault=='cleanup':value['cleanup_verified']=False
    elif fault=='generation':value['generated_input_materialization']['complete']=False
    elif fault=='native_mapping':value['native_command_plan']['context_argv_binding_verified']=False
    elif fault=='static_boundary':value['project_static_stage']['boundary_verified']=False
    elif fault=='static_cleanup':value['project_static_stage']['cleanup_verified']=False
    elif fault=='independent_error':value['independent_collection_error']='worker_configuration_probe_static_failed'
    assert current_summary(value,targets,artifacts).get('collection_complete') is False


@pytest.mark.parametrize('field,replacement', [('collection_complete',1),('required_contexts_count',True),
    ('required_contexts_count',3),('attempted_contexts_sha256','0'*64),('failed_contexts_count',0),
    ('unparsed_contexts_sha256','1'*64),('native_evidence_sha256','2'*64),('proof_sha256','bad'),
    ('secondary_native_evidence_sha256','3'*64)])
def test_receipt_rejects_malformed_or_substituted_compiler_collection_summary(field,replacement):
    identity,plan,receipt=current_receipt()
    receipt['native']['project_compiler_collection'][field]=replacement
    with pytest.raises(ValueError,match='native_invalid'):
        check(identity,plan,receipt)


@pytest.mark.parametrize('fault', ['old_schema','missing_field','extra_field','missing_ref','false_header',
    'static_failed_mismatch','compiler_success','static_success','unknown_error','unbounded_error',
    'missing_fallback','false_status','omitted_compiler_error'])
def test_current_record_rejects_downgrade_false_credit_and_unbound_population(fault):
    identity,plan,receipt=current_receipt()
    native=receipt['native']
    if fault=='old_schema':native['schema']='nico.cpp-configure-first-native.v7'
    elif fault=='missing_field':native.pop('project_compiler_collection')
    elif fault=='extra_field':native['synthetic_approval']=True
    elif fault=='missing_ref':native['artifacts'].pop('project-baseline-evidence')
    elif fault=='false_header':native['header_context_evidence_complete']=True
    elif fault=='static_failed_mismatch':native['project_static_collection']['failed_contexts_sha256']='a'*64
    elif fault=='compiler_success':native['project_compiler_complete']=True
    elif fault=='static_success':native['project_static_complete']=True
    elif fault=='unknown_error':native['error']='worker_configuration_probe_snapshot_unavailable'
    elif fault=='unbounded_error':native['independent_collection_error']='private arbitrary failure body'
    elif fault=='missing_fallback':native['artifacts'].pop('project-static-clang-fallback');native['project_static_collection']['secondary_native_evidence_sha256']=None
    elif fault=='false_status':native['status']='BASELINE_EXECUTED'
    elif fault=='omitted_compiler_error':native['error']=None
    with pytest.raises(ValueError,match='native_invalid'):
        check(identity,plan,receipt)


def test_current_runtime_collection_claim_requires_retained_runtime_artifact():
    identity,plan,receipt=current_receipt(True)
    receipt['native']['artifacts'].pop('project-runtime-evidence')
    with pytest.raises(ValueError,match='native_invalid'):
        check(identity,plan,receipt)


def test_completed_failed_ctest_does_not_turn_collection_into_tests_passed():
    value,targets,artifacts=owned_projection()
    value['tests_passed']=False
    value['tests_result']['passed']=['a']
    native=current_summary(value,targets,artifacts)
    assert native.get('collection_complete') is True
    assert native['tests_passed'] is False and native['tests_passed_count']==1


def test_current_policy_before_compiler_capture_retains_only_truthful_incomplete_fields():
    value,targets,artifacts=owned_projection()
    value['project_compiler_collection']=None
    value['project_static_stage']['static_collection']=None
    native=current_summary(value,targets,artifacts)
    assert native['schema']=='nico.cpp-configure-first-native.v9'
    assert native['collection_complete'] is False
    assert native['project_compiler_collection'] is None and native['project_static_collection'] is None


def test_green_current_envelope_cannot_downgrade_to_legacy_native_version():
    from nico.assessment_cpp_header_evidence import HEADER_TOOL_MANIFEST_SHA256
    identity,plan,receipt=current_receipt()
    value,targets,artifacts=owned_projection()
    value.update(status='BASELINE_EXECUTED',error=None)
    value['project_compiler'].update(complete=True,checked_contexts=['c1','c2'])
    value['project_static'].update(complete=True,analyzed_contexts=['c1','c2'],
        header_context_evidence=[{},{}],header_context_evidence_complete=True,
        header_population_complete=True,header_unvisited_files=[],header_tool_manifest_sha256=HEADER_TOOL_MANIFEST_SHA256)
    compiler=value['project_compiler_collection']
    compiler.update(compiler=deepcopy(value['project_compiler']),failed_contexts=[],unparsed_contexts=[])
    static=value['project_static_stage']['static_collection']
    static.update(analyzed_contexts=['c1','c2'],failed_contexts=[],unparsed_contexts=[])
    value['project_static_stage']['complete']=True
    native=current_summary(value,targets,artifacts)
    native.update(project_option_policy='conservative-cmake-v1',project_options={},project_options_sha256=_digest({}))
    assert native['complete_execution'] is True and native['collection_complete'] is True
    receipt['native']=native
    _,record,_=check(identity,plan,receipt)
    assert record['status']=='partial' and record['verified_complete'] is False
    receipt['native']['schema']='nico.cpp-configure-first-native.v7'
    with pytest.raises(ValueError,match='native_invalid'):
        check(identity,plan,receipt)


@pytest.mark.parametrize('runtime_collected',[False,True])
def test_current_wrapper_binds_policy_retained_runtime_and_schema_without_success_inference(
        tmp_path,monkeypatch,runtime_collected):
    import base64
    from nico.assessment_cpp_configure_first_execution import run_configure_first
    identity,plan,_=current_receipt(True)
    value,_,artifacts=owned_projection()
    source=tmp_path/'source';source.mkdir()
    cmake=b'option(BUILD_TESTS "tests" OFF)\n'
    (source/'CMakeLists.txt').write_bytes(cmake)
    targets={'CMakeLists.txt':_digest(cmake.decode())}
    import hashlib
    targets['CMakeLists.txt']=hashlib.sha256(cmake).hexdigest()
    acquisition={'schema':'nico.github_https_tree_materialization.v2',
        'tree_sha':plan['configuration']['expected_tree_sha'], 'inputs':targets,'population_sha256':_digest(targets)}
    runtime_plan={'schema':'nico.cpp-runtime-plan.v1','total_seconds':6000,'unit_test_data':None}
    retained_raw={};seen={}
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.capture_runtime_interfaces',lambda *args:{'owned':True})
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.derive_runtime_plan_from_interfaces',lambda *args:runtime_plan)
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.acquire_unit_test_data',lambda *args:None)
    monkeypatch.setattr('nico.assessment_cpp_runtime_scope.retained_runtime_bytes',lambda *args:b'synthetic retained failed runtime')
    monkeypatch.setattr('nico.assessment_cpp_baseline_evidence.retained_baseline_bytes',lambda *args,**kwargs:b'synthetic baseline')
    def produce(actual_source,actual_targets,image,**kwargs):
        seen['policy']=kwargs.get('collect_completed_compiler_failures')
        actual=deepcopy(value)
        actual['compilation_database']=base64.b64encode(b'[]').decode()
        actual['compilation_database_sha256']=hashlib.sha256(b'[]').hexdigest()
        actual['runtime_evidence']={'schema':'nico.cpp-runtime-evidence.v4','duration_ms':7}
        actual['runtime_summary']={'complete':False}
        for key in artifacts:
            if key not in {'project-compilation-database','project-baseline-evidence'}:
                kwargs['retain_artifact'](key,('synthetic '+key).encode())
        return actual
    def retain(key,raw):
        retained_raw[key]=raw
        return ref(key,raw)
    def validate_runtime(raw,actual_targets,options,scope):
        seen['runtime_raw']=raw
        assert raw==retained_raw['project-runtime-evidence']
        assert actual_targets==targets and scope==plan['configuration']['runtime_scope']
        if not runtime_collected:
            raise ValueError('worker_runtime_collection_incomplete')
        # This substitutes only the runtime verifier result for a controlled
        # failure envelope; it grants no actual runtime execution evidence.
        return {'collection_complete':True,'target_tests_passed':False}
    monkeypatch.setattr('nico.assessment_cpp_configuration_probe.probe_project_configuration',produce)
    monkeypatch.setattr('nico.assessment_cpp_runtime_collection.validate_runtime_collection',validate_runtime)
    result=run_configure_first(plan,source,acquisition,checkpoint=lambda:None,
        timeout_seconds=8980,retain_artifact=retain)
    native=result['native']
    assert seen['policy'] is True and seen['runtime_raw']==b'synthetic retained failed runtime'
    assert native['schema']=='nico.cpp-configure-first-native.v10'
    assert native['runtime_complete'] is False and native['complete_execution'] is False
    assert native['collection_complete'] is runtime_collected
    assert native['error']=='worker_configuration_probe_compiler_incomplete'
    assert native['independent_collection_error']==(None if runtime_collected else 'worker_configuration_probe_runtime_incomplete')
