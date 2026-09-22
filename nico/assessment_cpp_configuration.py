"""Typed source-bound compiler configuration, never repository command strings.

Versioned configured profiles build and run one native test executable.
They do not discover project build systems or enable production selection.
Required units and headers cannot be dropped. The runtime-cases profile adds
frozen named unit/integration steps and bounded source-bound corpus replay.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re

PROFILE = 'cpp-configured-v1'
SANITIZED_PROFILE = 'cpp-sanitized-v1'
RUNTIME_PROFILE = 'cpp-runtime-cases-v1'
CONFIGURED_PROFILES = {PROFILE, SANITIZED_PROFILE, RUNTIME_PROFILE}
COMPILER_VERSION = '14.2.0'
CHECKS = 'warning,style,performance,portability,information'
MAX_CORPUS_BYTES = 4096
RUNTIME_KINDS = {'unit', 'integration', 'corpus'}


def _path(value):
    return (isinstance(value, str) and len(value) <= 500
        and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', value)
        and all(part not in {'', '.', '..', '.git'} for part in value.split('/')))


def _validate_runtime_cases(cases, unit_paths, headers):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 16:
        raise ValueError('worker_runtime_cases_invalid')
    reserved = {'test', 'link'}
    seen, kinds, corpus = [], set(), []
    for case in cases:
        if (not isinstance(case, dict)
                or set(case) != {'id', 'kind', 'argv', 'stdin_target', 'expected_exit'}
                or not isinstance(case['id'], str)
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', case['id'])
                or case['id'] in reserved or case['id'].startswith(('compile-', 'analyze-'))
                or case['kind'] not in RUNTIME_KINDS
                or not isinstance(case['argv'], list) or not 1 <= len(case['argv']) <= 8
                or any(not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_./=-]{1,64}', token)
                       for token in case['argv'])
                or type(case['expected_exit']) is not int or not 0 <= case['expected_exit'] <= 255):
            raise ValueError('worker_runtime_case_invalid')
        if case['kind'] == 'corpus':
            if (not isinstance(case['stdin_target'], str) or not _path(case['stdin_target'])
                    or case['stdin_target'] in unit_paths or case['stdin_target'] in headers):
                raise ValueError('worker_runtime_corpus_unbound')
            corpus.append(case['stdin_target'])
        elif case['stdin_target'] is not None:
            raise ValueError('worker_runtime_case_invalid')
        seen.append(case['id'])
        kinds.add(case['kind'])
    if len(seen) != len(set(seen)):
        raise ValueError('worker_runtime_case_duplicate')
    if kinds != RUNTIME_KINDS:
        raise ValueError('worker_runtime_population_invalid')
    if not corpus or len(corpus) != len(set(corpus)):
        raise ValueError('worker_runtime_corpus_unbound')
    return corpus


def validate_configuration(configuration, targets, *, sanitized=False, runtime=False):
    fields = {'platform', 'compiler_version', 'translation_units', 'headers'}
    if sanitized:
        fields.add('sanitizer')
    if runtime:
        fields.add('runtime_cases')
    if (sanitized and runtime
            or not isinstance(configuration, dict)
            or set(configuration) != fields
            or configuration['platform'] != 'unix64'
            or configuration['compiler_version'] != COMPILER_VERSION):
        raise ValueError('worker_configuration_invalid')
    if sanitized and (not isinstance(configuration['sanitizer'], str)
                      or configuration['sanitizer'] not in {'address', 'undefined'}):
        raise ValueError('worker_sanitizer_configuration_invalid')
    units, headers = configuration['translation_units'], configuration['headers']
    if (not isinstance(units, list) or not 1 <= len(units) <= 64
            or not isinstance(headers, list) or len(headers) > 256
            or any(not _path(path) for path in headers) or headers != sorted(set(headers))):
        raise ValueError('worker_configuration_population_invalid')
    paths = []
    for unit in units:
        if (not isinstance(unit, dict)
                or set(unit) != {'path', 'language', 'standard', 'defines', 'include_dirs'}
                or not _path(unit['path'])
                or not isinstance(unit['language'], str) or not isinstance(unit['standard'], str)
                or (unit['language'], unit['standard']) not in {('c', 'c11'), ('c++', 'c++20')}
                or not isinstance(unit['defines'], dict) or len(unit['defines']) > 64
                or any(not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', key)
                    or not isinstance(value, str) or not re.fullmatch(r'-?[0-9]{1,10}', value)
                    for key, value in unit['defines'].items())
                or not isinstance(unit['include_dirs'], list) or len(unit['include_dirs']) > 64
                or any(not _path(path) or not any(p.startswith(path + '/') for p in targets)
                       for path in unit['include_dirs'])
                or len(unit['include_dirs']) != len(set(unit['include_dirs']))):
            raise ValueError('worker_translation_unit_invalid')
        paths.append(unit['path'])
    extra = set(_validate_runtime_cases(configuration['runtime_cases'], paths, headers) if runtime else [])
    if (len(paths) != len(set(paths)) or set(paths) & set(headers)
            or extra & set(paths) or extra & set(headers)
            or set(targets) != set(paths) | set(headers) | extra):
        raise ValueError('worker_configuration_input_mismatch')


def instrumentation(configuration):
    """Fixed, source-bound instrumentation; callers cannot supply environment/options."""
    kind = configuration.get('sanitizer')
    if kind is None:
        return None
    if kind not in {'address', 'undefined'}:
        raise ValueError('worker_sanitizer_configuration_invalid')
    common = ['-fsanitize=' + kind, '-fno-sanitize-recover=all']
    runtime = ({'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=86:'
                'quarantine_size_mb=16:thread_local_quarantine_size_kb=64:malloc_context_size=12:'
                'detect_stack_use_after_return=0:allow_addr2line=1'} if kind == 'address' else
               {'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=0:exitcode=87'})
    return {'kind': kind, 'compile_options': common + ['-g1', '-fno-omit-frame-pointer'],
            'link_options': common, 'runtime_options': runtime,
            'excluded_checks': ['leaks', 'stack_use_after_return'] if kind == 'address' else [],
            'instrumented_coverage_measured': False}


def commands(configuration):
    """One compiler invocation and one analyzer invocation per frozen unit."""
    result = []
    instrument = instrumentation(configuration)
    for index, unit in enumerate(configuration['translation_units']):
        prefix = '/work/unit-' + str(index)
        compiler = 'gcc' if unit['language'] == 'c' else 'g++'
        argv = [compiler, '-x', unit['language'], '-std=' + unit['standard'], '-O0', '-g0']
        if instrument:
            argv += instrument['compile_options']
        argv += ['-D' + key + '=' + value for key, value in sorted(unit['defines'].items())]
        argv += ['-I./' + directory for directory in unit['include_dirs']]
        argv += ['-MMD', '-MF', prefix + '.d', '-MT', 'unit-' + str(index),
                 '-c', './' + unit['path'], '-o', prefix + '.o']
        result.append({'id': 'compile-' + str(index), 'invocation': argv, 'artifact': prefix + '.d'})
        result.append({'id': 'analyze-' + str(index), 'invocation': ['cppcheck', '--xml',
            '--enable=' + CHECKS, '--check-level=normal', '--max-configs=1', '--platform=unix64',
            '-j1', '--project=' + prefix + '.json', '--output-file=' + prefix + '.xml'],
            'artifact': prefix + '.xml'})
    result.append({'id': 'link', 'invocation': ['g++'] +
        ['/work/unit-' + str(index) + '.o' for index in range(len(configuration['translation_units']))]
        + (instrument['link_options'] if instrument else [])
        + ['-o', '/work/native-test'], 'artifact': None})
    return result


def native_steps(configuration):
    """Compile/analyze/link, the default native test, then frozen named runtime cases."""
    steps = commands(configuration) + [{'id': 'test', 'invocation': ['/work/source/native-test'], 'artifact': None}]
    for case in configuration.get('runtime_cases') or []:
        steps.append({'id': case['id'], 'invocation': ['/work/source/native-test', *case['argv']], 'artifact': None})
    return steps


def compilation_database(configuration):
    return [{'directory': '/work/source', 'file': './' + unit['path'],
             'arguments': command['invocation']}
            for unit, command in zip(configuration['translation_units'], commands(configuration)[::2])]


def database_bytes(configuration):
    return json.dumps(compilation_database(configuration), sort_keys=True, separators=(',', ':')).encode()


def dependencies(raw, *, unit, targets, index):
    """GCC -MMD output under the profile's whitespace-free relative paths."""
    text = raw.decode('utf-8').replace('\\\n', ' ')
    prefix, separator, value = text.partition(':')
    if not separator or prefix != 'unit-' + str(index):
        raise ValueError('worker_dependency_record_invalid')
    paths = {path.removeprefix('./') for path in value.split()}
    if unit not in paths or not paths <= set(targets):
        raise ValueError('worker_dependency_population_invalid')
    return sorted(paths)


