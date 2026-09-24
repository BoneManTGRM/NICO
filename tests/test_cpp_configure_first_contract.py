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
