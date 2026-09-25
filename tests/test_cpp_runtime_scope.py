import hashlib
from pathlib import Path

from nico.assessment_cpp_runtime_scope import derive_runtime_plan


def _write(root: Path, path: str, data: bytes, targets: dict[str,str]):
    p=root/path; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    targets[path]=hashlib.sha256(data).hexdigest()


def test_runtime_plan_is_derived_from_exact_source_interfaces(tmp_path):
    root=tmp_path/'source'; root.mkdir(); targets={}
    cmake=b'''option(BUILD_TESTS "tests" ON)\nset(SANITIZERS "" CACHE STRING "sanitizers")\noption(BUILD_FUZZ_BINARY "fuzz" OFF)\noption(BUILD_FOR_FUZZING "fuzzing" OFF)\n'''
    runner=b'''BASE_SCRIPTS = [\n 'feature_alpha.py', 'mempool_alpha.py', 'p2p_alpha.py --v2transport',\n 'wallet_alpha.py', 'rpc_alpha.py', 'interface_ipc.py',\n 'feature_fast.py', 'mempool_fast.py', 'p2p_fast.py', 'wallet_fast.py', 'rpc_fast.py',\n]\n'''
    fuzz_cmake=b'add_executable(fuzz connect_block.cpp)\n'
    _write(root,'CMakeLists.txt',cmake,targets)
    _write(root,'test/functional/test_runner.py',runner,targets)
    for name in ['feature_fast.py','mempool_fast.py','p2p_fast.py','rpc_fast.py','wallet_fast.py','interface_ipc.py']:
        _write(root,'test/functional/'+name,b'#!/usr/bin/env python3\n',targets)
    _write(root,'test/fuzz/test_runner.py',b'#!/usr/bin/env python3\nFUZZ=1\n',targets)
    _write(root,'src/test/fuzz/CMakeLists.txt',fuzz_cmake,targets)
    _write(root,'src/test/fuzz/connect_block.cpp',b'int x;\n',targets)
    scope={'schema':'nico.cpp-runtime-scope.v1','functional_policy':'source-declared-functional-v1',
        'functional_seconds':900,'sanitizers':['address','undefined'],'sanitizer_build_seconds':1200,
        'sanitizer_test_seconds':600,'sanitizer_test_case_seconds':120,'fuzz_policy':'source-declared-libfuzzer-v1',
        'fuzz_replay_runs':1,'fuzz_campaign_runs':256,'fuzz_campaign_seconds':300,'parallel':4}
    plan=derive_runtime_plan(root,targets,{'ENABLE_IPC':'ON','ENABLE_WALLET':'ON'},scope)
    assert plan['schema']=='nico.cpp-runtime-plan.v1'
    assert plan['functional']['selected_tests']==[
        'feature_fast.py','mempool_fast.py','p2p_fast.py','rpc_fast.py','wallet_fast.py','interface_ipc.py']
    assert plan['sanitizers']['kinds']==['address','undefined']
    assert plan['fuzz']['target']=='connect_block'
    assert plan['fuzz']['qa_assets_commit']=='cf4ec4a6b7fe814dc3f2ddbaa00cd1a7d7c7ae2f'
    assert [x['sha256'] for x in plan['fuzz']['corpus']]==[
        'b711ed78d4987553c5a9fe7ca143ea017af39215f87e6c222b0796779edb3b44',
        'e7cf46a078fed4fafd0b5e3aff144802b853f8ae459a4f0c14add3314b7cc3a6']


def test_runtime_plan_fails_closed_when_required_source_interface_is_missing(tmp_path):
    root=tmp_path/'source'; root.mkdir(); targets={}
    _write(root,'CMakeLists.txt',b'option(BUILD_TESTS "tests" ON)\n',targets)
    scope={'schema':'nico.cpp-runtime-scope.v1','functional_policy':'source-declared-functional-v1',
        'functional_seconds':900,'sanitizers':['address','undefined'],'sanitizer_build_seconds':1200,
        'sanitizer_test_seconds':600,'sanitizer_test_case_seconds':120,'fuzz_policy':'source-declared-libfuzzer-v1',
        'fuzz_replay_runs':1,'fuzz_campaign_runs':256,'fuzz_campaign_seconds':300,'parallel':4}
    import pytest
    with pytest.raises(ValueError, match='runtime_scope_unsupported'):
        derive_runtime_plan(root,targets,{},scope)
