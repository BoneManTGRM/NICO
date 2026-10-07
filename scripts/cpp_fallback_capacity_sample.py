"""Four-context diagnostic seam, never full fallback qualification.

Host calls the existing verified preparation and exact request constructors.
This module only binds/selects their results and preserves the original
generated collector definitions. Root owns image/target/host lifecycle.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import time

SELECTED_INDICES = (0, 58, 154, 186)
LIMITS = {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
MAX_REQUEST = 8 * 1024 * 1024
MAX_EVIDENCE = 32 * 1024 * 1024
MAX_TELEMETRY = 128 * 1024
SIDECAR = '/work/analysis/capacity-sample-telemetry.json'
SOURCE_PINS = {
    'nico/assessment_cpp_clang_fallback.py': '3ab2c2b9c1a4c3bd20f0d6af34655a6b53e2f02ebd490554f0b189929fedd7db',
    'nico/assessment_cpp_project_compiler.py': '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8',
    'nico/assessment_cpp_compiler_evidence.py': 'bc26c3bb86c0673793c118f969234ece3bc4939325af3703b2da69259eb4a242',
    'nico/assessment_cpp_generated_context.py': '5ad9e587db7c7d26971ca3223708f45184826e92524c723f33781814908f09f4',
    'nico/assessment_cpp_clang_header_evidence.py': '4a568190c3cfa519df3a21145c1a96e7f1eec7609639046c61ee586b12670732',
    'nico/assessment_cpp_project_snapshot.py': 'e28dd501c79048dfd52e6f87b154ac1511f33cdb3a26e0b3220aebe86d814f6c',
}
FUNCTION_SOURCES = (
    ('_canonical', 'assessment_cpp_project_compiler.py'),
    ('_digest', 'assessment_cpp_project_compiler.py'),
    ('_stable_bytes', 'assessment_cpp_generated_context.py'),
    ('_verify_input', 'assessment_cpp_project_compiler.py'),
    ('_run', 'assessment_cpp_compiler_evidence.py'),
    ('_regular_bytes', 'assessment_cpp_compiler_evidence.py'),
    ('_clang_require', 'assessment_cpp_clang_header_evidence.py'),
    ('_clang_json', 'assessment_cpp_clang_header_evidence.py'),
    ('validate_clang_header_tool_receipt', 'assessment_cpp_clang_header_evidence.py'),
    ('_fallback_plan', 'assessment_cpp_clang_fallback.py'),
    ('_encode_plist', 'assessment_cpp_clang_fallback.py'),
    ('_request_limits', 'assessment_cpp_clang_fallback.py'),
    ('collect_clang_fallback', 'assessment_cpp_clang_fallback.py'),
    ('run_clang_fallback', 'assessment_cpp_clang_fallback.py'),
)
CONSTANT_NAMES = ('CLANG', 'CLANGXX', 'VERSION', 'LIMITS', 'EXTENDED_LIMITS', 'LOW_CONTENTION_LIMITS',
    'STREAM_LIMIT', 'REQUEST_LIMIT', 'PLIST_LIMIT', 'STORED_PLIST_LIMIT', 'GENERATED_FILE_LIMIT',
    'HEADER_PLUGIN', 'CLANG_HEADER_LIMIT', 'CLANG_HEADER_MANIFEST_SHA256', 'CLANG_HEADER_SOURCE_SHA256',
    'CLANG_HEADER_SDK_SHA256', 'CLANG_HEADER_RUNTIME_SHA256', '_DROP_EXACT', '_DROP_PREFIX')
CGROUP_FILES = ('cpu.stat', 'memory.events', 'cpu.pressure', 'memory.pressure', 'io.pressure',
                'memory.current', 'memory.peak')
TELEMETRY_WRITE_FAILED = False


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'sample_duplicate_json_key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda unused: require(False, 'sample_nonfinite_json'))


def select_sample(full_request, raw_fallback, *, expected_fallback_sha256, prepared_summary):
    """Bind already reconstructed current evidence; no primary/analyzer rerun."""
    require(type(raw_fallback) is bytes and 0 < len(raw_fallback) <= MAX_EVIDENCE
            and type(expected_fallback_sha256) is str and re.fullmatch(r'[0-9a-f]{64}', expected_fallback_sha256)
            and sha(raw_fallback) == expected_fallback_sha256, 'sample_evidence_anchor')
    raw = canonical(full_request)
    fields = {'schema', 'tool_version', 'primary_request_sha256', 'cppcheck_evidence_sha256',
        'compiler_evidence_sha256', 'required_contexts', 'primary_analyzed_contexts', 'contexts', 'limits',
        'header_tool_manifest_sha256', 'header_source_targets', 'header_generated_files'}
    if 'compiler_environment_sha256' in full_request:
        fields.add('compiler_environment_sha256')
    require(len(raw) <= MAX_REQUEST and type(full_request) is dict
            and set(full_request) == fields
            and full_request.get('schema') == 'nico.cpp-clang-fallback-request.v7'
            and full_request.get('tool_version') == '17.0.6'
            and full_request.get('limits') == LIMITS
            and all(type(v) is int for v in full_request['limits'].values()), 'sample_request_policy')
    require(type(prepared_summary) is dict
            and all(type(prepared_summary.get(key)) is int for key in ('source_population', 'snapshot_files',
                'generated_units', 'compiler_contexts', 'historical_required_fallback_contexts'))
            and prepared_summary.get('source_population') == 3031
            and prepared_summary.get('snapshot_files') == 143
            and prepared_summary.get('generated_units') == 42
            and prepared_summary.get('compiler_contexts') == 577
            and prepared_summary.get('historical_required_fallback_contexts') == 576,
            'sample_prepared_population')
    required, contexts = full_request.get('required_contexts'), full_request.get('contexts')
    require(type(required) is list and len(required) == 577
            and all(type(v) is str and re.fullmatch(r'[0-9a-f]{64}', v) for v in required)
            and len(set(required)) == 577
            and type(contexts) is list and len(contexts) == 576, 'sample_full_population')
    targets, generated = full_request.get('header_source_targets'), full_request.get('header_generated_files')
    require(type(targets) is dict and len(targets) == 3031
            and type(generated) is dict and len(generated) == 143
            and full_request.get('header_tool_manifest_sha256') ==
                'b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8',
            'sample_full_header_population')
    evidence = decode(raw_fallback)
    require(type(evidence) is dict and evidence.get('schema') == 'nico.cpp-clang-fallback-evidence.v7'
            and evidence.get('request_sha256') == sha(raw)
            and type(evidence.get('records')) is list and len(evidence['records']) == 576,
            'sample_reconstructed_request_binding')
    ids, indices = set(), set()
    for row, observation in zip(contexts, evidence['records']):
        require(type(row) is dict and type(observation) is dict
                and row.get('context_id') in required and row['context_id'] not in ids
                and type(row.get('index')) is int and 0 <= row['index'] < 577
                and row['index'] not in indices
                and observation.get('context_id') == row['context_id']
                and observation.get('invocation') == row.get('invocation')
                and observation.get('dropped_arguments') == row.get('dropped_arguments')
                and type(row.get('source_dependencies')) is dict
                and type(row.get('generated_dependencies')) is dict, 'sample_context_binding')
        ids.add(row['context_id']);indices.add(row['index'])
    selected = [contexts[position] for position in SELECTED_INDICES]
    require(all(row['index'] == position for row, position in zip(selected, SELECTED_INDICES)),
            'sample_selected_original_indices')
    # Canonical roundtrip owns new data and leaves the original request untouched.
    request = decode(raw)
    request['contexts'] = decode(canonical(selected))
    binding = {'schema': 'nico.diagnostic.four-fallback-selection.v1',
        'full_request_sha256': sha(raw), 'sample_request_sha256': sha(canonical(request)),
        'required_contexts_sha256': sha(canonical(required)),
        'full_fallback_context_ids_sha256': sha(canonical([r['context_id'] for r in contexts])),
        'header_source_targets_sha256': sha(canonical(targets)),
        'header_generated_files_sha256': sha(canonical(generated)),
        'sample_contexts_sha256': sha(canonical(selected)),
        'selected': [{'index': row['index'], 'context_id': row['context_id'],
            'invocation_sha256': sha(canonical(row['invocation'])),
            'source_dependencies_sha256': sha(canonical(row['source_dependencies'])),
            'generated_dependencies_sha256': sha(canonical(row['generated_dependencies']))} for row in selected],
        'obligations': {'full_contexts': 577, 'full_fallback_contexts': 576, 'sampled_contexts': 4,
            'unsampled_fallback_contexts': 572, 'unsampled_status': 'UNMEASURED',
            'source_files': 3031, 'snapshot_files': 143, 'generated_units': 42},
        'full_native_qualified': False, 'production_qualified': False, 'cache_state': 'UNKNOWN'}
    return request, binding


def static_value(node):
    """Data-only constant evaluator for the six immutable source files."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left, right = static_value(node.left), static_value(node.right)
        require(type(left) is int and type(right) is int, 'sample_constant_shape')
        return left * right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'frozenset':
        require(len(node.args) == 1 and not node.keywords, 'sample_constant_shape')
        return frozenset(ast.literal_eval(node.args[0]))
    return ast.literal_eval(node)


