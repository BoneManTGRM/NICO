"""Source-bound command inventory must not erase generated or repeated contexts."""
import base64
from copy import deepcopy
import hashlib
import json
import shlex

import pytest

from nico import assessment_cpp_full_project as project
from nico import assessment_cpp_configuration_probe as probe
from tests.test_cpp_configuration_qualification import Docker, source


def rows():
    result = []
    for source_path, define, output in (
        ('/work/source/main.cpp', 'ONE=1', 'CMakeFiles/one.dir/main.cpp.o'),
        ('/work/source/main.cpp', 'TWO=1', 'CMakeFiles/two.dir/main.cpp.o'),
        ('/work/build/sub/generated.cpp', 'GEN=1', 'CMakeFiles/gen.dir/generated.cpp.o'),
    ):
        argv = ['/usr/local/bin/g++', '-D' + define, '-I/work/build/sub',
                '-std=c++20', '-o', output, '-c', source_path]
        result.append({'directory': '/work/build/sub', 'file': source_path,
                       'command': shlex.join(argv), 'output': 'sub/' + output})
    return result


def targets():
    return {'CMakeLists.txt': 'a' * 64, 'main.cpp': 'b' * 64}


def inventory(value=None, original=None):
    function = getattr(project, 'compilation_contexts', None)
    assert callable(function), 'missing original/generated/multiple-context adapter'
    return function(json.dumps(rows() if value is None else value).encode(),
                    targets() if original is None else original, '/work/build')


def test_every_original_generated_and_repeated_command_has_a_distinct_bound_context():
    value = rows()
    proof = inventory(value)
    assert proof['schema'] == 'nico.cpp-compilation-contexts.v1'
    assert proof['database_sha256'] == hashlib.sha256(json.dumps(value).encode()).hexdigest()
    assert proof['original_units'] == ['main.cpp']
    assert proof['generated_units'] == ['sub/generated.cpp']
    assert proof['context_count'] == 3
    contexts = proof['contexts']
    assert [c['index'] for c in contexts] == [0, 1, 2]
    assert len({c['context_id'] for c in contexts}) == 3
    assert [c['origin'] for c in contexts] == ['original', 'original', 'generated']
    assert [c['source_sha256'] for c in contexts] == ['b' * 64, 'b' * 64, None]
    assert [c['arguments'] for c in contexts] == [shlex.split(r['command']) for r in value]
    assert contexts[2]['file'] == '/work/build/sub/generated.cpp'
    assert contexts[2]['output_path'] == '/work/build/sub/CMakeFiles/gen.dir/generated.cpp.o'
    assert proof['generated_bytes_captured'] is False
    assert proof['analysis_executed'] is False and proof['header_dependencies_verified'] is False
    assert proof['execution_authorized'] is False


def test_context_identity_tracks_inputs_not_row_order_or_command_quoting():
    original = inventory()['contexts']
    assert [c['context_id'] for c in inventory(list(reversed(rows())))['contexts']] == [
        c['context_id'] for c in reversed(original)]
    arguments = rows()
    for row in arguments:
        row['arguments'] = shlex.split(row.pop('command'))
    assert [c['context_id'] for c in inventory(arguments)['contexts']] == [c['context_id'] for c in original]
    changed = targets(); changed['main.cpp'] = 'c' * 64
    after = inventory(original=changed)['contexts']
    assert after[0]['context_id'] != original[0]['context_id']
    assert after[2]['context_id'] == original[2]['context_id']
    assert inventory(original=changed)['source_population_sha256'] != inventory()['source_population_sha256']


@pytest.mark.parametrize('field,value', [
    ('directory', '/work/build/../source'), ('directory', '/work/build//sub'),
    ('directory', '/work/build/.git'), ('directory', '/tmp/build'),
    ('file', '/work/build/../secret.cpp'), ('file', '/work/build/.git/secret.cpp'),
    ('file', '/work/build2/generated.cpp'), ('file', '/work/source/missing.cpp'),
    ('output', '../../outside.o'), ('output', '/etc/out.o'),
    ('output', 'sub/wrong.o'), ('output', ''),
])
def test_out_of_scope_paths_and_output_substitution_are_rejected(field, value):
    altered = rows(); altered[0][field] = value
    with pytest.raises(ValueError): inventory(altered)


@pytest.mark.parametrize('argv', [
    ['/bin/sh', '-c', '/work/source/main.cpp'],
    ['/usr/local/bin/g++', '-o', 'main.o', '-c', '/work/source/other.cpp'],
    ['/usr/local/bin/g++', '-o', '../../out.o', '-c', '/work/source/main.cpp'],
    ['/usr/local/bin/g++', '-o', 'main.o', '-c', '/work/source/main.cpp', '-c', '/work/source/main.cpp'],
    ['/usr/local/bin/g++', '-o', 'main.o', '-c', '/work/source/main.cpp', '\x00'],
])
def test_compiler_source_and_output_binding_is_checked_without_executing(argv):
    altered = rows(); altered[0].pop('command'); altered[0].pop('output')
    altered[0]['arguments'] = argv
    with pytest.raises(ValueError): inventory(altered)


