"""Owned compiler-configuration fixtures; not native or Bitcoin qualification."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from nico.assessment_cpp_full_project import execution_steps, validate_native
from nico.assessment_worker_receipts import validate_contract
from tests.test_cpp_generated_context import v3_fixture
from tests.test_assessment_cpp_full_project import encoded

MODE = 'nested-source-v2-gcc-options'
FLAGS = ['-fstack-protector', '-fstack-protector-all', '-fstack-protector-strong',
         '-fstack-protector-explicit', '-fstack-clash-protection',
         '-fvisibility=hidden', '-fvisibility=default', '-fvisibility=internal',
         '-fvisibility=protected', '-fvisibility-inlines-hidden',
         '-fstack-reuse=none', '-fstack-reuse=named_vars', '-fstack-reuse=all',
         '-Werror=return-type', '-Wno-error=unused-parameter']


def configured_native(flags):
    """Supply known synthetic producer outputs at the existing receipt seam."""
    contract, native = v3_fixture()
    config = contract['configuration']
    config.update(schema='nico.cpp-cmake-configuration.v6',
                  nested_base_schema='nico.cpp-cmake-configuration.v4', cmake_layout=MODE)
    # This call fails on the old producer: it has no such supported layout.
    assert validate_contract(contract) == contract
    specs = {row['id']: row for row in execution_steps(contract)}
    for row in native['steps']:
        row['invocation'] = specs[row['id']]['invocation']
    for group in ('baseline', 'address', 'undefined'):
        configured = next(row for row in native['steps'] if row['id'] == group + '-configure')
        database = json.loads(base64.b64decode(configured['artifacts']['compilation_database']))
        compiler = next(row for row in native['steps'] if row['id'] == group + '-compiler-evidence')
        proof = json.loads(base64.b64decode(compiler['output']))
        for row in database:
            row['directory'] += '/src/library'
            row['arguments'][1:1] = flags
        raw = json.dumps(database).encode()
        configured['artifacts']['compilation_database'] = encoded(raw)
        # Native proof must preserve actual flags in order, not silently omit them.
        for record in proof['records']:
            record['invocation'][1:1] = flags
        derived = [{'directory': '/work/analysis', 'file': '/work/source/' + record['unit'],
                    'arguments': record['invocation']} for record in proof['records']]
        proof['database_sha256'] = hashlib.sha256(raw).hexdigest()
        proof['analysis_database_sha256'] = hashlib.sha256(json.dumps(
            derived, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        compiler['output'] = encoded(json.dumps(proof).encode())
        if group == 'baseline':
            analysis = next(row for row in native['steps'] if row['id'] == 'static-analysis')
            analysis['artifacts']['compilation_database'] = encoded(json.dumps(
                derived, sort_keys=True, separators=(',', ':')).encode())
    return contract, native


@pytest.mark.parametrize('flag', FLAGS)
def test_project_flags_remain_bound_through_existing_native_receipt(flag):
    contract, native = configured_native([flag])
    result = validate_native(native, contract)
    assert result['complete'] is True
    assert result['build']['compiled_translation_units'] == ['main.cpp', 'sum.cpp']
    assert result['build']['full_project_qualified'] is False
    for group in ('baseline', 'address', 'undefined'):
        assert result['build']['compiler_evidence'][group]['complete'] is True


def test_order_and_duplicate_flags_are_preserved_not_rewritten():
    contract, native = configured_native(['-fvisibility=hidden', '-fvisibility=default', '-fvisibility=hidden'])
    assert validate_native(native, contract)['complete'] is True


def test_old_generated_and_nested_embedded_programs_keep_exact_identities():
    from nico.assessment_cpp_generated_context import COMPILER_PROGRAM, NESTED_COMPILER_PROGRAM, SNAPSHOT_PROGRAM
    assert hashlib.sha256(COMPILER_PROGRAM.encode()).hexdigest() == 'e733ce201f07381a5a5de7585b6296c3b9d21a5ca236246fc0b10dbd1140ae71'
    assert hashlib.sha256(NESTED_COMPILER_PROGRAM.encode()).hexdigest() == '388a56484e82b3e36f8776b8c14de2e1971b0200b03fe689154744dbb3a15e4d'
    assert hashlib.sha256(SNAPSHOT_PROGRAM.encode()).hexdigest() == '69260ed6a9832caa309c34c70607ca7c8b0136c70abf1395285a42ac1537d084'
    contract, native = v3_fixture()
    assert validate_native(native, contract)['complete'] is True


@pytest.mark.parametrize('flag', ['-fplugin=/work/source/plugin.so', '-specs=/work/source/specs',
    '-wrapper', '-B/work/source/tools', '@response', '-Wl,@payload', '-Wa,@payload',
    '-Xassembler', '-Xlinker', '-fprofile-generate=/work/source', '-save-temps',
    '-fvisibility=hidden/../../x', '-Werror=return-type,/tmp/x', '-Werror=',
    '-D__NICO_PROJECT_OPTION_0_1=1'])
def test_project_mode_does_not_allow_helpers_response_files_or_unreviewed_options(flag):
    contract, native = configured_native([flag])
    with pytest.raises(ValueError): validate_native(native, contract)


def test_dropping_a_recorded_option_is_not_accepted_as_equivalent_evidence():
    contract, native = configured_native(['-fstack-protector-strong'])
    row = next(r for r in native['steps'] if r['id'] == 'baseline-compiler-evidence')
    evidence = json.loads(base64.b64decode(row['output']))
    evidence['records'][0]['invocation'].remove('-fstack-protector-strong')
    row['output'] = encoded(json.dumps(evidence).encode())
    with pytest.raises(ValueError, match='invocation_mismatch'):
        validate_native(native, contract)


def test_old_mode_still_rejects_new_options_instead_of_rewriting_legacy_meaning():
    contract, native = configured_native(['-fstack-protector-strong'])
    contract['configuration']['cmake_layout'] = 'nested-source-v1'
    specs = {r['id']: r for r in execution_steps(contract)}
    for row in native['steps']: row['invocation'] = specs[row['id']]['invocation']
    with pytest.raises(ValueError, match='option_unsupported'):
        validate_native(native, contract)


def test_embedded_program_uses_identical_bound_parser_for_argument_and_command_forms():
    from nico.assessment_cpp_generated_context import PROJECT_COMPILER_PROGRAM, derive_project_database
    source = PROJECT_COMPILER_PROGRAM.removesuffix("\nrun_generated_program('compiler', collect_compiler)\n")
    namespace = {}; exec(compile(source, '<owned-project-parser>', 'exec'), namespace)
    import shlex
    args = ['/usr/local/bin/g++', '-fstack-protector-strong', '-Werror=return-type',
            '-I/work/source', '-I/work/build/generated', '-o', 'result.o', '-c', '/work/source/main.cpp']
    for key, argv in [('arguments', args), ('command', shlex.join(args))]:
        raw = json.dumps([{'directory': '/work/build/src/lib', 'file': '/work/source/main.cpp', key: argv}]).encode()
        expected = derive_project_database(raw, ['main.cpp'], 'baseline', ['generated/config.h'])
        assert namespace['derive_database'](raw, ['main.cpp'], 'baseline', ['generated/config.h']) == expected
        assert b'__NICO_PROJECT_OPTION' not in expected
        value = json.loads(expected)[0]['arguments']
        assert value[1:3] == args[1:3]
        assert '-I/work/analysis/generated-baseline/generated' in value


@pytest.mark.parametrize('position', ['output', 'include', 'source'])
def test_option_placeholders_cannot_make_malformed_operands_valid(position):
    from nico.assessment_cpp_generated_context import derive_project_database
    argv = ['/usr/local/bin/g++', '-I/work/source', '-o', 'main.o', '-c', '/work/source/main.cpp']
    if position == 'output': argv[3] = '-fstack-protector-strong'
    elif position == 'include': argv[1:2] = ['-include', '-fstack-protector-strong']
    else: argv[-1] = '-fstack-protector-strong'
    raw = json.dumps([{'directory':'/work/build/src', 'file':'/work/source/main.cpp', 'arguments':argv}]).encode()
    with pytest.raises(ValueError): derive_project_database(raw, ['main.cpp'], 'baseline', ['generated/config.h'])


def test_owned_native_control_requires_hardening_options_and_keeps_old_default():
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    from scripts.qualify_cpp_full_project_control import FIXTURE
    options = dict(generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    assert fixture() == FIXTURE
    before = fixture(**options)
    value = fixture(**options, project_compiler_options=True)
    assert 'src/library/helper.c' not in before
    assert 'control_identity(' in value['src/library/sum.cpp']
    for flag in ['-fstack-protector-strong', '-fstack-clash-protection', '-fvisibility=hidden', '-Werror=return-type']:
        assert flag in value['src/library/CMakeLists.txt']
    contract = plan('sha256:'+'d'*64, **options, project_compiler_options=True)
    assert validate_contract(contract) == contract
    assert contract['configuration']['cmake_layout'] == MODE
    assert contract['targets'] == {p:hashlib.sha256(s.encode()).hexdigest() for p,s in value.items()}
    assert contract['limits'] == {'max_attempts':1, 'wall_seconds':180, 'lease_seconds':30}
    assert set(before) | {'src/library/helper.c'} == set(value)


def test_configuration_api_rejects_unsupported_or_unbound_option_mode():
    from nico.assessment_cpp_full_project import configuration
    base = dict(units=['main.cpp'], unit_tests=['unit'], integration_tests=['integration'],
                compiler_evidence=True, generated_headers=['generated/config.h'])
    for invalid in [None, 1, [], 'yes']:
        with pytest.raises(ValueError): configuration(**base, nested_cmake=True, project_compiler_options=invalid)
    with pytest.raises(ValueError): configuration(**base, project_compiler_options=True)


def test_hosted_native_workflow_requires_the_new_mode_and_all_its_regressions():
    workflow = (Path(__file__).resolve().parents[1]/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_project_compiler_options.py' in workflow
    assert '--project-compiler-options' in workflow


def test_project_option_control_executes_both_c_and_cpp_translation_units():
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    options = dict(generated_headers=True, bounded_fuzz=True, project_dependencies=True, project_compiler_options=True)
    files = fixture(**options)
    assert 'src/library/helper.c' in files
    assert 'volatile int saved[4]' in files['src/library/helper.c']
    assert 'helper.c' in files['src/library/CMakeLists.txt']
    assert 'c_std_11 cxx_std_20' in files['src/library/CMakeLists.txt']
    assert 'control_identity(' in files['src/library/sum.cpp']
    contract = plan('sha256:'+'d'*64, **options)
    assert contract['configuration']['translation_units'] == ['main.cpp', 'src/library/helper.c', 'src/library/sum.cpp']
    assert set(contract['configuration']['translation_units']) <= set(contract['targets'])
    assert validate_contract(contract) == contract