def verified_program_prefix(program, source_buffers):
    require(type(program) is str and 0 < len(program.encode()) <= MAX_REQUEST
            and type(source_buffers) is dict and set(source_buffers) == set(SOURCE_PINS), 'sample_program_sources')
    sources, trees = {}, {}
    for name, digest in SOURCE_PINS.items():
        raw = source_buffers[name]
        require(type(raw) is bytes and sha(raw) == digest, 'sample_program_source_pin')
        sources[name] = raw.decode('utf-8', 'strict');trees[name] = ast.parse(raw)
    tree = ast.parse(program)
    imports = ast.parse('import base64, hashlib, json, os, plistlib, re, stat, subprocess, time, zlib\n'
                        'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor\n').body
    require(len(tree.body) == 3 + len(CONSTANT_NAMES) + len(FUNCTION_SOURCES) + 1
            and all(ast.dump(a) == ast.dump(b) for a, b in zip(tree.body[:3], imports)),
            'sample_program_top_level')
    expected = {}
    for path in ('nico/assessment_cpp_clang_fallback.py', 'nico/assessment_cpp_clang_header_evidence.py'):
        for node in trees[path].body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in CONSTANT_NAMES:
                    expected[node.targets[0].id] = static_value(node.value)
    snapshot = trees['nico/assessment_cpp_project_snapshot.py']
    generated_limit = next(node.value for node in snapshot.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'PROJECT_GENERATED_MAX_FILE_BYTES' for target in node.targets))
    expected['GENERATED_FILE_LIMIT'] = static_value(generated_limit)
    for name, node in zip(CONSTANT_NAMES, tree.body[3:3 + len(CONSTANT_NAMES)]):
        require(isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name
                and static_value(node.value) == expected[name], 'sample_program_constant_binding')
    start = 3 + len(CONSTANT_NAMES)
    for (name, file), node in zip(FUNCTION_SOURCES, tree.body[start:-1]):
        source_name = 'nico/' + file
        originals = [row for row in trees[source_name].body if isinstance(row, ast.FunctionDef) and row.name == name]
        require(len(originals) == 1 and isinstance(node, ast.FunctionDef) and node.name == name
                and ast.get_source_segment(program, node) == ast.get_source_segment(sources[source_name], originals[0]),
                'sample_program_function_binding')
    terminal = tree.body[-1]
    require(isinstance(terminal, ast.Expr) and isinstance(terminal.value, ast.Call)
            and isinstance(terminal.value.func, ast.Name) and terminal.value.func.id == 'run_clang_fallback'
            and not terminal.value.args and not terminal.value.keywords
            and program.endswith('\nrun_clang_fallback()\n'), 'sample_program_terminal')
    prefix = program[:-len('run_clang_fallback()\n')]
    return prefix


