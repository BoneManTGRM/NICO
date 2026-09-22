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


def configuration(*, units, unit_tests, integration_tests):
    """Create a bounded configuration, not an authorization/qualification flag."""
    return {'schema': 'nico.cpp-cmake-configuration.v1', 'platform': 'linux/amd64',
        'cmake_version': CMAKE_VERSION, 'compiler_version': COMPILER_VERSION,
        'translation_units': sorted(units), 'unit_tests': sorted(unit_tests),
        'integration_tests': sorted(integration_tests), 'project_options': {},
        'build_targets': [], 'parallel': 1, 'source_byte_limit': MAX_SOURCE_BYTES,
        'sanitizers': ['address', 'undefined']}


def _path(value):
    return (isinstance(value, str) and len(value) <= 500
        and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*', value)
        and all(p not in {'', '.', '..', '.git'} for p in value.split('/')))


def _names(values, *, empty=False):
    return (isinstance(values, list) and (empty or bool(values)) and len(values) <= 4096
        and all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./:+-]{0,199}', x) for x in values)
        and values == sorted(set(values)))


def validate_configuration(config, targets):
    fields = {'schema', 'platform', 'cmake_version', 'compiler_version', 'translation_units',
        'unit_tests', 'integration_tests', 'project_options', 'build_targets', 'parallel',
        'source_byte_limit', 'sanitizers'}
    if (not isinstance(config, dict) or set(config) != fields
            or config['schema'] != 'nico.cpp-cmake-configuration.v1'
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
    return deepcopy(config)


def execution_steps(contract):
    config = contract['configuration']
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
        if group == 'baseline':
            add('static-analysis', ['cppcheck', '--xml', '--enable=' + CHECKS,
                '--check-level=normal', '--max-configs=1', '--platform=unix64', '-j1',
                '--project=/work/build/compile_commands.json', '--output-file=/work/analysis.xml'],
                ('baseline-build', 'analyzer-version'), {'analysis_xml': '/work/analysis.xml'})
        add(group + '-discover', ['ctest', '--test-dir', directory, '--show-only=json-v1'], (group + '-build',))
        for kind in ('unit', 'integration'):
            names = config[kind + '_tests']
            pattern = '^(' + '|'.join(re.escape(name) for name in names) + ')$'
            output = '/work/' + group + '-' + kind + '.xml'
            add(group + '-' + kind, ['ctest', '--test-dir', directory, '--no-tests=error',
                '--output-on-failure', '--parallel', '1', '--timeout', '30', '-R', pattern,
                '--output-junit', output], (group + '-discover',), {'junit': output}, tests=names)
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


def _database(raw, units, build_dir, sanitizer=None):
    """Inspect data only; never execute commands from compilation databases."""
    rows = _json(raw)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError('worker_full_project_database_invalid')
    observed = []
    for row in rows:
        if not isinstance(row, dict) or row.get('directory') != build_dir:
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
            or native['error'] not in {None, 'worker_full_project_control_failed', 'worker_full_project_cleanup_failed'}
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
        if row['id'] == 'analyzer-version': okay &= streams['output'].strip() == ('Cppcheck ' + contract['tool_version']).encode()
        okay &= all(success.get(key, False) for key in spec['needs'])
        success[row['id']] = bool(okay)
        status = ('not_attempted' if not row['attempted'] else 'timed_out' if row['timed_out']
            else 'failed' if row['exit_code'] != 0 else 'completed' if okay else 'partial')
        stages.append({'id': row['id'], 'status': status, 'attempted': row['attempted'],
            'exit_code': row['exit_code'], 'duration_ms': row['duration_ms'],
            'artifact_sha256': {key: hashlib.sha256(data).hexdigest() for key, data in streams.items() if key != 'output'}})
    gaps, databases, discovered = [], {}, {}
    for group in ('baseline', *config['sanitizers']):
        key = group + '-configure'; directory = '/work/build' if group == 'baseline' else '/work/' + group
        try:
            if not success[key]: raise ValueError('configure_incomplete')
            _database(raw[key].get('compilation_database', b''), config['translation_units'], directory,
                      None if group == 'baseline' else group)
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
    static_complete = (stable and databases['baseline'] and success['static-analysis'] and parsed
        and observed == units and not any(item['rule_id'] != 'checkersReport' for item in limits))
    build_complete = bool(stable and databases['baseline'] and success['baseline-build'])
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
            'header_context_verified': False, 'repository_build_executed': build_complete,
            'all_repository_configurations_analyzed': False},
        'build': {'profile': PROFILE, 'required_translation_units': units,
            'compiled_translation_units': None, 'build_completed': build_complete,
            'compilation_database_translation_units': units if databases['baseline'] else [],
            'project_build_system_executed': rows['baseline-configure']['attempted'],
            'implemented_command_scope_complete': requested_complete,
            'requested_scope_complete': False, 'stages': stages,
            'discovered_tests': discovered, 'sanitizers': {s: {
                'instrumentation_verified': False,
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
            'source_read_only_verified': bool(stable), 'fuzz_executed': False,
            'full_project_qualified': False,
            'limitations': ['Header inclusion coverage has not been established.',
                'Compilation database membership is not measured compiler execution coverage.',
                'Sanitizer flags are verified in configuration; independent binary instrumentation is not established.',
                'Dependencies must be present in the pinned image or captured source; no runtime downloads.',
                'Bounded libFuzzer execution is not implemented by this profile revision.',
                'Build/test/sanitizer evidence is not an independent security finding or human approval.']}}
