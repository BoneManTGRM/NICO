"""One bounded diagnostic pair. Production v7 admission and qualification stay intact."""
from __future__ import annotations

import ast
import base64
import plistlib
import copy
import importlib.util
import importlib.machinery
import hashlib
from pathlib import Path
import re

SAMPLE_SHA256 = '6502680b08f124cfa417019647e7c42f873e7efa9017faa54efd52738cedfe1a'

class _VerifiedBufferLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, raw):
        super().__init__(name, str(path))
        self.verified_raw = raw
    def get_data(self, path):
        if path != self.path:
            raise OSError('verified_source_bytecode_unavailable')
        return self.verified_raw
    def set_data(self, path, data, **kwargs):
        return None

def verified_sample(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SAMPLE_SHA256:
        raise ValueError('pair_sample_source_identity')
    loader = _VerifiedBufferLoader('nico_capacity_reference', path, raw)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module, raw

SAMPLE, SAMPLE_RAW = verified_sample(Path(__file__).with_name('cpp_fallback_capacity_sample.py'))
require, canonical, sha, decode = SAMPLE.require, SAMPLE.canonical, SAMPLE.sha, SAMPLE.decode


SELECTED_INDICES = (58, 114, 153, 154)
SIDECAR = '/work/analysis/parallel-pair-telemetry.json'
PAIR_LIMITS = dict(SAMPLE.LIMITS)
EXECUTION_IDENTITY = {'image_digest': 'sha256:2de94c121db7ae46df5415a40b33cd2d057fcc3b7bf9aa9d51756ecb4412447e',
    'runner_class': 'ubuntu-24.04', 'cpu': 4, 'memory_bytes': 12884901888,
    'isolation': 'cpp-baseline-qualification-v1', 'stage_seconds_per_arm': 1020, 'outer_seconds': 155 * 60}
MAX_REQUEST, MAX_EVIDENCE, MAX_TELEMETRY = SAMPLE.MAX_REQUEST, SAMPLE.MAX_EVIDENCE, SAMPLE.MAX_TELEMETRY


def selected_identity(row):
    return {'index': row['index'], 'context_id': row['context_id'],
        'invocation_sha256': sha(canonical(row['invocation'])),
        'source_dependencies_sha256': sha(canonical(row['source_dependencies'])),
        'generated_dependencies_sha256': sha(canonical(row['generated_dependencies']))}


def scheduling_parallel(value):
    require(type(value) is int and value in (2, 4), 'pair_diagnostic_parallel')
    return value

def validate_execution_identity(value):
    require(type(value) is dict and value == EXECUTION_IDENTITY
        and all(type(value[key]) is int for key in ('cpu', 'memory_bytes', 'stage_seconds_per_arm', 'outer_seconds')),
        'pair_execution_identity')
    return value


def preflight_pair(full_request, raw_fallback, *, expected_fallback_sha256,
                   prepared_summary, expected_selected, execution_identity):
    """Both arms must be constructed/validated together before any dispatch.

    expected_selected is privately reviewed context identity, not index lookup.
    execution_identity must be the exact common image/runner allocation receipt.
    Stage budgets are per arm; aggregate outer budget is never reset by this seam.
    """
    require(type(full_request) is dict and type(raw_fallback) is bytes
        and 0 < len(raw_fallback) <= MAX_EVIDENCE
        and type(expected_fallback_sha256) is str
        and re.fullmatch(r'[0-9a-f]{64}', expected_fallback_sha256)
        and sha(raw_fallback) == expected_fallback_sha256, 'pair_retained_evidence')
    # Reuse the authoritative population and retained evidence checks; its old
    # sample is discarded. No analyzer runs, source globals or requests mutate.
    _, anchor = SAMPLE.select_sample(full_request, raw_fallback,
        expected_fallback_sha256=expected_fallback_sha256, prepared_summary=prepared_summary)
    rows = {row['index']: row for row in full_request['contexts']}
    require(all(index in rows for index in SELECTED_INDICES), 'pair_required_indices')
    selected = [rows[index] for index in SELECTED_INDICES]
    require(type(expected_selected) is list and len(expected_selected) == 4
        and expected_selected == [selected_identity(row) for row in selected]
        and all(type(row.get('index')) is int for row in expected_selected),
        'pair_private_selected_binding')
    validate_execution_identity(execution_identity)
    request = decode(canonical(full_request));request['contexts'] = decode(canonical(selected))
    binding = dict(anchor)
    binding.update(schema='nico.diagnostic.parallel-pair-selection.v1',
        sample_request_sha256=sha(canonical(request)), sample_contexts_sha256=sha(canonical(selected)),
        selected=decode(canonical(expected_selected)), retained_fallback_sha256=expected_fallback_sha256,
        execution_identity=decode(canonical(execution_identity)))
    envelopes = tuple({'request': decode(canonical(request)), 'binding': decode(canonical(binding)),
        'diagnostic_parallel': parallel} for parallel in (2, 4))
    for envelope in envelopes:
        check_pair_envelope(envelope)
    require(envelopes[0]['request'] == envelopes[1]['request']
        and envelopes[0]['binding'] == envelopes[1]['binding'], 'pair_arm_equivalence')
    return envelopes, binding


def check_pair_envelope(envelope):
    require(type(envelope) is dict and set(envelope) == {'request', 'binding', 'diagnostic_parallel'},
        'pair_envelope')
    scheduling_parallel(envelope['diagnostic_parallel'])
    request, binding = envelope['request'], envelope['binding']
    require(type(request) is dict and type(binding) is dict
        and set(binding) == {'schema', 'full_request_sha256', 'sample_request_sha256',
            'required_contexts_sha256', 'full_fallback_context_ids_sha256', 'header_source_targets_sha256',
            'header_generated_files_sha256', 'sample_contexts_sha256', 'selected', 'obligations',
            'full_native_qualified', 'production_qualified', 'cache_state',
            'retained_fallback_sha256', 'execution_identity'}
        and binding['schema'] == 'nico.diagnostic.parallel-pair-selection.v1'
        and request.get('schema') == 'nico.cpp-clang-fallback-request.v7'
        and request.get('limits') == PAIR_LIMITS
        and all(type(v) is int for v in request['limits'].values())
        and len(request.get('required_contexts', [])) == 577
        and len(request.get('header_source_targets', {})) == 3031
        and len(request.get('header_generated_files', {})) == 143
        and binding['sample_request_sha256'] == sha(canonical(request))
        and binding['required_contexts_sha256'] == sha(canonical(request['required_contexts']))
        and binding['header_source_targets_sha256'] == sha(canonical(request['header_source_targets']))
        and binding['header_generated_files_sha256'] == sha(canonical(request['header_generated_files']))
        and binding['sample_contexts_sha256'] == sha(canonical(request.get('contexts'))), 'pair_runtime_binding')
    require(binding['obligations'] == {'full_contexts': 577, 'full_fallback_contexts': 576, 'sampled_contexts': 4,
        'unsampled_fallback_contexts': 572, 'unsampled_status': 'UNMEASURED',
        'source_files': 3031, 'snapshot_files': 143, 'generated_units': 42}
        and binding['full_native_qualified'] is False and binding['production_qualified'] is False
        and binding['cache_state'] == 'UNKNOWN', 'pair_runtime_scope')
    validate_execution_identity(binding['execution_identity'])
    rows = request.get('contexts')
    require(type(rows) is list and len(rows) == 4 and type(binding['selected']) is list
        and binding['selected'] == [selected_identity(row) for row in rows]
        and all(type(row['index']) is int for row in rows)
        and tuple(row['index'] for row in rows) == SELECTED_INDICES
        and len({row['context_id'] for row in rows}) == 4
        and all(row['context_id'] in request['required_contexts'] for row in rows), 'pair_runtime_selected')
    require(all(type(binding[key]) is str and re.fullmatch(r'[0-9a-f]{64}', binding[key])
        for key in ('full_request_sha256', 'full_fallback_context_ids_sha256', 'retained_fallback_sha256')),
        'pair_runtime_anchor')
    return request, binding


def diagnostic_collector_source(prefix):
    """Only rename/signature/max_workers differ from the verified collector AST."""
    original = next(node for node in ast.parse(prefix).body
        if isinstance(node, ast.FunctionDef) and node.name == 'collect_clang_fallback')
    expected = copy.deepcopy(original)
    expected.name = 'collect_diagnostic_parallel_fallback'
    expected.args.kwonlyargs.append(ast.arg(arg='diagnostic_parallel'))
    expected.args.kw_defaults.append(None)
    replaced = 0
    for node in ast.walk(expected):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'ThreadPoolExecutor':
            require(len(node.keywords) == 1 and node.keywords[0].arg == 'max_workers'
                and ast.dump(node.keywords[0].value) == ast.dump(ast.parse("limits['parallel']", mode='eval').body),
                'pair_original_executor')
            node.keywords[0].value = ast.Name(id='diagnostic_parallel', ctx=ast.Load());replaced += 1
    require(replaced == 1, 'pair_single_executor')
    text = ast.unparse(ast.fix_missing_locations(expected))
    require(ast.dump(ast.parse(text).body[0]) == ast.dump(expected), 'pair_collector_ast')
    return text


def run_parallel_pair():
    import sys
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        require(0 < len(raw) <= MAX_REQUEST and len(sys.argv) <= 2, 'pair_runtime_request_bound')
        if len(sys.argv) == 2:
            require(sys.argv[1].isascii() and sys.argv[1].isdigit() and len(sys.argv[1]) <= 6
                and str(int(sys.argv[1])) == sys.argv[1], 'pair_runtime_allocation')
        budget = int(sys.argv[1]) if len(sys.argv) == 2 else 480000
        envelope = decode(raw)
        request, _ = check_pair_envelope(envelope)
        _request_limits(request)  # unchanged production v7 admission, parallel remains 2
        result = measure_parallel_collector(collect_diagnostic_parallel_fallback, envelope, wall_budget_ms=budget)
    except Exception as error:
        code = str(error)
        if re.fullmatch(r'worker_clang_fallback_[a-z_]+', code) is None:
            code = 'worker_clang_fallback_unavailable'
        print(json.dumps({'schema': 'nico.cpp-clang-fallback-failure.v1', 'error': code}))
        sys.exit(1)
    print(_canonical(result).decode())
    if TELEMETRY_WRITE_FAILED:
        sys.exit(2)


def build_worker_program(original_program, source_buffers, *, expected_sample_sha256, expected_pair_sha256):
    prefix = SAMPLE.verified_program_prefix(original_program, source_buffers)
    validator_proof = verify_diagnostic_validator(source_buffers)
    sample_raw = SAMPLE_RAW;pair_raw = Path(__file__).read_bytes()
    require(sha(sample_raw) == expected_sample_sha256 and sha(pair_raw) == expected_pair_sha256,
        'pair_instrumentation_source_binding')
    sample_text, pair_text = sample_raw.decode(), pair_raw.decode()
    sample_functions = {node.name: ast.get_source_segment(sample_text, node)
        for node in ast.parse(sample_text).body if isinstance(node, ast.FunctionDef)}
    pair_functions = {node.name: ast.get_source_segment(pair_text, node)
        for node in ast.parse(pair_text).body if isinstance(node, ast.FunctionDef)}
    measure = sample_functions['measure_collector']
    replacements = {
        'def measure_collector(': 'def measure_parallel_collector(',
        'check_envelope(envelope)': 'check_pair_envelope(envelope)',
        'collector(request, wall_budget_ms=wall_budget_ms)':
            "collector(request, wall_budget_ms=wall_budget_ms, diagnostic_parallel=envelope['diagnostic_parallel'])",
        "'nico.diagnostic.four-fallback-resources.v1'": "'nico.diagnostic.parallel-pair-resources.v1'",
        "'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS'":
            "'DIAGNOSTIC_PARALLEL_ONLY_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS'",
        "Path('/work/analysis/capacity-sample-telemetry.json')": "Path('/work/analysis/parallel-pair-telemetry.json')",
        '        try:\n            data = json.dumps(telemetry,':
            "        telemetry.update(diagnostic_parallel=envelope['diagnostic_parallel'], envelope_sha256=sha(canonical(envelope)))\n        try:\n            data = json.dumps(telemetry,",
    }
    for before, after in replacements.items():
        require(measure.count(before) == 1, 'pair_measurement_narrow_replacement')
        measure = measure.replace(before, after)
    names = ('require', 'canonical', 'sha', 'decode', 'finite_nonnegative', 'children_snapshot',
        'parse_cgroup', 'cgroup_snapshot', 'counter_deltas')
    extra = '\nimport resource, math\nTELEMETRY_WRITE_FAILED=False\nCGROUP_FILES=' + repr(SAMPLE.CGROUP_FILES)
    extra += '\nEXECUTION_IDENTITY=' + repr(EXECUTION_IDENTITY)
    extra += '\nPAIR_LIMITS=' + repr(PAIR_LIMITS) + '\nMAX_REQUEST=' + repr(MAX_REQUEST)
    extra += '\nSELECTED_INDICES=' + repr(SELECTED_INDICES) + '\n'
    program = prefix + extra + '\n'.join(sample_functions[name] for name in names) + '\n'
    program += '\n'.join(pair_functions[name] for name in
        ('selected_identity', 'scheduling_parallel', 'validate_execution_identity', 'check_pair_envelope')) + '\n'
    program += diagnostic_collector_source(prefix) + '\n' + measure + '\n'
    program += pair_functions['run_parallel_pair'] + '\nrun_parallel_pair()\n'
    require(program.startswith(prefix) and len(program.encode()) <= MAX_REQUEST, 'pair_program_bound')
    return program, {'original_program_sha256': sha(original_program.encode()),
        'original_prefix_sha256': sha(prefix.encode()), 'sample_module_sha256': expected_sample_sha256,
        'pair_module_sha256': expected_pair_sha256, 'pair_program_sha256': sha(program.encode()),
        'producer_source_pins': dict(SAMPLE.SOURCE_PINS), 'original_function_buffers_verified': True,
        'diagnostic_decoder': validator_proof,
        'diagnostic_collector_changes': ['name', 'required_keyword_diagnostic_parallel', 'executor_max_workers'],
        'same_program_both_arms': True, 'full_native_qualified': False, 'production_qualified': False}


def validate_pair_telemetry(raw, envelope, native_raw, *, actual_wall_budget_ms):
    """Validate transport, identity and observed counters, retaining native failures."""
    request, binding = check_pair_envelope(envelope)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_TELEMETRY
        and type(native_raw) is bytes and 0 < len(native_raw) <= MAX_EVIDENCE,
        'pair_telemetry_transport')
    value, native = decode(raw), decode(native_raw)
    require(type(value) is dict and set(value) == {'schema', 'status', 'collector_error_type', 'selection', 'limits',
        'collector_call_wall_ms', 'actual_wall_budget_ms', 'collector_wall_scope', 'children', 'cgroup', 'evidence_sha256',
        'full_native_qualified', 'production_qualified', 'historical_replay_credit', 'cache_state', 'unsampled_status',
        'diagnostic_parallel', 'envelope_sha256'}
        and value.get('schema') == 'nico.diagnostic.parallel-pair-resources.v1'
        and value.get('selection') == binding and value.get('limits') == PAIR_LIMITS
        and value.get('diagnostic_parallel') == envelope['diagnostic_parallel']
        and type(value.get('diagnostic_parallel')) is int
        and value.get('envelope_sha256') == sha(canonical(envelope))
        and value.get('evidence_sha256') == sha(canonical(native))
        and value.get('status') == 'COLLECTOR_RETURNED' and value.get('collector_error_type') is None
        and type(actual_wall_budget_ms) is int and 0 < actual_wall_budget_ms <= 480000
        and type(value.get('actual_wall_budget_ms')) is int
        and value['actual_wall_budget_ms'] == actual_wall_budget_ms
        and SAMPLE.finite_nonnegative(value.get('collector_call_wall_ms'))
        and value['collector_call_wall_ms'] <= actual_wall_budget_ms + 3000
        and value.get('collector_wall_scope') ==
            'DIAGNOSTIC_PARALLEL_ONLY_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS'
        and all(value.get(key) is False for key in ('full_native_qualified', 'production_qualified', 'historical_replay_credit'))
        and value.get('cache_state') == 'UNKNOWN' and value.get('unsampled_status') == 'UNMEASURED',
        'pair_telemetry_identity')
    validate_native_identity(native, request)
    children = value.get('children')
    require(type(children) is dict and set(children) == {'scope', 'includes_version_probe',
        'per_context_cpu_available', 'before', 'after', 'delta_status', 'delta'}
        and children.get('scope') == 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER'
        and children.get('includes_version_probe') is True and children.get('per_context_cpu_available') is False,
        'pair_children_scope')
    expected = None
    for row in (children['before'], children['after']):
        require(type(row) is dict and set(row) == {'status', 'user_seconds', 'system_seconds', 'scope', 'observation_ms'}
            and row.get('scope') == children['scope']
            and SAMPLE.finite_nonnegative(row.get('observation_ms'))
            and (row.get('status') == 'UNKNOWN' and row.get('user_seconds') is None and row.get('system_seconds') is None
                or row.get('status') == 'OBSERVED' and SAMPLE.finite_nonnegative(row.get('user_seconds'))
                    and SAMPLE.finite_nonnegative(row.get('system_seconds'))), 'pair_children_snapshot')
    if children['before']['status'] == children['after']['status'] == 'OBSERVED':
        user = children['after']['user_seconds'] - children['before']['user_seconds']
        system = children['after']['system_seconds'] - children['before']['system_seconds']
        if SAMPLE.finite_nonnegative(user) and SAMPLE.finite_nonnegative(system):
            expected = {'user_seconds': user, 'system_seconds': system, 'total_seconds': user + system}
    require(children.get('delta') == expected and children.get('delta_status') ==
        ('OBSERVED' if expected is not None else 'UNKNOWN'), 'pair_children_delta')
    group = value.get('cgroup')
    require(type(group) is dict and set(group) == {'before', 'after', 'delta'}, 'pair_cgroup_shape')
    for snapshot in (group['before'], group['after']):
        require(type(snapshot) is dict and set(snapshot) == {'scope', 'files', 'observation_ms'}
            and snapshot.get('scope') == 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT'
            and SAMPLE.finite_nonnegative(snapshot.get('observation_ms'))
            and type(snapshot.get('files')) is dict and set(snapshot['files']) == set(SAMPLE.CGROUP_FILES),
            'pair_cgroup_snapshot')
        for name, row in snapshot['files'].items():
            require(type(row) is dict and set(row) == {'status', 'values'}, 'pair_cgroup_counter_shape')
            if row['status'] == 'UNKNOWN':
                require(row['values'] is None, 'pair_unknown_counter');continue
            data = row['values']
            require(row['status'] == 'OBSERVED' and type(data) is dict, 'pair_observed_counter')
            if name.endswith('.pressure'):
                text = ''.join(key + ' ' + ' '.join(str(k) + '=' + str(v) for k, v in numbers.items())
                    + '\n' for key, numbers in data.items())
            elif name in {'memory.current', 'memory.peak'}:
                require(set(data) == {'bytes'} and type(data['bytes']) is int, 'pair_memory_counter')
                text = str(data['bytes'])
            else:
                require(all(type(number) is int for number in data.values()), 'pair_integer_counter')
                text = ''.join(str(key) + ' ' + str(number) + '\n' for key, number in data.items())
            require(SAMPLE.parse_cgroup(name, text.encode()) == data, 'pair_counter_values')
    require(group['delta'] == SAMPLE.counter_deltas(group['before'], group['after']), 'pair_cgroup_delta')
    return value


