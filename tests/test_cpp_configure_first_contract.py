from copy import deepcopy
import pytest
from nico.assessment_worker_receipts import validate_contract

def contract():
    return {'profile':'cpp-configure-first-v2','tool_version':'2.17.1','image_digest':'sha256:'+'d'*64,
        'configuration':{'schema':'nico.cpp-configure-first-contract.v1','platform':'linux/amd64',
            'expected_tree_sha':'b'*40,'project_options':{},'source_byte_limit':64*1024*1024,
            'baseline_execution':{'schema':'nico.cpp-baseline-execution.v2','profile':'cpp-baseline-qualification-v1',
                'freeze_compilation_database':'after_configuration_before_build','build_seconds':1200,
                'test_seconds':480,'test_case_seconds':60,'parallel':4},
            'capabilities':{'capture_generated_context':True,'project_compiler_evidence':True,
                'project_static_analysis':True,'extended_compiler_budget':True,'compiler_environment':True}},
        'targets':{},'limits':{'max_attempts':1,'wall_seconds':2420,'lease_seconds':120},'max_receipt_bytes':8*1024*1024}

def test_configure_first_contract_is_strict_and_internal_source_population_is_initially_empty():
    value=contract(); assert validate_contract(value)==value
    for change in ({'targets':{'CMakeLists.txt':'a'*64}},
                   {'configuration':{**value['configuration'],'expected_tree_sha':'x'*40}},
                   {'limits':{'max_attempts':1,'wall_seconds':2421,'lease_seconds':120}}):
        broken=deepcopy(value); broken.update(change)
        with pytest.raises(ValueError): validate_contract(broken)


def test_configure_first_v2_accepts_only_release_owned_cmake_policy():
    value=contract()
    value['configuration'].pop('project_options')
    value['configuration'].update(schema='nico.cpp-configure-first-contract.v2',
        project_option_policy='conservative-cmake-v1')
    assert validate_contract(value)==value
    broken=deepcopy(value); broken['configuration']['project_option_policy']='caller-selected'
    with pytest.raises(ValueError): validate_contract(broken)


def test_configure_first_v3_freezes_required_runtime_scope_before_execution():
    value=contract()
    value['configuration'].pop('project_options')
    value['configuration'].update(
        schema='nico.cpp-configure-first-contract.v3',
        project_option_policy='conservative-cmake-v1',
        runtime_scope={
            'schema':'nico.cpp-runtime-scope.v1',
            'total_seconds':6000,
            'functional_policy':'source-declared-functional-v1',
            'functional_seconds':900,
            'sanitizers':['address','undefined'],
            'sanitizer_build_seconds':1200,
            'sanitizer_test_seconds':600,
            'sanitizer_test_case_seconds':120,
            'fuzz_policy':'source-declared-libfuzzer-v1',
            'fuzz_replay_runs':1,
            'fuzz_campaign_runs':256,
            'fuzz_campaign_seconds':300,
            'parallel':4,
        })
    value['limits']={'max_attempts':1,'wall_seconds':9000,'lease_seconds':300}
    assert validate_contract(value)==value
    for field, replacement in (
        ('total_seconds',5999),
        ('sanitizers',['address']),
        ('functional_policy','disabled'),
        ('fuzz_policy','disabled'),
        ('fuzz_campaign_runs',0),
    ):
        broken=deepcopy(value)
        broken['configuration']['runtime_scope'][field]=replacement
        with pytest.raises(ValueError):
            validate_contract(broken)