def test_ambiguous_command_forms_and_duplicate_contexts_do_not_inflate_coverage():
    altered = rows(); altered[0]['arguments'] = shlex.split(altered[0]['command'])
    assert inventory(altered)['context_count'] == 3
    altered[0]['arguments'][1] = '-DDIFFERENT=1'
    with pytest.raises(ValueError): inventory(altered)
    with pytest.raises(ValueError): inventory([rows()[0], rows()[0]])
    with pytest.raises(ValueError): inventory(original={'main.cpp': 'not-a-hash'})


def test_database_adapter_is_explicit_and_legacy_population_rules_are_unchanged():
    raw = json.dumps(rows()).encode()
    function = getattr(project, 'compilation_contexts', None)
    assert callable(function), 'missing original/generated/multiple-context adapter'
    with pytest.raises(ValueError, match='database_path_invalid'):
        project._database(raw, ['main.cpp'], '/work/build', nested=True)
    proof = project._database(raw, ['main.cpp'], '/work/build', nested=True, source_targets=targets())
    assert proof == function(raw, targets(), '/work/build')
    with pytest.raises(ValueError, match='population_invalid'):
        project._database(raw, ['main.cpp', 'missing.cpp'], '/work/build', nested=True, source_targets=targets())


def test_configuration_probe_uses_the_shared_context_adapter_and_retains_native_bytes(tmp_path):
    root, original = source(tmp_path)
    docker = Docker(original)
    raw = json.dumps(rows()).encode()
    def boundary(args, **kwargs):
        observed = docker(args, **kwargs)
        if probe.READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
            observed['output'] = json.dumps({'data': base64.b64encode(raw).decode(), 'truncated': False}).encode()
        return observed
    result = probe.probe_project_configuration(root, original, 'sha256:' + 'a' * 64,
        project_options={'BUILD_TESTS': 'ON'}, command=boundary)
    assert result['status'] == 'CONFIGURATION_CAPTURED'
    assert result.get('schema') == 'nico.cpp-project-configuration-probe.v3'
    assert result.get('compilation_contexts', {}).get('context_count') == 3, 'probe still collapses command contexts'
    assert result['compilation_contexts'] == project.compilation_contexts(raw, original, '/work/build')
    assert result['configured_invocations'] == 3 and result['configured_translation_units'] == ['main.cpp']
    assert result['configured_generated_units'] == ['sub/generated.cpp']
    assert result['compiled'] is False and result['full_project_qualified'] is False
    assert base64.b64decode(result['compilation_database']) == raw


def test_parser_failure_retains_returned_bytes_and_cannot_be_configuration_success(tmp_path):
    root, original = source(tmp_path)
    docker = Docker(original)
    bad = rows(); bad[0]['command'] = '/bin/sh -c /work/source/main.cpp'
    raw = json.dumps(bad).encode()
    def boundary(args, **kwargs):
        observed = docker(args, **kwargs)
        if probe.READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
            observed['output'] = json.dumps({'data': base64.b64encode(raw).decode(), 'truncated': False}).encode()
        return observed
    result = probe.probe_project_configuration(root, original, 'sha256:' + 'a' * 64,
        project_options={'BUILD_TESTS': 'ON'}, command=boundary)
    assert result['status'] == 'UNPROVEN', 'invalid compiler metadata was accepted'
    retained = next(r for r in result['operations'] if r['id'] == 'compilation-database')
    assert base64.b64decode(json.loads(base64.b64decode(retained['output']))['data']) == raw
    assert result['cleanup_verified'] is True


def test_input_limits_duplicate_json_and_sanitizer_binding():
    function = getattr(project, 'compilation_contexts', None)
    assert callable(function), 'missing original/generated/multiple-context adapter'
    for raw in (b'[]', b'{}', b'x' * (4 * 1024 * 1024 + 1), b'[{"file":1,"file":2}]'):
        with pytest.raises(ValueError): function(raw, targets(), '/work/build')
    value = rows()
    with pytest.raises(ValueError): function(json.dumps(value).encode(), targets(), '/work/build', sanitizer='address')
    with pytest.raises(ValueError): function(json.dumps(value).encode(), targets(), '/tmp/build')


def test_equivalent_output_metadata_cannot_create_a_second_context():
    altered = [rows()[0], deepcopy(rows()[0])]
    altered[1]['output'] = '/work/build/' + altered[1]['output']
    with pytest.raises(ValueError, match='context_duplicate'):
        inventory(altered)


def test_explicit_null_argument_list_is_not_a_second_valid_command_encoding():
    altered = rows(); altered[0]['arguments'] = None
    with pytest.raises(ValueError): inventory(altered)


def test_original_and_generated_same_relative_name_stay_in_separate_namespaces():
    altered = rows(); altered[2]['file'] = '/work/build/main.cpp'
    altered[2]['command'] = altered[2]['command'].replace('/work/build/sub/generated.cpp', '/work/build/main.cpp')
    proof = inventory(altered)
    assert proof['original_units'] == proof['generated_units'] == ['main.cpp']
    assert len({c['context_id'] for c in proof['contexts']}) == 3
    assert proof['contexts'][2]['source_sha256'] is None


def test_context_schema_is_not_an_existing_worker_completion_receipt():
    from nico.assessment_worker_capacity_v1 import select_production_profile
    proof = inventory()
    assert select_production_profile(proof) is None
    assert proof['execution_authorized'] is False


def test_new_context_regressions_are_in_the_hosted_contract_gate():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / '.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_compilation_contexts.py' in text