def validate_native_identity(native, request):
    require(type(native) is dict and native.get('schema') == 'nico.cpp-clang-fallback-evidence.v7'
        and native.get('request_sha256') == sha(canonical(request))
        and type(native.get('records')) is list and len(native['records']) == 4, 'pair_native_identity')
    for row, context in zip(native['records'], request['contexts']):
        require(type(row) is dict and row.get('context_id') == context['context_id']
            and row.get('invocation') == context['invocation']
            and row.get('dropped_arguments') == context['dropped_arguments'], 'pair_native_context')


def compare_pair_outputs(native2, native4, envelopes):
    """Compare semantic/native artifacts; differing failures remain differences.

    Original native decoder remains independently required. This comparison
    deliberately grants no qualification or inferred 576-context capacity.
    """
    require(type(envelopes) in (tuple, list) and len(envelopes) == 2, 'pair_comparison_arms')
    for envelope, parallel in zip(envelopes, (2, 4)):
        check_pair_envelope(envelope)
        require(envelope['diagnostic_parallel'] == parallel, 'pair_comparison_order')
    require(envelopes[0]['request'] == envelopes[1]['request']
        and envelopes[0]['binding'] == envelopes[1]['binding'], 'pair_comparison_equivalence')
    values = [decode(raw) for raw in (native2, native4)]
    for native, envelope in zip(values, envelopes):
        validate_native_identity(native, envelope['request'])
    def semantic(value):
        result = copy.deepcopy(value)
        result.pop('duration_ms', None)
        for execution in [result.get('version'), *(row.get('execution') for row in result['records'])]:
            if type(execution) is dict:
                execution.pop('duration_ms', None)
        return result
    rows = [{'context_id': left['context_id'],
        'native_output_equal': left.get('execution', {}).get('output_sha256') == right.get('execution', {}).get('output_sha256')
            if type(left.get('execution')) is dict and type(right.get('execution')) is dict else left.get('execution') == right.get('execution'),
        'plist_equal': left.get('plist_sha256') == right.get('plist_sha256'),
        'header_trace_equal': left.get('header_trace_sha256') == right.get('header_trace_sha256'),
        'error_equal': left.get('error') == right.get('error')}
        for left, right in zip(values[0]['records'], values[1]['records'])]
    return {'semantic_equal': semantic(values[0]) == semantic(values[1]), 'contexts': rows,
        'full_native_qualified': False, 'production_qualified': False, 'unsampled_status': 'UNMEASURED'}


