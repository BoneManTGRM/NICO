"""Source-bound CMake project contract and independently reconstructed evidence.

This profile is internal only. Accepting a contract is not production selection
or qualification. Static-analysis completion, build/test outcomes, and missing
fuzz/header proof are deliberately separate. Commands never run in this module.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import shlex
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from nico.assessment_cpp_configuration import CHECKS, COMPILER_VERSION, decode_stream

PROFILE = 'cpp-full-project-v1'
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
CMAKE_VERSION = '3.31.6'


def configuration(*, units, unit_tests, integration_tests, compiler_evidence=False,
                  native_test_evidence=False, generated_headers=None, bounded_fuzz=None, nested_cmake=False, project_compiler_options=False):
    """Create a bounded configuration, not an authorization/qualification flag."""
    if type(compiler_evidence) is not bool or type(native_test_evidence) is not bool or (native_test_evidence and not compiler_evidence):
        raise ValueError('worker_compiler_mode_invalid')
    result = {'schema': 'nico.cpp-cmake-configuration.v1', 'platform': 'linux/amd64',
        'cmake_version': CMAKE_VERSION, 'compiler_version': COMPILER_VERSION,
        'translation_units': sorted(units), 'unit_tests': sorted(unit_tests),
        'integration_tests': sorted(integration_tests), 'project_options': {},
        'build_targets': [], 'parallel': 1, 'source_byte_limit': MAX_SOURCE_BYTES,
        'sanitizers': ['address', 'undefined']}
    if compiler_evidence:
        result.update(schema='nico.cpp-cmake-configuration.v2', compiler_evidence='isolated-recompile-v1')
    if native_test_evidence:
        result.update(schema='nico.cpp-cmake-configuration.v3', native_test_evidence='bound-binary-replay-v1')
    if generated_headers is not None:
        from nico.assessment_cpp_generated_context import MODE, validate_header_paths
        if not compiler_evidence:
            raise ValueError('worker_generated_compiler_required')
        # v3 is the already-published native replay contract. Never reuse its
        # identity for the independently prepared generated-header increment.
        result.update(schema='nico.cpp-cmake-configuration.v4', compiler_evidence=MODE,
                      generated_headers=validate_header_paths(generated_headers),
                      native_test_evidence=('bound-binary-replay-v1' if native_test_evidence else 'not_requested'))
    if bounded_fuzz is not None:
        if not native_test_evidence:
            raise ValueError('worker_fuzz_native_binding_required')
        result.update(fuzz_base_schema=result['schema'], schema='nico.cpp-cmake-configuration.v5',
                      bounded_fuzz=deepcopy(bounded_fuzz))
    if type(nested_cmake) is not bool:
        raise ValueError('worker_nested_cmake_mode_invalid')
    if type(project_compiler_options) is not bool or (project_compiler_options and not nested_cmake):
        raise ValueError('worker_project_compiler_options_invalid')
    if nested_cmake:
        if generated_headers is None:
            raise ValueError('worker_nested_cmake_generated_context_required')
        result.update(nested_base_schema=result['schema'], schema='nico.cpp-cmake-configuration.v6',
                      cmake_layout=('nested-source-v2-gcc-options' if project_compiler_options else 'nested-source-v1'))
    return result


def _path(value):
    return (isinstance(value, str) and len(value) <= 500
        and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*', value)
        and all(p not in {'', '.', '..', '.git'} for p in value.split('/')))


def _names(values, *, empty=False):
    return (isinstance(values, list) and (empty or bool(values)) and len(values) <= 4096
        and all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./:+-]{0,199}', x) for x in values)
        and values == sorted(set(values)))


def validate_configuration(config, targets):
    if isinstance(config, dict) and config.get('schema') == 'nico.cpp-cmake-configuration.v6':
        base = deepcopy(config)
        schema = base.pop('nested_base_schema', None)
        mode = base.pop('cmake_layout', None)
        if (not isinstance(schema, str) or schema not in {'nico.cpp-cmake-configuration.v4', 'nico.cpp-cmake-configuration.v5'}
                or mode not in ('nested-source-v1', 'nested-source-v2-gcc-options') or not base.get('generated_headers')):
            raise ValueError('worker_nested_cmake_configuration_invalid')
        base['schema'] = schema
        validate_configuration(base, targets)
        return deepcopy(config)
    if isinstance(config, dict) and config.get('schema') == 'nico.cpp-cmake-configuration.v5':
        from nico.assessment_cpp_fuzz import validate_plan
        base = deepcopy(config)
        schema = base.pop('fuzz_base_schema', None)
        fuzz = base.pop('bounded_fuzz', None)
        if schema not in {'nico.cpp-cmake-configuration.v3', 'nico.cpp-cmake-configuration.v4'}:
            raise ValueError('worker_fuzz_base_configuration_invalid')
        base['schema'] = schema
        validate_configuration(base, targets)
        if base.get('native_test_evidence') != 'bound-binary-replay-v1':
            raise ValueError('worker_fuzz_native_binding_required')
        validate_plan(fuzz, targets)
        return deepcopy(config)
    fields = {'schema', 'platform', 'cmake_version', 'compiler_version', 'translation_units',
        'unit_tests', 'integration_tests', 'project_options', 'build_targets', 'parallel',
        'source_byte_limit', 'sanitizers'}
    schema = config.get('schema') if isinstance(config, dict) else None
    direct = schema in {'nico.cpp-cmake-configuration.v2', 'nico.cpp-cmake-configuration.v3',
                        'nico.cpp-cmake-configuration.v4'}
    generated = schema == 'nico.cpp-cmake-configuration.v4'
    bound_tests = schema == 'nico.cpp-cmake-configuration.v3'
    if direct:
        fields = fields | {'compiler_evidence'}
    if bound_tests or generated:
        fields = fields | {'native_test_evidence'}
    if generated:
        fields = fields | {'generated_headers'}
    if (not isinstance(config, dict) or set(config) != fields
            or schema not in {'nico.cpp-cmake-configuration.v1', 'nico.cpp-cmake-configuration.v2',
                              'nico.cpp-cmake-configuration.v3', 'nico.cpp-cmake-configuration.v4'}
            or (direct and config['compiler_evidence'] != (
                'isolated-recompile-v2-generated-context' if generated else 'isolated-recompile-v1'))
            or (bound_tests and config['native_test_evidence'] != 'bound-binary-replay-v1')
            or (generated and config['native_test_evidence'] not in ('bound-binary-replay-v1', 'not_requested'))
            or config['platform'] != 'linux/amd64' or config['cmake_version'] != CMAKE_VERSION
            or config['compiler_version'] != COMPILER_VERSION
            or type(config['parallel']) is not int or not 1 <= config['parallel'] <= 2
            or type(config['source_byte_limit']) is not int
            or not 1 <= config['source_byte_limit'] <= MAX_SOURCE_BYTES):
        raise ValueError('worker_full_project_configuration_invalid')
    units = config['translation_units']
    if (not _names(units) or any(not _path(p) for p in units)
            or not set(units) <= set(targets) or 'CMakeLists.txt' not in targets
            or not _names(config['unit_tests']) or not _names(config['integration_tests'])
            or set(config['unit_tests']) & set(config['integration_tests'])
            or config['build_targets'] != []
            or config['sanitizers'] != ['address', 'undefined']):
        raise ValueError('worker_full_project_population_invalid')
    options = config['project_options']
    if (not isinstance(options, dict) or len(options) > 64
            or any(not isinstance(k, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', k)
                or k.startswith('CMAKE_') or not isinstance(v, str)
                or not re.fullmatch(r'[A-Za-z0-9_./+-]{1,120}', v) for k, v in options.items())):
        raise ValueError('worker_full_project_options_invalid')
    if generated:
        from nico.assessment_cpp_generated_context import validate_header_paths
        validate_header_paths(config['generated_headers'])
    return deepcopy(config)


def execution_steps(contract):
    config = contract['configuration']
    generated = config.get('fuzz_base_schema', config.get('nested_base_schema', config.get('schema'))) == 'nico.cpp-cmake-configuration.v4'
    steps = []
    def add(key, args, needs=(), artifacts=None, **extra):
        steps.append({'id': key, 'invocation': args, 'needs': list(needs),
                      'artifacts': artifacts or {}, **extra})
    add('cmake-version', ['cmake', '--version'])
    add('compiler-version', ['g++', '-dumpfullversion'])
    add('analyzer-version', ['cppcheck', '--version'])
    for group in ('baseline', *config['sanitizers']):
        directory = '/work/build' if group == 'baseline' else '/work/' + group
        args = ['cmake', '-S', '/work/source', '-B', directory, '-G', 'Unix Makefiles',
            '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_COMPILER=/usr/local/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++']
        args += ['-D' + k + '=' + v for k, v in sorted(config['project_options'].items())]
        extra = {}
        if group != 'baseline':
            flags = '-fsanitize=' + group + ' -fno-sanitize-recover=all -fno-omit-frame-pointer -fno-pie'
            args += ['-DCMAKE_C_FLAGS=' + flags, '-DCMAKE_CXX_FLAGS=' + flags,
                     '-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=' + group + ' -no-pie']
            extra['sanitizer'] = group
        add(group + '-configure', args, ('cmake-version', 'compiler-version'),
            {'compilation_database': directory + '/compile_commands.json'}, build_dir=directory, **extra)
        build = ['cmake', '--build', directory, '--parallel', str(config['parallel'])]
        if config['build_targets']: build += ['--target', *config['build_targets']]
        add(group + '-build', build, (group + '-configure',))
        if config.get('compiler_evidence'):
            if generated:
                from nico.assessment_cpp_generated_context import SNAPSHOT_PROGRAM, COMPILER_PROGRAM, NESTED_COMPILER_PROGRAM, PROJECT_COMPILER_PROGRAM
                PROGRAM = (PROJECT_COMPILER_PROGRAM if config.get('cmake_layout') == 'nested-source-v2-gcc-options' else
                           NESTED_COMPILER_PROGRAM if config.get('cmake_layout') == 'nested-source-v1' else COMPILER_PROGRAM)
                add(group + '-generated-context', ['python3', '-I', '-S', '-c', SNAPSHOT_PROGRAM],
                    (group + '-build',), generated_configuration=group)
            else:
                from nico.assessment_cpp_compiler_evidence import PROGRAM
            add(group + '-compiler-evidence', ['python3', '-I', '-S', '-c', PROGRAM],
                (group + '-generated-context' if generated else group + '-build',), compiler_configuration=group)
        if group == 'baseline':
            add('static-analysis', ['cppcheck', '--xml', '--enable=' + CHECKS,
                '--check-level=exhaustive', '--max-configs=1', '--platform=unix64', '-j1',
                '--project=/work/analysis/compile_commands.json', '--output-file=/work/analysis/cppcheck.xml'],
                ('baseline-generated-context' if generated else 'baseline-build', 'analyzer-version'),
                {'analysis_xml': '/work/analysis/cppcheck.xml',
                    'compilation_database': '/work/analysis/compile_commands.json'})
        add(group + '-discover', ['ctest', '--test-dir', directory, '--show-only=json-v1'], (group + '-build',))
        for kind in ('unit', 'integration'):
            names = config[kind + '_tests']
            pattern = '^(' + '|'.join(re.escape(name) for name in names) + ')$'
            output = '/work/' + group + '-' + kind + '.xml'
            add(group + '-' + kind, ['ctest', '--test-dir', directory, '--no-tests=error',
                '--output-on-failure', '--parallel', '1', '--timeout', '30', '-R', pattern,
                '--output-junit', output], (group + '-discover',), {'junit': output}, tests=names)
    if config.get('native_test_evidence') == 'bound-binary-replay-v1':
        for group in config['sanitizers']:
            add(group + '-native-test-evidence', ['nico-controller:bound-native-tests-v1', group],
                (group + '-discover',), native_test_configuration=group)
    if config.get('bounded_fuzz') is not None:
        from nico.assessment_cpp_fuzz import build_steps
        for key, argv, needs in build_steps(config['bounded_fuzz']):
            add(key, argv, needs)
        add('fuzz-native-evidence', ['nico-controller:bounded-fuzz-v1'], ('fuzz-build',), fuzz_execution=True)
    return steps


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('worker_full_project_duplicate_member')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('worker_full_project_nonfinite')))


def compilation_contexts(raw, targets, build_dir, *, sanitizer=None, nested=True):
    """Capture every source-bound command, not permission or proof to execute it.

    Original and generated paths occupy different namespaces. Repeated original
    files retain distinct argument/output contexts. Generated hashes remain
    unknown until a separate immutable-byte capture; headers are not inferred
    from include flags. The executable compiler allowlist remains mandatory at
    replay time: this data-only inventory never replaces it.
    """
    from nico.assessment_cpp_generated_context import valid_build_directory
    from nico.assessment_worker_receipts import canonical_bytes
    if (not isinstance(raw, bytes) or not 0 < len(raw) <= 4 * 1024 * 1024
            or build_dir not in ('/work/build', '/work/address', '/work/undefined')
            or type(nested) is not bool or sanitizer not in (None, 'address', 'undefined')
            or not isinstance(targets, dict) or not 1 <= len(targets) <= 20000):
        raise ValueError('worker_full_project_context_input_invalid')
    for path, digest in targets.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path
                or any(p in {'', '.', '..', '.git'} for p in path.split('/'))
                or ':' in path or '\\' in path or any(ord(c) < 32 for c in path)
                or not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
            raise ValueError('worker_full_project_context_source_invalid')
    rows = _json(raw)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError('worker_full_project_database_invalid')
    contexts, originals, generated, identities = [], set(), set(), set()

    def output_path(value, directory):
        if not isinstance(value, str) or not value:
            raise ValueError('worker_full_project_context_output_invalid')
        if value.startswith('/'):
            if value == build_dir or not valid_build_directory(value, build_dir):
                raise ValueError('worker_full_project_context_output_invalid')
            return value
        if not _path(value):
            raise ValueError('worker_full_project_context_output_invalid')
        return directory + '/' + value

    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or not set(row) <= {'directory', 'file', 'arguments', 'command', 'output'}
                or not (valid_build_directory(row.get('directory'), build_dir)
                        if nested else row.get('directory') == build_dir)):
            raise ValueError('worker_full_project_database_invalid')
        path = row.get('file')
        if not isinstance(path, str):
            raise ValueError('worker_full_project_database_path_invalid')
        if path.startswith('/work/source/'):
            origin, relative = 'original', path[len('/work/source/'):]
            if relative not in targets:
                raise ValueError('worker_full_project_database_path_invalid')
            source_sha256 = targets[relative]
            originals.add(relative)
        elif path.startswith(build_dir + '/'):
            origin, relative = 'generated', path[len(build_dir) + 1:]
            source_sha256 = None
            generated.add(relative)
        else:
            raise ValueError('worker_full_project_database_path_invalid')
        if not _path(relative):
            raise ValueError('worker_full_project_database_path_invalid')
        argv = row.get('arguments')
        if 'arguments' in row and not isinstance(argv, list):
            raise ValueError('worker_full_project_database_command_invalid')
        if 'command' in row:
            if not isinstance(row['command'], str) or not row['command']:
                raise ValueError('worker_full_project_database_command_invalid')
            parsed = shlex.split(row['command'])
            if argv is not None and argv != parsed:
                raise ValueError('worker_full_project_context_command_ambiguous')
            argv = parsed if argv is None else argv
        if (not isinstance(argv, list) or not 1 <= len(argv) <= 4096
                or any(not isinstance(a, str) or not a or len(a) > 16384
                       or any(ord(c) < 32 for c in a) for a in argv)
                or argv[0] not in {'/usr/local/bin/gcc', '/usr/local/bin/g++'}
                or argv.count('-c') != 1 or argv.count(path) != 1 or argv.count('-o') != 1
                or argv.index('-c') + 1 >= len(argv) or argv[argv.index('-c') + 1] != path
                or argv.index('-o') + 1 >= len(argv)
                or (sanitizer and '-fsanitize=' + sanitizer not in argv)):
            raise ValueError('worker_full_project_database_command_invalid')
        output = output_path(argv[argv.index('-o') + 1], row['directory'])
        if 'output' in row:
            # CMake's optional output metadata may be build-root relative;
            # retain its literal value and bind it to the actual -o operand.
            options = {output_path(row['output'], row['directory']),
                       output_path(row['output'], build_dir)}
            if output not in options:
                raise ValueError('worker_full_project_context_output_mismatch')
        identity = {'origin': origin, 'path': relative, 'file': path,
            'source_sha256': source_sha256, 'directory': row['directory'],
            'arguments': list(argv), 'output': row.get('output'), 'output_path': output}
        # Literal output metadata is retained, but equivalent relative/absolute
        # spelling must not inflate the number of distinct semantic contexts.
        digest = hashlib.sha256(canonical_bytes({k: v for k, v in identity.items()
                                                if k != 'output'})).hexdigest()
        if digest in identities:
            raise ValueError('worker_full_project_context_duplicate')
        identities.add(digest)
        contexts.append({'index': index, 'context_id': digest, **identity})
    result = {'schema': 'nico.cpp-compilation-contexts.v1',
        'database_sha256': hashlib.sha256(raw).hexdigest(),
        'source_population_sha256': hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        'build_directory': build_dir, 'contexts': contexts, 'context_count': len(contexts),
        'context_membership_sha256': hashlib.sha256(canonical_bytes(sorted(identities))).hexdigest(),
        'original_units': sorted(originals), 'generated_units': sorted(generated),
        'generated_bytes_captured': False, 'analysis_executed': False,
        'header_dependencies_verified': False, 'execution_authorized': False}
    if len(canonical_bytes(result)) > 8 * 1024 * 1024:
        raise ValueError('worker_full_project_context_budget_exceeded')
    return result


def _database(raw, units, build_dir, sanitizer=None, *, nested=False, source_targets=None):
    """Inspect data only; legacy callers retain their original-only contract.

    Explicit source_targets selects versioned context inventory. It grants no
    static-analysis, generated-byte or execution proof to legacy consumers.
    """
    if source_targets is not None:
        result = compilation_contexts(raw, source_targets, build_dir,
                                      sanitizer=sanitizer, nested=nested)
        if units is not None and result['original_units'] != sorted(units):
            raise ValueError('worker_full_project_database_population_invalid')
        return result
    from nico.assessment_cpp_generated_context import valid_build_directory
    rows = _json(raw)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError('worker_full_project_database_invalid')
    observed = []
    for row in rows:
        if not isinstance(row, dict) or not (valid_build_directory(row.get('directory'), build_dir)
                if nested else row.get('directory') == build_dir):
            raise ValueError('worker_full_project_database_invalid')
        path = row.get('file', '')
        if not isinstance(path, str) or not path.startswith('/work/source/'):
            raise ValueError('worker_full_project_database_path_invalid')
        unit = path[len('/work/source/'):]
        if not _path(unit): raise ValueError('worker_full_project_database_path_invalid')
        argv = row.get('arguments')
        if argv is None and isinstance(row.get('command'), str): argv = shlex.split(row['command'])
        if (not isinstance(argv, list) or not argv or len(argv) > 4096
                or any(not isinstance(arg, str) for arg in argv)
                or argv[0] not in {'/usr/local/bin/gcc', '/usr/local/bin/g++'}
                or '-c' not in argv or path not in argv
                or (sanitizer and '-fsanitize=' + sanitizer not in argv)):
            raise ValueError('worker_full_project_database_command_invalid')
        observed.append(unit)
    if sorted(observed) != sorted(units):
        raise ValueError('worker_full_project_database_population_invalid')
    return observed


def _discovery(raw):
    value = _json(raw)
    if (not isinstance(value, dict) or value.get('kind') != 'ctestInfo'
            or value.get('version') != {'major': 1, 'minor': 0}
            or not isinstance(value.get('tests'), list) or len(value['tests']) > 20000):
        raise ValueError('worker_full_project_test_discovery_invalid')
    names = [row.get('name') for row in value['tests'] if isinstance(row, dict)]
    if len(names) != len(value['tests']) or not _names(sorted(names), empty=True):
        raise ValueError('worker_full_project_test_discovery_invalid')
    return sorted(names)


def _junit(raw, expected):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('worker_full_project_xml_invalid')
    root = ET.fromstring(raw)
    if root.tag != 'testsuite': raise ValueError('worker_full_project_xml_invalid')
    cases = list(root.findall('testcase'))
    names = [row.get('name') for row in cases]
    if sorted(names) != sorted(expected) or root.get('tests') != str(len(cases)):
        raise ValueError('worker_full_project_test_population_invalid')
    executed, passed, skipped = [], [], []
    for row in cases:
        name = row.get('name')
        if row.find('skipped') is not None or row.get('status') in {'notrun', 'disabled', 'skipped'}:
            skipped.append(name)
        else:
            executed.append(name)
            if row.find('failure') is None and row.find('error') is None and row.get('status', 'run') == 'run':
                passed.append(name)
    return sorted(executed), sorted(passed), sorted(skipped)


def validate_native(native, contract):
    """Never use a worker-supplied success/coverage/approval classification."""
    from nico.cppcheck_native_output import parse_native, NativeOutputRedactionRequired
    from nico.assessment_worker_jobs import _digest
    config = validate_configuration(contract['configuration'], contract['targets'])
    from nico.assessment_cpp_full_project_execution import boundary_valid
    fields = {'schema', 'steps', 'source_hashes', 'boundary', 'boundary_verified', 'memory_peak_bytes', 'cleanup_verified', 'error'}
    if (not isinstance(native, dict) or set(native) != fields
            or native['schema'] != 'nico.cpp-full-project-native.v1'
            or native['source_hashes'] != contract['targets']
            or type(native['boundary_verified']) is not bool or type(native['cleanup_verified']) is not bool
            or (native['memory_peak_bytes'] is not None and (type(native['memory_peak_bytes']) is not int
                or not 0 < native['memory_peak_bytes'] <= 2147483648))
            or (native['error'] is not None and (not isinstance(native['error'], str) or native['error'] not in {
                'worker_full_project_control_failed', 'worker_full_project_cleanup_failed'}))
            or not isinstance(native['steps'], list)):
        raise ValueError('worker_full_project_native_invalid')
    expected = execution_steps(contract)
    if len(native['steps']) != len(expected): raise ValueError('worker_full_project_steps_invalid')
    rows, raw, stages, success, duration = {}, {}, [], {}, 0
    row_fields = {'id', 'invocation', 'attempted', 'exit_code', 'timed_out', 'output_truncated',
                  'duration_ms', 'output', 'artifacts'}
    for row, spec in zip(native['steps'], expected):
        if (not isinstance(row, dict) or set(row) != row_fields or row['id'] != spec['id']
                or row['invocation'] != spec['invocation']
                or any(type(row[k]) is not bool for k in ('attempted', 'timed_out', 'output_truncated'))
                or type(row['duration_ms']) is not int or row['duration_ms'] < 0
                or (row['attempted'] and (type(row['exit_code']) is not int or not -255 <= row['exit_code'] <= 255))
                or (not row['attempted'] and (row['exit_code'] is not None or row['duration_ms']
                    or row['timed_out'] or row['output_truncated']))
                or not isinstance(row['artifacts'], dict)
                or not set(row['artifacts']) <= set(spec['artifacts'])):
            raise ValueError('worker_full_project_step_invalid')
        streams = {'output': decode_stream(row['output']),
                   **{key: decode_stream(value) for key, value in row['artifacts'].items()}}
        if not row['attempted'] and (any(streams.values()) or row['artifacts']):
            raise ValueError('worker_full_project_step_invalid')
        duration += row['duration_ms']
        if duration > contract['limits']['wall_seconds'] * 1000:
            raise ValueError('worker_full_project_duration_invalid')
        rows[row['id']], raw[row['id']] = row, streams
        okay = row['attempted'] and row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated']
        if row['id'] == 'cmake-version': okay &= streams['output'].splitlines()[:1] == [b'cmake version 3.31.6']
        if row['id'] == 'compiler-version': okay &= streams['output'].strip() == COMPILER_VERSION.encode()
        if row['id'] == 'fuzz-compiler-version': okay &= streams['output'].strip() == b'17.0.6'
        if row['id'] == 'analyzer-version': okay &= streams['output'].strip() == ('Cppcheck ' + contract['tool_version']).encode()
        okay &= all(success.get(key, False) for key in spec['needs'])
        success[row['id']] = bool(okay)
        status = ('not_attempted' if not row['attempted'] else 'timed_out' if row['timed_out']
            else 'failed' if row['exit_code'] != 0 else 'completed' if okay else 'partial')
        stages.append({'id': row['id'], 'status': status, 'attempted': row['attempted'],
            'exit_code': row['exit_code'], 'duration_ms': row['duration_ms'],
            **({'observation_kind': 'controller'} if 'native_test_configuration' in spec or spec.get('fuzz_execution') else {}),
            'artifact_sha256': {key: hashlib.sha256(data).hexdigest() for key, data in streams.items() if key != 'output'}})
    gaps, databases, discovered = [], {}, {}
    generated_contexts = {}
    if config.get('fuzz_base_schema', config.get('nested_base_schema', config.get('schema'))) == 'nico.cpp-cmake-configuration.v4':
        from nico.assessment_cpp_generated_context import validate_snapshot, validate_failure
        for group in ('baseline', *config['sanitizers']):
            key = group + '-generated-context'
            context = None
            if raw[key]['output'] and not rows[key]['output_truncated']:
                value = _json(raw[key]['output'])
                if isinstance(value, dict) and value.get('schema') == 'nico.cpp-generated-failure.v1':
                    validate_failure(value, group, 'snapshot')
                    if rows[key]['exit_code'] == 0:
                        raise ValueError('worker_generated_failure_exit_invalid')
                else:
                    context = validate_snapshot(value, group, config['generated_headers'], decoder=decode_stream)
            generated_contexts[group] = context if success[key] else None
            success[key] &= context is not None
            stage = next(s for s in stages if s['id'] == key)
            stage.update(captured_generated_headers=sorted(context['files']) if context else None,
                         captured_generated_bytes=context['captured_bytes'] if context else None)
            if stage['status'] == 'completed' and not success[key]: stage['status'] = 'partial'
            if not success[key]: gaps.append({'rule_id': 'generated_context_unverified', 'configuration': group})
    for group in ('baseline', *config['sanitizers']):
        key = group + '-configure'; directory = '/work/build' if group == 'baseline' else '/work/' + group
        try:
            if not success[key]: raise ValueError('configure_incomplete')
            _database(raw[key].get('compilation_database', b''), config['translation_units'], directory,
                      None if group == 'baseline' else group,
                      nested=config.get('cmake_layout') in ('nested-source-v1', 'nested-source-v2-gcc-options'))
            databases[group] = True
        except (ValueError, TypeError, UnicodeError):
            databases[group] = False
            gaps.append({'rule_id': 'compilation_database_unverified', 'configuration': group})
        try:
            if not success[group + '-discover']: raise ValueError('discovery_incomplete')
            discovered[group] = _discovery(raw[group + '-discover']['output'])
        except (ValueError, TypeError, UnicodeError):
            discovered[group] = None
        for kind in ('unit', 'integration'):
            key = group + '-' + kind
            stage = next(s for s in stages if s['id'] == key)
            names = config[kind + '_tests']
            executed = passed = skipped = None
            try:
                if not rows[key]['attempted']: raise ValueError('test_unattempted')
                if discovered[group] is None or not set(names) <= set(discovered[group]):
                    raise ValueError('test_not_discovered')
                executed, passed, skipped = _junit(raw[key].get('junit', b''), names)
            except (ValueError, TypeError, UnicodeError, ET.ParseError):
                pass
            success[key] &= bool(databases[group] and passed == names and skipped == [])
            stage.update(required_tests=names, executed_tests=executed, passed_tests=passed, skipped_tests=skipped)
            if stage['status'] == 'completed' and not success[key]: stage['status'] = 'partial'
    findings, limits, observed = [], [], []
    parsed = False
    try:
        findings, limits, observed = parse_native(raw['static-analysis'].get('analysis_xml', b'').decode('utf-8'),
            raw['static-analysis']['output'].decode('utf-8'), sorted(contract['targets']),
            version=contract['tool_version'], source_prefix='/work/source/')
        parsed = True
    except NativeOutputRedactionRequired:
        raise ValueError('worker_native_redaction_required') from None
    except (ValueError, TypeError, UnicodeError, ET.ParseError):
        limits = [{'rule_id': 'native_output_invalid', 'message': 'Native XML was not completely parsed.'}]
    stable = (native['boundary_verified'] and boundary_valid(native['boundary']) and native['cleanup_verified'] and native['error'] is None
              and native['memory_peak_bytes'] is not None)
    units = config['translation_units']
    analysis_input_frozen = (bool(raw['static-analysis'].get('compilation_database')) and
        raw['static-analysis'].get('compilation_database') == raw['baseline-configure'].get('compilation_database'))
    if generated_contexts:
        from nico.assessment_cpp_generated_context import configured_database_parser
        derive = configured_database_parser(config)
        try:
            expected_database = derive(raw['baseline-configure'].get('compilation_database', b''),
                units, 'baseline', config['generated_headers'])
            analysis_input_frozen = bool(generated_contexts.get('baseline') and
                raw['static-analysis'].get('compilation_database') == expected_database)
        except (ValueError, TypeError, UnicodeError):
            analysis_input_frozen = False
    static_complete = (stable and analysis_input_frozen and databases['baseline'] and success['static-analysis'] and parsed
        and observed == units and not any(item['rule_id'] != 'checkersReport' for item in limits))
    build_complete = bool(stable and databases['baseline'] and success['baseline-build'])
    compiler_evidence = {}
    if config.get('compiler_evidence'):
        from nico.assessment_cpp_compiler_evidence import validate_compiler_evidence
        for group in ('baseline', *config['sanitizers']):
            key = group + '-compiler-evidence'
            stage = next(s for s in stages if s['id'] == key)
            # A malformed nested base64 payload is not a redacted retained receipt.
            # Validate even failure output before deciding whether it grants coverage.
            verified_compiler = None
            if raw[key]['output'] and not rows[key]['output_truncated']:
                if generated_contexts:
                    from nico.assessment_cpp_generated_context import validate_generated_compiler
                    verified_compiler = validate_generated_compiler(raw[key]['output'],
                        raw[group + '-configure'].get('compilation_database', b''),
                        raw[group + '-generated-context']['output'], contract, group)
                else:
                    verified_compiler = validate_compiler_evidence(raw[key]['output'],
                        raw[group + '-configure'].get('compilation_database', b''), contract, group)
            if stable and success[key] and databases[group] and verified_compiler is not None:
                compiler_evidence[group] = verified_compiler
                success[key] &= verified_compiler['complete']
            else:
                compiler_evidence[group] = None
                success[key] = False
            if stage['status'] == 'completed' and not success[key]:
                stage['status'] = 'partial'
    native_test_evidence = {}
    if config.get('native_test_evidence') == 'bound-binary-replay-v1':
        from nico.assessment_cpp_native_tests import validate_evidence, ORIGINAL_CTEST_LIMIT
        for group in config['sanitizers']:
            key = group + '-native-test-evidence'
            stage = next(s for s in stages if s['id'] == key)
            proof = None
            if raw[key]['output'] and not rows[key]['output_truncated']:
                proof = validate_evidence(_json(raw[key]['output']), raw[group + '-discover']['output'], config, group,
                    enclosing_duration_ms=rows[key]['duration_ms'])
            if stable and success[key] and proof is not None:
                native_test_evidence[group] = proof
                success[key] &= proof['tests_passed']
                stage.update(required_tests=proof['required_tests'], executed_tests=proof['executed_tests'],
                    passed_tests=proof['passed_tests'], binary_bound_tests=proof['binary_bound_tests'])
                if not proof['binary_instrumentation_verified']: stage['status'] = 'partial'
            else:
                native_test_evidence[group] = None
                success[key] = False
                if stage['status'] == 'completed': stage['status'] = 'partial'
    baseline_compiler = compiler_evidence.get('baseline')
    if generated_contexts:
        # A derived include configuration is not qualified when compiler dependency
        # receipts still visit a mutable or otherwise unbound header population.
        static_complete &= bool(baseline_compiler and baseline_compiler['complete'])
    headers = sorted(p for p in contract['targets'] if PurePosixPath(p).suffix.lower() in {'.h', '.hh', '.hpp', '.hxx', '.inc'})
    header_verified = bool(baseline_compiler and baseline_compiler['complete']
        and set(headers) <= set(baseline_compiler['header_inclusions']))
    fuzz_evidence = None
    if config.get('bounded_fuzz') is not None:
        from nico.assessment_cpp_fuzz import validate_evidence, LIMITATION
        key = 'fuzz-native-evidence'
        if rows[key]['attempted'] and raw[key]['output'] and not rows[key]['output_truncated']:
            fuzz_evidence = validate_evidence(_json(raw[key]['output']), config['bounded_fuzz'], contract['targets'])
        if fuzz_evidence is not None:
            if fuzz_evidence['duration_ms'] > rows[key]['duration_ms'] + 2:
                raise ValueError('worker_fuzz_duration_contradiction')
            fuzz_evidence['execution_chain_verified'] = bool(stable and success['fuzz-build'])
            fuzz_evidence['complete'] &= fuzz_evidence['execution_chain_verified']
        success[key] &= bool(stable and fuzz_evidence and fuzz_evidence['complete'])
        stage = next(s for s in stages if s['id'] == key)
        stage.update(required_fuzz_targets=[t['name'] for t in config['bounded_fuzz']['targets']],
            executed_fuzz_targets=fuzz_evidence['executed_targets'] if fuzz_evidence else [],
            completed_fuzz_targets=fuzz_evidence['completed_targets'] if fuzz_evidence else [])
        if stage['status'] == 'completed' and not success[key]: stage['status'] = 'partial'
    requested_complete = bool(static_complete and all(success.values()) and all(databases.values()))
    static = rows['static-analysis']
    status = ('completed' if static_complete else 'timed_out' if static['timed_out'] else
              'failed' if static['attempted'] and static['exit_code'] != 0 else 'partial')
    for finding in findings:
        # Whole-project analysis does not identify a particular TU for a header diagnostic.
        finding.update(translation_unit=None, unit_configuration_sha256=_digest(config))
    return {'complete': bool(static_complete), 'status': status, 'findings': findings,
        'duration_ms': duration, 'output_truncated': any(r['output_truncated'] for r in rows.values()),
        'coverage': {'requested_targets': units, 'requested_target_count': len(units),
            'observed_targets': observed, 'observed_target_count': len(observed),
            'unobserved_targets': sorted(set(units) - set(observed)), 'limitations': [*gaps, *limits],
            'population_sha256': _digest(units), 'configuration_aware': bool(static_complete),
            'header_context_verified': header_verified, 'repository_build_executed': build_complete,
            **({'required_source_headers': headers, 'compiler_header_inclusions': baseline_compiler['header_inclusions']
                if baseline_compiler else {}, 'header_coverage_basis': 'direct compiler dependency files; immutable original headers only'}
               if config.get('compiler_evidence') else {}),
            'all_repository_configurations_analyzed': False},
        'build': {'profile': PROFILE, 'required_translation_units': units,
            'compiled_translation_units': baseline_compiler['compiled_translation_units'] if baseline_compiler else None,
            **({'compiler_evidence': compiler_evidence} if config.get('compiler_evidence') else {}),
            **({'generated_context': {group: {
                'captured_header_hashes': {p: item['sha256'] for p, item in value['files'].items()},
                'captured_bytes': value['captured_bytes'],
                'capture_sha256': hashlib.sha256(raw[group + '-generated-context']['output']).hexdigest(),
                'origin': 'assessed build output; not immutable Git source'} if value else None
                for group, value in generated_contexts.items()}} if generated_contexts else {}),
            'build_completed': build_complete,
            'compilation_database_translation_units': units if databases['baseline'] else [],
            'project_build_system_executed': rows['baseline-configure']['attempted'],
            'implemented_command_scope_complete': requested_complete,
            'requested_scope_complete': False, 'stages': stages,
            'discovered_tests': discovered,
            **({'native_test_binary_evidence': native_test_evidence} if config.get('native_test_evidence') == 'bound-binary-replay-v1' else {}),
            'sanitizers': {s: {
                'instrumentation_verified': False,
                **({'isolated_binary_replay_verified': bool(native_test_evidence.get(s) and native_test_evidence[s]['binary_instrumentation_verified'])} if config.get('native_test_evidence') == 'bound-binary-replay-v1' else {}),
                'instrumentation_configuration_verified': databases[s],
                'executed': bool(stable and databases[s] and all(
                    next(r for r in stages if r['id'] == s + '-' + kind).get('executed_tests')
                    == config[kind + '_tests'] for kind in ('unit', 'integration'))),
                'passed': bool(stable and databases[s] and success[s + '-unit'] and success[s + '-integration'])}
                for s in config['sanitizers']},
            'sanitizers_executed': bool(stable and all(databases[s] and all(
                next(r for r in stages if r['id'] == s + '-' + kind).get('executed_tests')
                == config[kind + '_tests'] for kind in ('unit', 'integration')) for s in config['sanitizers'])),
            'compilation_database_sha256': hashlib.sha256(raw['baseline-configure'].get('compilation_database', b'')).hexdigest(),
            'memory_peak_bytes': native['memory_peak_bytes'], 'resource_class': 'full-project-v1',
            'cleanup_verified': native['cleanup_verified'], 'controller_error': native['error'],
            'analysis_artifact_isolation_verified': bool(stable and analysis_input_frozen),
            'source_read_only_verified': bool(stable),
            'fuzz_executed': bool(stable and fuzz_evidence and fuzz_evidence['executed_targets']),
            **({'bounded_fuzz_evidence': fuzz_evidence} if config.get('bounded_fuzz') is not None else {}),
            'full_project_qualified': False,
            'limitations': [*([] if header_verified else ['Header inclusion coverage has not been established.']),
                'Compilation database membership is not measured compiler execution coverage.',
                ORIGINAL_CTEST_LIMIT if config.get('native_test_evidence') == 'bound-binary-replay-v1' else 'Sanitizer flags are verified in configuration; independent binary instrumentation is not established.',
                'Dependencies must be present in the pinned image or captured source; no runtime downloads.',
                LIMITATION if config.get('bounded_fuzz') is not None else 'Bounded libFuzzer execution is not implemented by this profile revision.',
                'Build/test/sanitizer evidence is not an independent security finding or human approval.']}}