def finite_nonnegative(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def children_snapshot():
    started = time.perf_counter_ns()
    try:
        value = resource.getrusage(resource.RUSAGE_CHILDREN)
        user, system = value.ru_utime, value.ru_stime
        require(finite_nonnegative(user) and finite_nonnegative(system), 'sample_children_counters')
        return {'status': 'OBSERVED', 'user_seconds': user, 'system_seconds': system,
            'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER',
            'observation_ms': (time.perf_counter_ns() - started) / 1e6}
    except (OSError, ValueError, OverflowError):
        return {'status': 'UNKNOWN', 'user_seconds': None, 'system_seconds': None,
            'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER',
            'observation_ms': (time.perf_counter_ns() - started) / 1e6}


def parse_cgroup(name, raw):
    require(type(raw) is bytes and 0 < len(raw) <= 32768 and b'\0' not in raw, 'sample_cgroup_bound')
    text = raw.decode('ascii', 'strict').strip()
    if name in {'memory.current', 'memory.peak'}:
        require(re.fullmatch(r'[0-9]{1,20}', text) is not None, 'sample_cgroup_integer')
        return {'bytes': int(text)}
    if name in {'cpu.stat', 'memory.events'}:
        allowed = ({'usage_usec', 'user_usec', 'system_usec', 'nice_usec', 'nr_periods', 'nr_throttled', 'throttled_usec',
            'nr_bursts', 'burst_usec'} if name == 'cpu.stat' else {'low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill'})
        required = {'usage_usec', 'user_usec', 'system_usec'} if name == 'cpu.stat' else {'low', 'high', 'max', 'oom', 'oom_kill'}
        result = {}
        for line in text.splitlines():
            parts = line.split()
            require(len(parts) == 2 and parts[0] in allowed and parts[0] not in result
                    and re.fullmatch(r'[0-9]{1,20}', parts[1]), 'sample_cgroup_counter')
            result[parts[0]] = int(parts[1])
        require(required <= set(result), 'sample_cgroup_required')
        return result
    require(name in {'cpu.pressure', 'memory.pressure', 'io.pressure'}, 'sample_cgroup_file')
    result = {}
    for line in text.splitlines():
        parts = line.split()
        require(len(parts) == 5 and parts[0] in {'some', 'full'} and parts[0] not in result, 'sample_pressure_shape')
        values = {}
        for field in parts[1:]:
            key, separator, value = field.partition('=')
            require(separator and key in {'avg10', 'avg60', 'avg300', 'total'} and key not in values, 'sample_pressure_key')
            if key == 'total':
                require(re.fullmatch(r'[0-9]{1,20}', value), 'sample_pressure_total')
                values[key] = int(value)
            else:
                require(re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,6})?', value), 'sample_pressure_average')
                number = float(value)
                require(finite_nonnegative(number) and number <= 100, 'sample_pressure_average')
                values[key] = number
        require(set(values) == {'avg10', 'avg60', 'avg300', 'total'}, 'sample_pressure_population')
        result[parts[0]] = values
    require('some' in result, 'sample_pressure_required')
    return result


