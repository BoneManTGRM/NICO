"""Owned, synthetic compilation databases; never Bitcoin execution evidence."""
import base64
from copy import deepcopy
import json
import hashlib

import pytest

from nico.assessment_cpp_full_project import _database, validate_native
from nico.assessment_cpp_generated_context import derive_database, derive_nested_database
from tests.test_assessment_cpp_full_project import plan, native, encoded


@pytest.mark.parametrize('group', ['baseline', 'address', 'undefined'])
@pytest.mark.parametrize('child', ['src', 'src/wallet', 'libraries/common'])
def test_frozen_nested_cmake_working_directory_is_supported(group, child):
    root = '/work/build' if group == 'baseline' else '/work/' + group
    source = '/work/source/main.cpp'
    argv = ['/usr/local/bin/g++', '-I/work/source', '-I' + root + '/generated',
            '-g', '-o', 'CMakeFiles/main.dir/main.cpp.o', '-c', source]
    if group != 'baseline': argv.insert(1, '-fsanitize=' + group)
    raw = json.dumps([{'directory': root + '/' + child, 'file': source, 'arguments': argv}]).encode()
    assert _database(raw, ['main.cpp'], root, None if group == 'baseline' else group, nested=True) == ['main.cpp']
    frozen = json.loads(derive_nested_database(raw, ['main.cpp'], group, ['generated/config.h']))
    assert frozen[0]['directory'] == '/work/analysis'
    assert '-I/work/analysis/generated-' + group + '/generated' in frozen[0]['arguments']
    assert source == frozen[0]['file']
    assert json.loads(raw)[0]['directory'] == root + '/' + child


@pytest.mark.parametrize('directory', [None, 1, '/work/build-other/src', '/work/address/src',
    '/work/build/../source', '/work/build//src', '/work/build/./src', '/work/build/.git',
    '/work/build/src/..', '/work/build/src\\bad', '/work/build/src\n', '/tmp/src',
    '/work/build/', '/work/build/' + 'x' * 501])
def test_other_or_noncanonical_working_directories_are_rejected(directory):
    source = '/work/source/main.cpp'
    raw = json.dumps([{'directory': directory, 'file': source,
        'arguments': ['/usr/local/bin/g++', '-o', 'main.o', '-c', source]}]).encode()
    with pytest.raises(ValueError): _database(raw, ['main.cpp'], '/work/build', nested=True)
    with pytest.raises(ValueError): derive_nested_database(raw, ['main.cpp'], 'baseline', ['generated/config.h'])


def test_nested_database_reaches_existing_receipt_coverage_without_changing_population():
    from nico.assessment_cpp_full_project import execution_steps
    from nico.assessment_worker_receipts import validate_contract
    from tests.test_cpp_generated_context import v3_fixture
    p, n = v3_fixture()
    p['configuration'].update(schema='nico.cpp-cmake-configuration.v6',
        nested_base_schema='nico.cpp-cmake-configuration.v4', cmake_layout='nested-source-v1')
    assert validate_contract(p) == p
    specs = {s['id']: s for s in execution_steps(p)}
    for row in n['steps']:
        row['invocation'] = specs[row['id']]['invocation']
    for group in ('baseline', 'address', 'undefined'):
        row = next(r for r in n['steps'] if r['id'] == group + '-configure')
        data = json.loads(base64.b64decode(row['artifacts']['compilation_database']))
        for entry in data: entry['directory'] += '/src'
        raw = json.dumps(data).encode()
        row['artifacts']['compilation_database'] = encoded(raw)
        compiler = next(r for r in n['steps'] if r['id'] == group + '-compiler-evidence')
        proof = json.loads(base64.b64decode(compiler['output']))
        proof['database_sha256'] = hashlib.sha256(raw).hexdigest()
        compiler['output'] = encoded(json.dumps(proof).encode())
    result = validate_native(n, p)
    assert result['complete'] is True
    assert result['build']['build_completed'] is True
    assert result['coverage']['requested_targets'] == ['main.cpp', 'sum.cpp']
    assert result['build']['full_project_qualified'] is False
    for group in ('baseline', 'address', 'undefined'):
        assert result['build']['compiler_evidence'][group]['complete'] is True
    missing = deepcopy(n)
    configured = next(r for r in missing['steps'] if r['id'] == 'baseline-configure')
    data = json.loads(base64.b64decode(configured['artifacts']['compilation_database']))
    configured['artifacts']['compilation_database'] = encoded(json.dumps(data[:1]).encode())
    with pytest.raises(ValueError): validate_native(missing, p)


