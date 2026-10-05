"""Owned native Make rules retain omitted contexts and ordered arguments.

The primary fixture was actually configured/built with CMake3.31.6/GCC14.2.
These replays prove data reconstruction, not production execution.
"""
from pathlib import Path
import base64
import copy
import hashlib
import importlib
import json
import shlex

import pytest

FIXTURE = Path(__file__).parent / 'fixtures/cpp/fileapi-native-arguments-v15'


def owned():
    return fixture(FIXTURE)


def fixture(path):
    provenance = json.loads((path / 'fixture-provenance.json').read_bytes())
    for row in provenance['files']:
        raw = (path / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    data = json.loads((path / 'fixture.json').read_bytes())
    return data, (path / 'native-capture.json').read_bytes(), (path / 'fileapi-capture.json').read_bytes(), (path / 'compile_commands.json').read_bytes()


def reconstruct(data, native, fileapi, database):
    try:
        module = importlib.import_module('nico.assessment_cpp_native_commands')
    except ModuleNotFoundError:
        # Existing installed behavior reconstructs only the original DB.
        # Preserve the semantic failing population, not an import-only failure.
        return {'contexts': json.loads(database), 'context_argv_binding_verified': False}
    return module.configured_native_commands(native, fileapi, database, data['targets'], **data['membership_kwargs'])


def test_export_suppressed_context_has_the_exact_owned_native_argument_order():
    data, native, fileapi, database = owned()
    assert {Path(x['file']).name for x in json.loads(database)} == {'main.c'}
    plan = reconstruct(data, native, fileapi, database)
    assert len(plan['contexts']) == 2
    actual = {x[x.index('-c') + 1]: x for x in data['native_compile_commands']}
    assert {x['file']: x['arguments'] for x in plan['contexts']} == actual
    assert plan['context_argv_binding_verified'] is True
    assert plan['execution_authorized'] is False
    assert plan['analysis_executed'] is False
    assert plan['analyzer_header_coverage_verified'] is False
    assert plan['original_database_sha256'] == data['original_database_sha256']


def test_same_source_keeps_both_actual_target_contexts_and_source_specific_settings():
    data, native, fileapi, database = fixture(FIXTURE.parent / 'fileapi-native-contexts-v15')
    plan = reconstruct(data, native, fileapi, database)
    assert plan['context_count'] == 4
    assert plan['original_database_context_count'] == plan['omitted_database_context_count'] == 2
    repeated = [c for c in plan['contexts'] if c['file'].endswith('/common.cpp')]
    assert len(repeated) == 2 and len({c['context_id'] for c in repeated}) == 2
    alpha, beta = sorted(repeated, key=lambda c: c['target_name'])
    assert alpha['directory'].endswith('/alpha') and beta['directory'].endswith('/beta')
    assert '-DSOURCE_SENTINEL=31' in alpha['arguments'] and '-Wextra' in alpha['arguments']
    assert '-DSOURCE_SENTINEL=37' in beta['arguments'] and '-Wconversion' in beta['arguments']
    assert alpha['arguments'][alpha['arguments'].index('-DMODE=1'):][:3] == ['-DMODE=1', '-UMODE', '-DMODE=2']
    assert beta['arguments'][beta['arguments'].index('-DMODE=1'):][:3] == ['-DMODE=1', '-UMODE', '-DMODE=7']
    actual = {tuple(a) for a in data['native_compile_commands']}
    assert {tuple(c['literal_arguments']) for c in plan['contexts']} == actual
    assert sum(len(c['response_files']) for c in plan['contexts']) == 6
    assert plan['analysis_executed'] is False


def pack(raw):
    return {'data': base64.b64encode(raw).decode(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def ctest_recipe_fixture(change=None):
    data, raw, fileapi, database = owned()
    native = json.loads(raw)
    cmake = data['membership_kwargs'].get('cmake_path', '/usr/local/bin/cmake')
    ctest = cmake.rsplit('/', 1)[0] + '/ctest'
    name = 'CMakeFiles/Makefile2' if change == 'other_parent' else 'Makefile'
    rule = 'test: all'
    recipe = '\t' + ctest + ' --force-new-ctest-process $(ARGS)'
    if change == 'foreign_ctest': recipe = recipe.replace(ctest, '/foreign/ctest')
    elif change == 'extra_operand': recipe += ' --extra'
    elif change == 'shell_suffix': recipe += '; true'
    elif change == 'dynamic_args': recipe = recipe.replace('$(ARGS)', '$(shell true)')
    elif change == 'other_target': rule = 'other: all'
    elif change == 'other_prerequisite': rule = 'test: unbound'
    elif change == 'compiler_args': recipe = '\t' + data['membership_kwargs']['compiler_paths']['C'] + ' $(ARGS)'
    content = base64.b64decode(native['files'][name]['data'])
    assert b'\ntest:' not in content
    content += ('\n' + rule + '\n' + recipe + '\n.PHONY : test\n').encode()
    if change == 'args_assignment': content += b'ARGS = --unbound\n'
    native['files'][name] = pack(content)
    return data, json.dumps(native, sort_keys=True, separators=(',', ':')).encode(), fileapi, database


def test_generated_top_level_ctest_recipe_does_not_change_compiler_contexts():
    before = reconstruct(*owned())
    after = reconstruct(*ctest_recipe_fixture())
    assert after['contexts'] == before['contexts']
    assert after['analysis_database'] == before['analysis_database']
    assert after['execution_authorized'] is False and after['analysis_executed'] is False


@pytest.mark.parametrize('change', ['foreign_ctest', 'extra_operand', 'shell_suffix',
    'dynamic_args', 'other_target', 'other_prerequisite', 'compiler_args',
    'args_assignment', 'other_parent'])
def test_ctest_args_exception_cannot_modify_commands_or_another_rule(change):
    with pytest.raises(ValueError, match='worker_native_command_plan_invalid'):
        reconstruct(*ctest_recipe_fixture(change))


@pytest.mark.parametrize('target', ['hidden-target', 'hidden.target', 'hidden+target'])
def test_generated_object_variable_uses_the_target_make_identifier(target):
    from nico.assessment_cpp_native_commands import _make_environment
    data, raw, unused_fileapi, unused_database = owned()
    native = json.loads(raw)
    files = {name: base64.b64decode(row['data']) for name, row in native['files'].items()}
    original = 'CMakeFiles/hidden.dir'
    renamed = 'CMakeFiles/' + target + '.dir'
    variable = target.replace('.', '_').replace('-', '__').replace('+', '___')
    captured = {}
    for name, content in files.items():
        name = name.replace(original, renamed)
        content = content.replace(original.encode(), renamed.encode())
        content = content.replace(b'hidden_OBJECTS', (variable + '_OBJECTS').encode())
        content = content.replace(b'hidden_EXTERNAL_OBJECTS', (variable + '_EXTERNAL_OBJECTS').encode())
        captured[name] = content
    kwargs = data['membership_kwargs']
    _make_environment(captured[renamed + '/build.make'], captured,
        kwargs['build_root'] + '/' + renamed, kwargs['source_root'], kwargs['build_root'],
        kwargs.get('cmake_path', '/usr/local/bin/cmake'))
    wrong = captured[renamed + '/build.make'].replace(
        (variable + '_OBJECTS').encode(), b'foreign_OBJECTS')
    with pytest.raises(ValueError, match='worker_native_command_plan_invalid'):
        _make_environment(wrong, captured, kwargs['build_root'] + '/' + renamed,
            kwargs['source_root'], kwargs['build_root'], kwargs.get('cmake_path', '/usr/local/bin/cmake'))


def test_inert_dependency_evolution_preserves_commands_but_overrides_are_rejected():
    from nico.assessment_cpp_native_commands import validate_native_plan_freeze
    data, before, fileapi, database = owned()
    after = json.loads(before)
    name = 'CMakeFiles/hidden.dir/compiler_depend.make'
    after['files'][name] = pack(b'# Dependencies generated by the compiler.\nCMakeFiles/hidden.dir/hidden.c.o: ' +
        data['membership_kwargs']['source_root'].encode() + b'/hidden.c\n')
    encode = lambda value: json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    freeze = validate_native_plan_freeze(before,encode(after),fileapi,database,data['targets'],**data['membership_kwargs'])
    assert freeze['exact_command_inputs_unchanged'] is True
    assert freeze['validated_dependency_changes'] == [name]
    assert freeze['before_capture_sha256'] != freeze['after_capture_sha256']
    after['files'][name] = pack(b'C_FLAGS = -DEVIL\n')
    with pytest.raises(ValueError):
        validate_native_plan_freeze(before,encode(after),fileapi,database,data['targets'],**data['membership_kwargs'])


@pytest.mark.parametrize('change', [
    'missing_rule', 'missing_flags', 'missing_include', 'extra_file', 'wrong_digest',
    'wrong_database', 'wrong_cache', 'wrong_fileapi', 'wrong_root', 'wrong_compiler',
    'wrong_source', 'wrong_output', 'extra_object', 'unknown_make_variable',
    'make_function', 'global_override', 'target_override', 'conditional', 'extra_include',
    'dependency_override', 'dependency_make_function', 'progress_override', 'shell_change',
    'echo_make_function', 'shell_substitution', 'shell_compound', 'wrapper',
])
def test_incomplete_or_dynamic_native_rules_cannot_bind_authoritative_arguments(change):
    data, raw, fileapi, database = owned()
    native = json.loads(raw)
    prefix = 'CMakeFiles/hidden.dir/'
    name = prefix + 'build.make'
    content = base64.b64decode(native['files'][name]['data'])
    compiler = data['membership_kwargs']['compiler_paths']['C']
    source = data['membership_kwargs']['source_root'] + '/hidden.c'
    if change.startswith('missing_'):
        native['files'].pop(prefix + {'missing_rule':'build.make','missing_flags':'flags.make','missing_include':'depend.make'}[change])
    elif change == 'extra_file':
        native['files']['foreign/flags.make'] = pack(b'x')
    elif change == 'wrong_digest':
        native['files'][name]['sha256'] = '0' * 64
    elif change in {'wrong_database','wrong_cache','wrong_fileapi'}:
        native[{'wrong_database':'database_sha256','wrong_cache':'cache_sha256','wrong_fileapi':'fileapi_capture_sha256'}[change]] = '0' * 64
    elif change == 'wrong_root':
        native['build_root'] += '/other'
    elif change == 'dependency_override':
        native['files'][prefix+'depend.make'] = pack(b'C_DEFINES = -DTARGET_SENTINEL=99\n')
    elif change == 'dependency_make_function':
        native['files'][prefix+'compiler_depend.make'] = pack(b'x: $(shell echo wrong)\n')
    elif change == 'progress_override':
        native['files'][prefix+'progress.make'] = pack(b'C_FLAGS = -DBAD=1\n')
    else:
        edits = {
            'wrong_compiler': (compiler, '/usr/bin/wrong'),
            'wrong_source': ('-c '+source, '-c '+source+'.changed'),
            'wrong_output': ('-o CMakeFiles/hidden.dir/hidden.c.o', '-o CMakeFiles/hidden.dir/other.c.o'),
            'unknown_make_variable': ('$(C_FLAGS)', '$(UNKNOWN_FLAGS)'),
            'make_function': ('$(C_FLAGS)', '$(shell echo wrong)'),
            'shell_change': ('SHELL = /bin/sh', 'SHELL = /bin/bash'),
            'echo_make_function': ('--switch=$(COLOR)', '--switch=$(shell echo wrong)'),
            'shell_substitution': ('$(C_FLAGS)', '$(C_FLAGS) `echo wrong`'),
            'shell_compound': ('$(C_FLAGS)', '$(C_FLAGS); echo wrong'),
            'wrapper': ('\t'+compiler+' ', '\tenv '+compiler+' '),
        }
        if change in edits:
            before, after = edits[change]
            assert before.encode() in content
            content = content.replace(before.encode(), after.encode())
        else:
            additions = {
                'global_override': 'C_DEFINES = -DTARGET_SENTINEL=99\n',
                'target_override': 'CMakeFiles/hidden.dir/hidden.c.o: C_DEFINES = -DTARGET_SENTINEL=99\n',
                'conditional': 'ifeq (1,1)\nC_DEFINES = -DBAD=1\nendif\n',
                'extra_include': 'include foreign.make\n',
                'extra_object': 'CMakeFiles/hidden.dir/other.c.o: '+source+'\n\t'+compiler+' $(C_DEFINES) $(C_INCLUDES) $(C_FLAGS) -o CMakeFiles/hidden.dir/other.c.o -c '+source+'\n',
            }
            content += additions[change].encode()
        native['files'][name] = pack(content)
    with pytest.raises(ValueError, match='worker_native_command_plan_invalid'):
        reconstruct(data, json.dumps(native, sort_keys=True, separators=(',', ':')).encode(), fileapi, database)


@pytest.mark.parametrize('text,expected', [
    (b"'a\\b'", ['ab']), (b'"" \'\' x', ['', '', 'x']),
    (b'a\\ b "c d" e\\\"f', ['a b','c d','e"f']),
    (b'\t\r\n', []), (b'', []),
])
def test_gcc_response_grammar_preserves_exact_documented_order(text, expected):
    from nico.assessment_cpp_native_commands import gcc_response_arguments
    assert gcc_response_arguments(text) == expected
    if text == b"'a\\b'":
        assert expected != shlex.split(text.decode())


@pytest.mark.parametrize('rule', [b'.ONESHELL:\n', b'.IGNORE:\n', b'%.o: source.c\n',
    b'object.o:: source.c\n', b'object.o: source.c ; echo changed\n'])
def test_dependency_metadata_cannot_change_make_execution(rule):
    data, raw, fileapi, database = owned()
    native = json.loads(raw)
    name = next(name for name in native['files'] if name.endswith('/compiler_depend.make'))
    native['files'][name] = pack(rule)
    with pytest.raises(ValueError, match='worker_native_command_plan_invalid'):
        reconstruct(data, json.dumps(native, sort_keys=True, separators=(',', ':')).encode(), fileapi, database)


@pytest.mark.parametrize('change', ['missing','digest','escape','cycle','nested_missing','oversize','unmatched_quote','nul'])
def test_response_capture_is_complete_bounded_and_nondynamic(change):
    data, raw, fileapi, database = fixture(FIXTURE.parent / 'fileapi-native-contexts-v15')
    native = json.loads(raw)
    name = 'beta/CMakeFiles/beta.dir/options.rsp'
    if change == 'missing':
        native['files'].pop(name)
    elif change == 'digest':
        native['files'][name]['sha256'] = '0' * 64
    else:
        value = {'escape':b'@../outside.rsp','cycle':('@'+data['membership_kwargs']['build_root']+'/'+name).encode(),
            'nested_missing':b'@missing.rsp','oversize':b'x'*(1024*1024+1),'unmatched_quote':b"'",'nul':b'x\0'}[change]
        native['files'][name] = pack(value)
    with pytest.raises(ValueError, match='worker_native_command_plan_invalid'):
        reconstruct(data,json.dumps(native, sort_keys=True, separators=(',', ':')).encode(),fileapi,database)