def cgroup_snapshot():
    started = time.perf_counter_ns();result = {}
    for name in CGROUP_FILES:
        try:
            with (Path('/sys/fs/cgroup') / name).open('rb') as stream:
                raw = stream.read(32769)
            result[name] = {'status': 'OBSERVED', 'values': parse_cgroup(name, raw)}
        except (OSError, ValueError, UnicodeError, OverflowError):
            result[name] = {'status': 'UNKNOWN', 'values': None}
    return {'scope': 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT',
        'files': result, 'observation_ms': (time.perf_counter_ns() - started) / 1e6}


def counter_deltas(before, after):
    """Missing/reset counters stay unknown; pressure averages are not deltas."""
    result = {}
    for name in CGROUP_FILES:
        left, right = before['files'][name], after['files'][name]
        delta = None
        if left['status'] == right['status'] == 'OBSERVED':
            a, b = left['values'], right['values']
            if name.endswith('.pressure'):
                if set(a) == set(b) and all(b[k]['total'] >= a[k]['total'] for k in a):
                    delta = {k: {'total_usec': b[k]['total'] - a[k]['total']} for k in a}
            elif name not in {'memory.current', 'memory.peak'}:
                if set(a) == set(b) and all(b[k] >= a[k] for k in a):
                    delta = {k: b[k] - a[k] for k in a}
        result[name] = {'status': 'OBSERVED_DELTA' if delta is not None else 'UNKNOWN', 'values': delta}
    return result