def test_legacy_database_and_program_contracts_are_not_redefined():
    from nico.assessment_cpp_generated_context import COMPILER_PROGRAM, NESTED_COMPILER_PROGRAM
    from nico.assessment_cpp_full_project import execution_steps
    from tests.test_cpp_generated_context import v3_fixture
    raw = json.dumps([{'directory': '/work/build/src', 'file': '/work/source/main.cpp',
        'arguments': ['/usr/local/bin/g++', '-o', 'main.o', '-c', '/work/source/main.cpp']}]).encode()
    with pytest.raises(ValueError): _database(raw, ['main.cpp'], '/work/build')
    with pytest.raises(ValueError): derive_database(raw, ['main.cpp'], 'baseline', ['include/config.h'])
    assert COMPILER_PROGRAM != NESTED_COMPILER_PROGRAM
    assert 'valid_build_directory' not in COMPILER_PROGRAM
    contract, native = v3_fixture()
    assert next(s for s in execution_steps(contract) if s['id'] == 'baseline-compiler-evidence')['invocation'][-1] == COMPILER_PROGRAM
    assert validate_native(native, contract)['complete'] is True
    compile(NESTED_COMPILER_PROGRAM, '<nested-compiler>', 'exec')


@pytest.mark.parametrize('mode', [True, False, None, 1, {}, [], 'unknown'])
def test_new_configuration_rejects_invalid_or_smuggled_layout(mode):
    from nico.assessment_worker_receipts import validate_contract
    from tests.test_cpp_generated_context import v3_fixture
    contract, _ = v3_fixture()
    contract['configuration'].update(schema='nico.cpp-cmake-configuration.v6',
        nested_base_schema='nico.cpp-cmake-configuration.v4', cmake_layout=mode)
    with pytest.raises(ValueError): validate_contract(contract)


@pytest.mark.parametrize('schema', ['nico.cpp-cmake-configuration.v1', 'nico.cpp-cmake-configuration.v3',
                                  'nico.cpp-cmake-configuration.v6', None])
def test_new_configuration_cannot_change_old_schema_or_recursively_wrap(schema):
    from nico.assessment_worker_receipts import validate_contract
    from tests.test_cpp_generated_context import v3_fixture
    contract, _ = v3_fixture()
    contract['configuration'].update(schema='nico.cpp-cmake-configuration.v6',
        nested_base_schema=schema, cmake_layout='nested-source-v1')
    with pytest.raises(ValueError): validate_contract(contract)


def test_embedded_nested_compiler_uses_the_same_bound_database_parser():
    from nico.assessment_cpp_generated_context import NESTED_COMPILER_PROGRAM
    # Load trusted function definitions only. No compiler/target program executes.
    definitions = NESTED_COMPILER_PROGRAM.removesuffix("\nrun_generated_program('compiler', collect_compiler)\n")
    namespace = {}; exec(compile(definitions, '<owned-parser-definitions>', 'exec'), namespace)
    raw = json.dumps([{'directory': '/work/build/src/library', 'file': '/work/source/main.cpp',
        'arguments': ['/usr/local/bin/g++', '-I/work/source', '-I/work/build/include',
                      '-o', 'main.o', '-c', '/work/source/main.cpp']}]).encode()
    assert namespace['derive_database'](raw, ['main.cpp'], 'baseline', ['include/config.h']) == derive_nested_database(
        raw, ['main.cpp'], 'baseline', ['include/config.h'])
