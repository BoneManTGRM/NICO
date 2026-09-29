import hashlib
from pathlib import Path
import pytest
from nico.assessment_cpp_cmake_policy import POLICY, derive_project_options


def materialized(tmp_path, text):
    root=tmp_path/'source'; root.mkdir()
    raw=text.encode(); (root/'CMakeLists.txt').write_bytes(raw)
    return root, {'CMakeLists.txt':hashlib.sha256(raw).hexdigest()}


def test_policy_derives_only_declared_safe_baseline_options(tmp_path):
    root,targets=materialized(tmp_path, '''
cmake_minimum_required(VERSION 3.22)
option(BUILD_TESTS "tests" OFF)
option(BUILD_GUI "gui" ON)
option(BUILD_BENCH "bench" ON)
option(BUILD_FUZZ_BINARY "fuzz" OFF)
option(BUILD_FOR_FUZZING "fuzz-only" OFF)
option(ENABLE_WALLET "wallet" OFF)
cmake_dependent_option(WITH_ZMQ "zmq" ON "ENABLE_WALLET" OFF)
option(ENABLE_IPC "ipc" OFF)
option(UNRELATED_PROJECT_SWITCH "leave me alone" ON)
''')
    result=derive_project_options(root,targets,POLICY)
    assert result=={
        'BUILD_BENCH':'OFF','BUILD_FOR_FUZZING':'OFF','BUILD_FUZZ_BINARY':'OFF',
        'BUILD_GUI':'OFF','BUILD_TESTS':'ON','ENABLE_IPC':'ON','ENABLE_WALLET':'ON','WITH_ZMQ':'OFF'}
    assert 'UNRELATED_PROJECT_SWITCH' not in result


def test_policy_ignores_commented_option_and_is_repository_name_independent(tmp_path):
    root,targets=materialized(tmp_path, '# option(BUILD_GUI "not real" ON)\nproject(whatever)\n')
    assert derive_project_options(root,targets,POLICY)=={}
    assert 'bitcoin' not in Path(__import__('nico.assessment_cpp_cmake_policy',fromlist=['x']).__file__).read_text().lower()


def test_policy_fails_closed_on_substituted_cmakelists(tmp_path):
    root,targets=materialized(tmp_path, 'option(BUILD_TESTS "tests" ON)\n')
    targets['CMakeLists.txt']='0'*64
    with pytest.raises(ValueError,match='source_invalid'):
        derive_project_options(root,targets,POLICY)


def test_policy_output_validator_rejects_worker_invented_option():
    from nico.assessment_cpp_cmake_policy import validate_project_options
    assert validate_project_options({'BUILD_TESTS':'ON','BUILD_GUI':'OFF'}) == {'BUILD_GUI':'OFF','BUILD_TESTS':'ON'}
    with pytest.raises(ValueError,match='options_invalid'):
        validate_project_options({'UNRELATED_PROJECT_SWITCH':'OFF'})
    with pytest.raises(ValueError,match='options_invalid'):
        validate_project_options({'BUILD_TESTS':'OFF'})


@pytest.mark.parametrize('declaration,expected', [
    ('cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "BUILD_GUI;BUILD_TESTS" OFF)', False),
    ('cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "BUILD_TESTS" OFF)', True),
    ('cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "UNKNOWN" OFF)', True),
    ('cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "NOT BUILD_GUI" OFF)', True),
    ('cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "BUILD_GUI" ON)', True),
    ('option(BUILD_GUI_TESTS "tests" ON)', True),
])
def test_dependent_options_require_proven_inactive_matching_fallback(tmp_path, declaration, expected):
    root, targets = materialized(tmp_path, 'option(BUILD_GUI "gui" ON)\n'
        'option(BUILD_TESTS "tests" OFF)\n' + declaration + '\n')
    options = derive_project_options(root, targets, POLICY)
    assert ('BUILD_GUI_TESTS' in options) is expected
    assert options['BUILD_GUI'] == 'OFF'
    assert options['BUILD_TESTS'] == 'ON'


def test_dependent_parent_cannot_justify_omission(tmp_path):
    root, targets = materialized(tmp_path, '''
cmake_dependent_option(BUILD_GUI "gui" OFF "UNKNOWN" ON)
cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "BUILD_GUI" OFF)
''')
    assert derive_project_options(root, targets, POLICY)['BUILD_GUI_TESTS'] == 'OFF'


def test_real_cmake_inactive_dependent_uses_fallback_without_internal_override(tmp_path):
    import shutil
    import subprocess
    cmake = shutil.which('cmake')
    if cmake is None:
        pytest.skip('CMake required for native cache semantics regression')
    root, targets = materialized(tmp_path, '''
cmake_minimum_required(VERSION 3.22)
project(DependentOptions NONE)
include(CMakeDependentOption)
option(BUILD_GUI "gui" ON)
option(BUILD_TESTS "tests" OFF)
cmake_dependent_option(BUILD_GUI_TESTS "tests" ON "BUILD_GUI;BUILD_TESTS" OFF)
if(BUILD_GUI OR BUILD_GUI_TESTS OR NOT BUILD_TESTS)
  message(FATAL_ERROR "Incorrect effective baseline options")
endif()
''')
    options = derive_project_options(root, targets, POLICY)
    subprocess.run([cmake, '-S', str(root), '-B', str(tmp_path/'build'),
        *[f'-D{k}={v}' for k, v in options.items()]], check=True, capture_output=True)
    cache = (tmp_path/'build/CMakeCache.txt').read_text()
    assert 'BUILD_GUI:BOOL=OFF' in cache
    assert 'BUILD_TESTS:BOOL=ON' in cache
    assert 'BUILD_GUI_TESTS:INTERNAL' not in cache
