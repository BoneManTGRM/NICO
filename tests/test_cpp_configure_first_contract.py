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


@pytest.mark.parametrize('native_commands', [False, True])
def test_native_command_contract_cannot_downgrade_its_declared_capability(native_commands):
    value = contract()
    cfg = value['configuration']
    cfg.pop('project_options')
    cfg.update(schema='nico.cpp-configure-first-contract.v6' if native_commands else
        'nico.cpp-configure-first-contract.v4', project_option_policy='conservative-cmake-v1')
    cfg['capabilities']['capture_enabled_targets'] = True
    if native_commands:
        cfg['capabilities']['capture_native_commands'] = True
    assert validate_contract(value) == value
    broken = deepcopy(value)
    broken['configuration']['capabilities']['capture_native_commands'] = not native_commands
    with pytest.raises(ValueError, match='capabilities_invalid'):
        validate_contract(broken)
    if native_commands:
        broken['configuration']['capabilities'].pop('capture_native_commands')
        with pytest.raises(ValueError, match='capabilities_invalid'):
            validate_contract(broken)


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


@pytest.mark.parametrize('runtime',[False,True])
def test_current_generation_contract_rejects_legacy_capability_downgrade(runtime):
    from nico.assessment_cpp_production_selection import select_configure_first_contract
    from tests.test_cpp_production_selection import repo_step,env,RELEASE
    paths=['CMakeLists.txt','src/a.cpp']
    if runtime:
        paths += ['test/functional/test_runner.py','test/fuzz/test_runner.py',
                  'src/test/fuzz/CMakeLists.txt','src/test/fuzz/connect_block.cpp']
    value=select_configure_first_contract(repo_step(paths),environ=env(),release_revision=RELEASE)
    assert validate_contract(value)==value
    assert value['configuration']['schema']=='nico.cpp-configure-first-contract.v'+('9' if runtime else '8')
    for replacement in (False,None):
        broken=deepcopy(value)
        if replacement is None:broken['configuration']['capabilities'].pop('materialize_generated_inputs')
        else:broken['configuration']['capabilities']['materialize_generated_inputs']=replacement
        with pytest.raises(ValueError,match='capabilities_invalid'):validate_contract(broken)
    # Historical contract identities remain readable with their actual scope.
    historical=deepcopy(value)
    historical['configuration']['schema']='nico.cpp-configure-first-contract.v'+('7' if runtime else '6')
    historical['configuration']['capabilities'].pop('materialize_generated_inputs')
    assert validate_contract(historical)==historical