def check_envelope(envelope):
    require(type(envelope) is dict and set(envelope) == {'request', 'binding'}, 'sample_envelope')
    request, binding = envelope['request'], envelope['binding']
    require(type(request) is dict and type(binding) is dict
            and set(binding) == {'schema', 'full_request_sha256', 'sample_request_sha256',
                'required_contexts_sha256', 'full_fallback_context_ids_sha256', 'header_source_targets_sha256',
                'header_generated_files_sha256', 'sample_contexts_sha256', 'selected', 'obligations',
                'full_native_qualified', 'production_qualified', 'cache_state'}
            and all(type(binding.get(key)) is str and re.fullmatch(r'[0-9a-f]{64}', binding[key])
                for key in ('full_request_sha256', 'full_fallback_context_ids_sha256'))
            and binding.get('schema') == 'nico.diagnostic.four-fallback-selection.v1'
            and binding.get('sample_request_sha256') == sha(canonical(request))
            and request.get('schema') == 'nico.cpp-clang-fallback-request.v7'
            and request.get('limits') == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
            and all(type(v) is int for v in request['limits'].values())
            and len(request.get('required_contexts', [])) == 577
            and len(request.get('header_source_targets', {})) == 3031
            and len(request.get('header_generated_files', {})) == 143,
            'sample_runtime_binding')
    require(binding.get('obligations') == {'full_contexts': 577, 'full_fallback_contexts': 576, 'sampled_contexts': 4,
            'unsampled_fallback_contexts': 572, 'unsampled_status': 'UNMEASURED',
            'source_files': 3031, 'snapshot_files': 143, 'generated_units': 42}
            and binding.get('full_native_qualified') is False and binding.get('production_qualified') is False
            and binding.get('cache_state') == 'UNKNOWN', 'sample_runtime_scope')
    contexts = request.get('contexts')
    require(type(contexts) is list and len(contexts) == 4 and type(binding.get('selected')) is list
            and len(binding['selected']) == 4
            and binding.get('sample_contexts_sha256') == sha(canonical(contexts))
            and binding.get('required_contexts_sha256') == sha(canonical(request['required_contexts']))
            and binding.get('header_source_targets_sha256') == sha(canonical(request['header_source_targets']))
            and binding.get('header_generated_files_sha256') == sha(canonical(request['header_generated_files'])),
            'sample_runtime_population')
    for index, row, selected in zip((0, 58, 154, 186), contexts, binding['selected']):
        require(type(row) is dict and type(selected) is dict
                and set(selected) == {'index', 'context_id', 'invocation_sha256',
                    'source_dependencies_sha256', 'generated_dependencies_sha256'}
                and row.get('index') == index and type(row['index']) is int
                and selected.get('index') == index and selected.get('context_id') == row.get('context_id')
                and selected.get('invocation_sha256') == sha(canonical(row['invocation']))
                and selected.get('source_dependencies_sha256') == sha(canonical(row['source_dependencies']))
                and selected.get('generated_dependencies_sha256') == sha(canonical(row['generated_dependencies'])),
                'sample_runtime_selected_context')
    return request, binding