def decode_stream(value):
    from nico.scanner_tool_runners import redact_text
    import html
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ValueError('worker_native_encoding_invalid') from None
    text = raw.decode('utf-8', errors='replace')
    if redact_text(text) != text or redact_text(html.unescape(text)) != html.unescape(text):
        raise ValueError('worker_native_redaction_required')
    return raw


def validate_native(native, contract):
    """Reconstruct commands and populations independently of worker success flags."""
    from nico.cppcheck_native_output import parse_native, NativeOutputRedactionRequired
    from nico.assessment_worker_jobs import _digest
    from xml.etree.ElementTree import ParseError
    config = contract['configuration']
    instrument = instrumentation(config)
    native_fields = {'steps', 'compilation_database', 'tool_versions', 'binary_sha256'}
    if instrument:
        native_fields.add('instrumentation')
    if (not isinstance(native, dict) or set(native) != native_fields
            or (instrument and native['instrumentation'] != instrument)
            or native['tool_versions'] != {'gcc': COMPILER_VERSION, 'g++': COMPILER_VERSION, 'cppcheck': contract['tool_version']}
            or decode_stream(native['compilation_database']) != database_bytes(config)
            or not isinstance(native['steps'], list)):
        raise ValueError('worker_configured_native_invalid')
    expected = native_steps(config)
    if len(native['steps']) != len(expected):
        raise ValueError('worker_configured_step_population_invalid')
    steps = {}
    raw_steps = {}
    duration = 0
    for actual, required in zip(native['steps'], expected):
        if (not isinstance(actual, dict) or set(actual) != {'id', 'invocation', 'attempted', 'exit_code',
                'timed_out', 'output_truncated', 'duration_ms', 'stdout', 'stderr', 'artifact'}
                or actual['id'] != required['id'] or actual['invocation'] != required['invocation']
                or any(type(actual[key]) is not bool for key in ('attempted', 'timed_out', 'output_truncated'))
                or type(actual['duration_ms']) is not int or actual['duration_ms'] < 0
                or (actual['attempted'] and (type(actual['exit_code']) is not int or not -255 <= actual['exit_code'] <= 255))
                or (not actual['attempted'] and (actual['exit_code'] is not None or actual['duration_ms']
                    or actual['timed_out'] or actual['output_truncated']))):
            raise ValueError('worker_configured_step_invalid')
        raw = {key: decode_stream(actual[key]) for key in ('stdout', 'stderr', 'artifact')}
        if ((not actual['attempted'] and any(raw.values()))
                or (required['artifact'] is None and raw['artifact'])):
            raise ValueError('worker_configured_step_invalid')
        duration += actual['duration_ms']
        if duration > contract['limits']['wall_seconds'] * 1000:
            raise ValueError('worker_configured_duration_invalid')
        steps[actual['id']] = actual
        raw_steps[actual['id']] = raw
    def succeeded(key):
        row = steps[key]
        return row['attempted'] and row['exit_code'] == 0 and not row['timed_out'] and not row['output_truncated']
    findings, limitations, analyzed, compiled, headers = [], [], [], [], []
    for index, unit in enumerate(config['translation_units']):
        compile_id, analyze_id = 'compile-' + str(index), 'analyze-' + str(index)
        unit_sha = _digest(unit)
        if succeeded(compile_id):
            try:
                population = dependencies(raw_steps[compile_id]['artifact'], unit=unit['path'],
                    targets=contract['targets'], index=index)
                compiled.append(unit['path'])
                headers += [{'path': path, 'translation_unit': unit['path'], 'language': unit['language'],
                             'configuration_sha256': unit_sha} for path in population if path in config['headers']]
            except (ValueError, UnicodeError):
                limitations.append({'rule_id': 'header_dependencies_invalid', 'path': unit['path']})
        if steps[analyze_id]['attempted']:
            raw = raw_steps[analyze_id]
            try:
                rows, gaps, observed = parse_native(raw['artifact'].decode('utf-8'),
                    (raw['stdout'] + raw['stderr']).decode('utf-8'), sorted(contract['targets']),
                    version=contract['tool_version'], source_prefix='/work/source/')
                for row in rows:
                    row.update(translation_unit=unit['path'], unit_configuration_sha256=unit_sha)
                findings += rows
                limitations += gaps
                if succeeded(analyze_id) and observed == [unit['path']] and not any(g['rule_id'] != 'checkersReport' for g in gaps):
                    analyzed.append(unit['path'])
            except NativeOutputRedactionRequired:
                raise ValueError('worker_native_redaction_required') from None
            except (ValueError, ParseError, UnicodeError):
                limitations.append({'rule_id': 'native_output_invalid', 'path': unit['path']})
    binary_valid = isinstance(native['binary_sha256'], str) and bool(re.fullmatch(r'[0-9a-f]{64}', native['binary_sha256']))
    if not isinstance(native['binary_sha256'], str) or (native['binary_sha256'] and not binary_valid):
        raise ValueError('worker_configured_binary_invalid')
    required_paths = [unit['path'] for unit in config['translation_units']]
    header_paths = sorted({row['path'] for row in headers})
    build_complete = compiled == required_paths and succeeded('link') and binary_valid
    test_complete = build_complete and succeeded('test')
    sanitizer = None
    if instrument:
        runtime_output = (raw_steps['test']['stdout'] + raw_steps['test']['stderr']).decode('utf-8', errors='replace')
        # Program output is untrusted. These are reported diagnostic patterns,
        # never independently verified findings or proof of entry after failure.
        reported = (bool(re.search(r'ERROR: AddressSanitizer: [a-z][a-z-]+', runtime_output))
                    if instrument['kind'] == 'address' else
                    bool(re.search(r':\d+:\d+: runtime error: ', runtime_output)))
        test = steps['test']
        exit_expected = 86 if instrument['kind'] == 'address' else 87
        outcome = ('not_attempted' if not test['attempted'] else
                   'timed_out' if test['timed_out'] else
                   'output_truncated' if test['output_truncated'] else
                   'diagnostic_reported' if build_complete and reported and test['exit_code'] == exit_expected else
                   'clean' if test_complete and not reported else 'execution_failed')
        sanitizer = {**instrument, 'required': 1, 'attempted': int(test['attempted']),
                     'executed': 1 if succeeded('test') else None if test['attempted'] else 0,
                     'outcome': outcome, 'diagnostic_reported': reported,
                     'diagnostic_origin': 'untrusted_native_program_output',
                     'independently_verified_finding': False}
        test_complete = test_complete and outcome == 'clean'
    runtime = None
    cases = list(config.get('runtime_cases') or [])
    case_exit = {case['id']: case['expected_exit'] for case in cases}
    runtime_ok = True
    if cases:
        by_kind = {kind: {'required': 0, 'passed': 0} for kind in ('unit', 'integration', 'corpus')}
        rows, passed, attempted, uncertain = [], 0, 0, False
        for case in cases:
            row = steps[case['id']]
            by_kind[case['kind']]['required'] += 1
            matched = (row['attempted'] and row['exit_code'] == case['expected_exit']
                       and not row['timed_out'] and not row['output_truncated'])
            if row['attempted']:
                attempted += 1
            if matched:
                passed += 1
                by_kind[case['kind']]['passed'] += 1
            else:
                uncertain = True
            rows.append({'id': case['id'], 'kind': case['kind'], 'expected_exit': case['expected_exit'],
                         'matched': matched, 'stdin_target': case['stdin_target'],
                         'original_output_retained': row['attempted'] and not row['output_truncated'],
                         'independently_verified_finding': False})
        corpus_targets = [case['stdin_target'] for case in cases if case['kind'] == 'corpus']
        corpus_assurance = bool(corpus_targets) and all(
            steps[case['id']]['attempted'] and not steps[case['id']]['timed_out']
            and not steps[case['id']]['output_truncated']
            for case in cases if case['kind'] == 'corpus')
        runtime = {'required': len(cases), 'attempted': attempted,
                   'executed': passed if attempted == len(cases) and not uncertain else None if attempted else 0,
                   'passed': passed, 'by_kind': by_kind, 'cases': rows, 'corpus_seeds': corpus_targets,
                   'corpus_replayed': corpus_assurance, 'corpus_assurance': corpus_assurance,
                   'diagnostic_origin': 'untrusted_native_program_output'}
        runtime_ok = passed == len(cases) and corpus_assurance
    complete = (test_complete and runtime_ok and analyzed == required_paths and header_paths == config['headers']
                and not any(row['rule_id'] != 'checkersReport' for row in limitations))
    status = ('completed' if complete else 'timed_out' if any(row['timed_out'] for row in steps.values())
              else 'failed' if any(row['attempted'] and row['exit_code'] != case_exit.get(row['id'], 0)
                                   for row in steps.values()) else 'partial')
    return {'status': status, 'complete': complete, 'findings': findings, 'duration_ms': duration,
        'coverage': {'requested_targets': required_paths, 'requested_target_count': len(required_paths),
            'observed_targets': analyzed, 'observed_target_count': len(analyzed),
            'unobserved_targets': sorted(set(required_paths) - set(analyzed)), 'limitations': limitations,
            'population_sha256': _digest(config['translation_units']), 'configuration_aware': analyzed == required_paths,
            'header_context_verified': header_paths == config['headers'] and compiled == required_paths,
            'repository_build_executed': build_complete, 'all_repository_configurations_analyzed': False,
            'required_headers': config['headers'], 'observed_headers': header_paths, 'header_contexts': headers},
        'build': {'required_translation_units': required_paths, 'compiled_translation_units': compiled,
            'build_completed': build_complete, 'native_test': {'required': 1,
            'attempted': int(steps['test']['attempted']),
            'executed': 1 if succeeded('test') else None if steps['test']['attempted'] else 0,
            'passed': int(test_complete)},
            'binary_sha256': native['binary_sha256'],
            'compilation_database_sha256': hashlib.sha256(database_bytes(config)).hexdigest(),
            'sanitizers_executed': (bool(sanitizer['executed']) if sanitizer['executed'] is not None else None)
                if sanitizer else False,
            **({'sanitizer': sanitizer} if sanitizer else {}),
            **({'runtime_cases': runtime} if runtime else {}),
            'fuzz_executed': False, 'project_build_system_executed': False},
        'output_truncated': any(row['output_truncated'] for row in steps.values())}