def validate_pair_native(raw, envelope, primary_request, *, wall_budget_ms=None):
    # Caller preparation installs the verified source finder and dependencies
    # before this runtime-only gate. Pure host controls never import NICO.
    # Explicit bindings leave production helpers/admission untouched; the
    # static decoder copy and its narrow AST proof remain unchanged.
    request, _ = check_pair_envelope(envelope)
    global _request_limits, _execution, _decode_plist, _clang_standard
    global _digest, _canonical, STREAM_LIMIT, VERSION, CLANG_HEADER_LIMIT, CLANG_HEADER_MANIFEST_SHA256
    global validate_clang_header_tool_receipt, validate_clang_header_trace
    from nico.assessment_cpp_clang_fallback import (
        _request_limits, _execution, _decode_plist, _clang_standard,
        _digest, _canonical, STREAM_LIMIT, VERSION, CLANG_HEADER_LIMIT, CLANG_HEADER_MANIFEST_SHA256,
        validate_clang_header_tool_receipt, validate_clang_header_trace)
    return _validate_diagnostic_native(raw, request, primary_request,
        wall_budget_ms=wall_budget_ms, diagnostic_parallel=scheduling_parallel(envelope['diagnostic_parallel']))


def verify_diagnostic_validator(source_buffers):
    """Prove preserved parser/header/failure checks plus one aggregate slot bound."""
    require(type(source_buffers) is dict and set(source_buffers) == set(SAMPLE.SOURCE_PINS)
        and all(type(source_buffers[name]) is bytes and sha(source_buffers[name]) == digest
            for name, digest in SAMPLE.SOURCE_PINS.items()), 'pair_validator_source_pins')
    source = source_buffers['nico/assessment_cpp_clang_fallback.py'].decode()
    original = next(node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == 'validate_clang_fallback')
    expected = copy.deepcopy(original);expected.name = '_validate_diagnostic_native'
    expected.args.kwonlyargs.append(ast.arg(arg='diagnostic_parallel'));expected.args.kw_defaults.append(None)
    replaced = 0
    for node in ast.walk(expected):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            if ast.dump(node.left) == ast.dump(ast.parse("evidence['duration_ms']", mode='eval').body) and ast.dump(node.right) == ast.dump(ast.parse("limits['parallel']", mode='eval').body):
                node.right = ast.Name(id='diagnostic_parallel', ctx=ast.Load());replaced += 1
    actual = next(node for node in ast.parse(Path(__file__).read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == '_validate_diagnostic_native')
    require(replaced == 1 and ast.dump(expected) == ast.dump(actual), 'pair_validator_ast')
    return {'source_sha256': sha(source_buffers['nico/assessment_cpp_clang_fallback.py']),
        'changes': ['name', 'required_keyword_diagnostic_parallel', 'aggregate_worker_slot_duration_bound'],
        'production_admission_unchanged': True, 'parser_header_failure_checks_unchanged': True}


def _validate_diagnostic_native(raw, request, primary_request, *, wall_budget_ms=None, diagnostic_parallel):
    from nico.assessment_cpp_full_project import _json
    limits = _request_limits(request)
    if not isinstance(raw,bytes) or not 0<len(raw)<=STREAM_LIMIT: raise ValueError('worker_clang_fallback_output_limit')
    evidence=_json(raw)
    if wall_budget_ms is not None and (type(wall_budget_ms) is not int
            or not 0 < wall_budget_ms <= limits['wall_seconds'] * 1000
            or evidence.get('wall_budget_ms') != wall_budget_ms):
        raise ValueError('worker_clang_fallback_evidence_invalid')
    header_provenance=request['schema'] in {'nico.cpp-clang-fallback-request.v5','nico.cpp-clang-fallback-request.v7'}
    if (primary_request.get('schema')=='nico.cpp-project-static-request.v4') != (
            request['schema']=='nico.cpp-clang-fallback-request.v7'):
        raise ValueError('worker_clang_fallback_header_policy_invalid')
    fields={'schema','request_sha256','analyst_uid','version','records','duration_ms'}
    allocated_ms = limits['wall_seconds'] * 1000
    if 'wall_budget_ms' in evidence:
        fields.add('wall_budget_ms')
        allocated_ms = evidence['wall_budget_ms']
        if type(allocated_ms) is not int or not 0 < allocated_ms <= limits['wall_seconds'] * 1000:
            raise ValueError('worker_clang_fallback_evidence_invalid')
    if header_provenance:fields|={'header_tool_receipt','header_tool_receipt_sha256'}
    if (not isinstance(evidence,dict) or set(evidence)!=fields
            or evidence['schema']!=request['schema'].replace('-request.', '-evidence.')
            or evidence['request_sha256']!=_digest(_canonical(request))
            or evidence['analyst_uid']!=1001 or type(evidence['analyst_uid']) is not int
            or type(evidence['duration_ms']) is not int or not 0<=evidence['duration_ms']<=allocated_ms+3000
            or not isinstance(evidence['records'],list) or len(evidence['records'])!=len(request['contexts'])):
        raise ValueError('worker_clang_fallback_evidence_invalid')
    okay,version=_execution(evidence['version'],8000)
    if not okay or version.strip()!=VERSION.encode(): raise ValueError('worker_clang_fallback_tool_version')
    if header_provenance:
        try:tool_raw=base64.b64decode(evidence['header_tool_receipt'],validate=True)
        except (ValueError,TypeError) as error:raise ValueError('worker_clang_fallback_header_tool_invalid') from error
        if _digest(tool_raw)!=evidence['header_tool_receipt_sha256']:
            raise ValueError('worker_clang_fallback_header_tool_invalid')
        validate_clang_header_tool_receipt(tool_raw)
        if (request['header_source_targets']!=primary_request['targets']
                or request['header_generated_files']!=primary_request['generated_files']
                or request['header_tool_manifest_sha256']!=CLANG_HEADER_MANIFEST_SHA256):
            raise ValueError('worker_clang_fallback_header_binding_invalid')
    native_sha=_digest(raw); primary_by_id={row['context_id']:row for row in primary_request['contexts']}
    analyzed=[]; findings=[]; limitations=[]; attempted=[]; headers=[]; duration=evidence['version']['duration_ms']
    for planned,row in zip(request['contexts'],evidence['records']):
        row_fields={'context_id','invocation','dropped_arguments','execution','plist','plist_sha256','error'}
        if header_provenance:row_fields|={'header_trace','header_trace_sha256'}
        if (not isinstance(row,dict) or set(row)!=row_fields
                or row['context_id']!=planned['context_id'] or row['invocation']!=planned['invocation']
                or row['dropped_arguments']!=planned['dropped_arguments']
                or row['error'] is not None and (not isinstance(row['error'],str) or re.fullmatch(r'worker_clang_fallback_[a-z_]+',row['error']) is None)):
            raise ValueError('worker_clang_fallback_record_invalid')
        context=primary_by_id[row['context_id']]
        header=None
        if header_provenance and row['header_trace']:
            trace=_decode_plist(row['header_trace'],row['header_trace_sha256'])
            if len(trace)>CLANG_HEADER_LIMIT:raise ValueError('worker_clang_fallback_header_limit')
            header_locations={'/work/source/'+p:('original',p,sha) for p,sha in primary_request['targets'].items()}
            header_locations.update({'/work/analysis/generated-baseline/'+p:('generated',p,item['sha256'])
                for p,item in primary_request['generated_files'].items()})
            header=validate_clang_header_trace(trace,source=context['analysis_file'],context_id=context['context_id'],
                locations=header_locations,standard=_clang_standard(context))
            header.update(native_execution_verified=False,header_tool_manifest_sha256=CLANG_HEADER_MANIFEST_SHA256,
                header_tool_receipt_sha256=evidence['header_tool_receipt_sha256'])
            headers.append(header)
        elif header_provenance and row['header_trace_sha256'] is not None:
            raise ValueError('worker_clang_fallback_header_missing')
        if row['execution'] is None:
            if row['error'] is None or row['plist'] or row['plist_sha256'] is not None or header: raise ValueError('worker_clang_fallback_missing_execution')
            limitations.append({'context_id':row['context_id'],'rule_id':row['error'],'analyzer':'clang-static-analyzer'}); continue
        success,_=_execution(row['execution'],(limits['case_seconds']+3)*1000); duration+=row['execution']['duration_ms']; attempted.append(row['context_id'])
        if not success or row['error']:
            limitations.append({'context_id':row['context_id'],'rule_id':row['error'] or 'clang_native_execution_incomplete','analyzer':'clang-static-analyzer'}); continue
        if not row['plist'] or row['plist_sha256'] is None:
            limitations.append({'context_id':row['context_id'],'rule_id':'clang_native_output_missing','analyzer':'clang-static-analyzer'}); continue
        try: document=plistlib.loads(_decode_plist(row['plist'],row['plist_sha256']))
        except Exception as exc: raise ValueError('worker_clang_fallback_plist_invalid') from exc
        if not isinstance(document,dict) or not isinstance(document.get('files'),list) or not isinstance(document.get('diagnostics'),list):
            raise ValueError('worker_clang_fallback_plist_invalid')
        locations={'/work/source/'+p:('original',p,sha) for p,sha in context['source_dependencies'].items()}
        locations.update({'/work/analysis/generated-baseline/'+p:('generated',p,sha) for p,sha in context['generated_dependencies'].items()})
        files=document['files']; blocked=False
        for diagnostic in document['diagnostics']:
            if not isinstance(diagnostic,dict) or not isinstance(diagnostic.get('location'),dict): raise ValueError('worker_clang_fallback_diagnostic_invalid')
            location=diagnostic['location']; index=location.get('file')
            if type(index) is not int or not 0<=index<len(files) or files[index] not in locations:
                limitations.append({'context_id':row['context_id'],'rule_id':'clang_diagnostic_location_unbound','analyzer':'clang-static-analyzer','message':str(diagnostic.get('description') or '')[:500]}); blocked=True; continue
            origin,path,sha=locations[files[index]]
            rule=str(diagnostic.get('check_name') or diagnostic.get('type') or 'clang-analyzer')[:200]
            message=str(diagnostic.get('description') or diagnostic.get('type') or '')[:2000]
            line=location.get('line'); column=location.get('col')
            if type(line) is not int or line<1 or type(column) is not int or column<1: raise ValueError('worker_clang_fallback_diagnostic_invalid')
            finding={'rule_id':rule,'path':path,'line':line,'column':column,
                'locations':[{'origin':origin,'path':path,'source_sha256':sha,'line':line,'column':column}],
                'message':message,'severity':'unknown','native_severity':'warning','cwe':None,'inconclusive':False,
                'classification':'review_required_candidate','specialist_review_completed':False,'origin':origin,
                'source_sha256':sha,'context_id':row['context_id'],'native_evidence_sha256':native_sha,'analyzer':'clang-static-analyzer'}
            finding['id']='cpp-clang-context-'+_digest(_canonical({k:v for k,v in finding.items() if k!='native_evidence_sha256'})); findings.append(finding)
        if not blocked:
            analyzed.append(row['context_id'])
            if header is not None:header['native_execution_verified']=True
            if header_provenance and (header is None or not header['normal_pass_completed']):
                limitations.append({'context_id':row['context_id'],'rule_id':'clang_header_observation_incomplete','analyzer':'clang-static-analyzer'})
    if duration>evidence['duration_ms']*diagnostic_parallel+1000: raise ValueError('worker_clang_fallback_duration_invalid')
    return {'required_contexts':[c['context_id'] for c in request['contexts']],'attempted_contexts':attempted,
        'analyzed_contexts':analyzed,'complete':len(analyzed)==len(request['contexts']),'findings':findings,
        'limitations':limitations,'native_evidence_sha256':native_sha,'static_analysis_executed':bool(attempted),'tool_version':VERSION,
        **({'header_context_evidence':headers,'header_tool_manifest_sha256':CLANG_HEADER_MANIFEST_SHA256} if header_provenance else {}),
        **({'header_completion_policy':'unit-and-header-completion-v1'} if request['schema']=='nico.cpp-clang-fallback-request.v7' else {})}