def measure_collector(collector, envelope, *, wall_budget_ms=480000):
    # Input/hash comparisons and snapshot reads are outside positive call timing.
    global TELEMETRY_WRITE_FAILED
    TELEMETRY_WRITE_FAILED = False
    require(type(wall_budget_ms) is int and 0 < wall_budget_ms <= 480000, 'sample_runtime_allocation')
    request, binding = check_envelope(envelope)
    cgroup_before = cgroup_snapshot();children_before = children_snapshot()
    started = time.perf_counter_ns();failure = None;result = None
    try:
        result = collector(request, wall_budget_ms=wall_budget_ms)
        return result
    except BaseException as error:
        failure = type(error).__name__ if type(error).__name__ in {
            'ValueError', 'OSError', 'KeyError', 'TypeError', 'KeyboardInterrupt', 'SystemExit'} else 'OtherException'
        raise
    finally:
        elapsed = (time.perf_counter_ns() - started) / 1e6
        children_after = children_snapshot();cgroup_after = cgroup_snapshot()
        child_delta = None
        if children_before['status'] == children_after['status'] == 'OBSERVED':
            user = children_after['user_seconds'] - children_before['user_seconds']
            system = children_after['system_seconds'] - children_before['system_seconds']
            if finite_nonnegative(user) and finite_nonnegative(system):
                child_delta = {'user_seconds': user, 'system_seconds': system, 'total_seconds': user + system}
        telemetry = {'schema': 'nico.diagnostic.four-fallback-resources.v1',
            'status': 'COLLECTOR_RETURNED' if failure is None else 'UNPROVEN', 'collector_error_type': failure,
            'selection': binding, 'limits': {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2},
            'collector_call_wall_ms': elapsed, 'actual_wall_budget_ms': wall_budget_ms,
            'collector_wall_scope': 'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS',
            'children': {'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER',
                'includes_version_probe': True, 'per_context_cpu_available': False,
                'before': children_before, 'after': children_after,
                'delta_status': 'OBSERVED' if child_delta is not None else 'UNKNOWN', 'delta': child_delta},
            'cgroup': {'before': cgroup_before, 'after': cgroup_after,
                'delta': counter_deltas(cgroup_before, cgroup_after)},
            'evidence_sha256': sha(canonical(result)) if result is not None else None,
            'full_native_qualified': False, 'production_qualified': False, 'historical_replay_credit': False,
            'cache_state': 'UNKNOWN', 'unsampled_status': 'UNMEASURED'}
        try:
            data = json.dumps(telemetry, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            require(len(data) <= 128 * 1024, 'sample_telemetry_bound')
            # Same private analyst directory; raw fallback output remains on stdout.
            with Path('/work/analysis/capacity-sample-telemetry.json').open('xb') as stream:
                stream.write(data)
        except (OSError, ValueError, OverflowError, TypeError):
            # Preserve original collector data/error. Missing sidecar causes an
            # explicit nonzero success-path exit, never a fabricated observation.
            TELEMETRY_WRITE_FAILED = True


def run_capacity_sample():
    import sys
    try:
        raw = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        require(len(raw) <= 8 * 1024 * 1024 and len(sys.argv) <= 2, 'sample_runtime_request_bound')
        if len(sys.argv) == 2:
            require(sys.argv[1].isascii() and sys.argv[1].isdigit() and len(sys.argv[1]) <= 6
                    and str(int(sys.argv[1])) == sys.argv[1], 'sample_runtime_allocation')
        budget = int(sys.argv[1]) if len(sys.argv) == 2 else 480000
        envelope = decode(raw)
        result = measure_collector(collect_clang_fallback, envelope, wall_budget_ms=budget)
    except Exception as error:
        code = str(error)
        if re.fullmatch(r'worker_clang_fallback_[a-z_]+', code) is None:
            code = 'worker_clang_fallback_unavailable'
        print(json.dumps({'schema': 'nico.cpp-clang-fallback-failure.v1', 'error': code}))
        sys.exit(1)
    print(_canonical(result).decode())
    if TELEMETRY_WRITE_FAILED:
        sys.exit(2)


def build_worker_program(original_program, source_buffers, *, expected_sample_sha256):
    prefix = verified_program_prefix(original_program, source_buffers)
    with Path(__file__).open('rb') as stream:
        source_raw = stream.read(MAX_REQUEST + 1)
    require(type(expected_sample_sha256) is str
            and re.fullmatch(r'[0-9a-f]{64}', expected_sample_sha256)
            and 0 < len(source_raw) <= MAX_REQUEST
            and sha(source_raw) == expected_sample_sha256, 'sample_instrumentation_source_binding')
    this = source_raw.decode('utf-8', 'strict')
    tree = ast.parse(this)
    names = ('require', 'canonical', 'sha', 'decode', 'finite_nonnegative', 'children_snapshot', 'parse_cgroup',
             'cgroup_snapshot', 'counter_deltas', 'check_envelope', 'measure_collector', 'run_capacity_sample')
    functions = {node.name: ast.get_source_segment(this, node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    extra = '\nimport resource, math\nTELEMETRY_WRITE_FAILED=False\nCGROUP_FILES=' + repr(CGROUP_FILES) + '\n'
    program = prefix + extra + '\n'.join(functions[name] for name in names) + '\nrun_capacity_sample()\n'
    require(program.startswith(prefix) and len(program.encode()) <= MAX_REQUEST, 'sample_program_bound')
    return program, {'original_program_sha256': sha(original_program.encode()),
        'sample_module_sha256': expected_sample_sha256,
        'sample_program_sha256': sha(program.encode()), 'original_prefix_sha256': sha(prefix.encode()),
        'original_function_buffers_verified': True, 'producer_source_pins': dict(SOURCE_PINS),
        'new_terminal_only': True, 'full_native_qualified': False}


def validate_sample_telemetry(raw, envelope, native_raw, *, actual_wall_budget_ms):
    """Host gate after original four-record validation, never full qualification."""
    request, binding = check_envelope(envelope)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_TELEMETRY
            and type(native_raw) is bytes and 0 < len(native_raw) <= MAX_EVIDENCE,
            'sample_telemetry_transport_bound')
    value = decode(raw)
    keys = {'schema', 'status', 'collector_error_type', 'selection', 'limits', 'collector_call_wall_ms',
        'actual_wall_budget_ms', 'collector_wall_scope', 'children', 'cgroup', 'evidence_sha256',
        'full_native_qualified', 'production_qualified', 'historical_replay_credit', 'cache_state', 'unsampled_status'}
    require(type(value) is dict and set(value) == keys
            and value.get('schema') == 'nico.diagnostic.four-fallback-resources.v1'
            and value.get('status') == 'COLLECTOR_RETURNED' and value.get('collector_error_type') is None
            and value.get('selection') == binding and value.get('limits') == LIMITS
            and type(actual_wall_budget_ms) is int and 0 < actual_wall_budget_ms <= 480000
            and type(value.get('actual_wall_budget_ms')) is int
            and value['actual_wall_budget_ms'] == actual_wall_budget_ms
            and finite_nonnegative(value.get('collector_call_wall_ms'))
            and value['collector_call_wall_ms'] <= actual_wall_budget_ms + 3000
            and value.get('collector_wall_scope') ==
                'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS'
            and all(value.get(key) is False for key in ('full_native_qualified', 'production_qualified', 'historical_replay_credit'))
            and value.get('cache_state') == 'UNKNOWN' and value.get('unsampled_status') == 'UNMEASURED'
            and value.get('evidence_sha256') == sha(canonical(decode(native_raw))),
            'sample_telemetry_identity')
    children = value.get('children')
    require(type(children) is dict and set(children) == {'scope', 'includes_version_probe', 'per_context_cpu_available',
        'before', 'after', 'delta_status', 'delta'}
        and children.get('scope') == 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER'
        and children.get('includes_version_probe') is True
        and children.get('per_context_cpu_available') is False, 'sample_telemetry_children_scope')
    for snapshot in (children['before'], children['after']):
        require(type(snapshot) is dict and set(snapshot) == {'status', 'user_seconds', 'system_seconds', 'scope', 'observation_ms'}
                and snapshot['scope'] == children['scope'] and finite_nonnegative(snapshot['observation_ms'])
                and (snapshot['status'] == 'OBSERVED' and finite_nonnegative(snapshot['user_seconds'])
                    and finite_nonnegative(snapshot['system_seconds'])
                    or snapshot['status'] == 'UNKNOWN' and snapshot['user_seconds'] is None and snapshot['system_seconds'] is None),
                'sample_telemetry_children_snapshot')
    expected = None
    if children['before']['status'] == children['after']['status'] == 'OBSERVED':
        user = children['after']['user_seconds'] - children['before']['user_seconds']
        system = children['after']['system_seconds'] - children['before']['system_seconds']
        if finite_nonnegative(user) and finite_nonnegative(system):
            expected = {'user_seconds': user, 'system_seconds': system, 'total_seconds': user + system}
    require(children['delta'] == expected
            and children['delta_status'] == ('OBSERVED' if expected is not None else 'UNKNOWN'),
            'sample_telemetry_children_delta')
    group = value.get('cgroup')
    require(type(group) is dict and set(group) == {'before', 'after', 'delta'}, 'sample_telemetry_cgroup')
    for snapshot in (group['before'], group['after']):
        require(type(snapshot) is dict and set(snapshot) == {'scope', 'files', 'observation_ms'}
                and snapshot['scope'] == 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT'
                and finite_nonnegative(snapshot['observation_ms']) and type(snapshot['files']) is dict
                and set(snapshot['files']) == set(CGROUP_FILES), 'sample_telemetry_cgroup_snapshot')
        for name, row in snapshot['files'].items():
            require(type(row) is dict and set(row) == {'status', 'values'}
                    and row['status'] in {'OBSERVED', 'UNKNOWN'}, 'sample_telemetry_cgroup_status')
            data = row['values']
            if row['status'] == 'UNKNOWN':
                require(data is None, 'sample_telemetry_unknown_counter')
                continue
            require(type(data) is dict, 'sample_telemetry_counter_population')
            if name.endswith('.pressure'):
                require('some' in data and set(data) <= {'some', 'full'}, 'sample_telemetry_pressure_population')
                for numbers in data.values():
                    require(type(numbers) is dict and set(numbers) == {'avg10', 'avg60', 'avg300', 'total'}
                            and type(numbers['total']) is int and 0 <= numbers['total'] < 10 ** 20
                            and all(finite_nonnegative(numbers[key]) and numbers[key] <= 100
                                    for key in ('avg10', 'avg60', 'avg300')), 'sample_telemetry_pressure_values')
            else:
                reconstructed = (str(data.get('bytes', '')) + '\n' if name in {'memory.current', 'memory.peak'}
                    else ''.join(str(key) + ' ' + str(number) + '\n' for key, number in data.items()))
                require(parse_cgroup(name, reconstructed.encode()) == data
                        and all(type(number) is int for number in data.values()), 'sample_telemetry_counter_values')
    require(group['delta'] == counter_deltas(group['before'], group['after']), 'sample_telemetry_cgroup_delta')
    return value
