"""Inert pair policy controls. No provider, native process or host execution."""
import ast
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
import py_compile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PAIR = load('owned_parallel_pair', ROOT / 'scripts/cpp_fallback_parallel_pair.py')
FIXTURES = load('owned_pair_fixtures', ROOT / 'tests/test_cpp_fallback_capacity_sample.py')


def inputs():
    request, evidence, summary = FIXTURES.owned_inputs()
    expected = [PAIR.selected_identity(request['contexts'][index]) for index in (58, 114, 153, 154)]
    identity = dict(PAIR.EXECUTION_IDENTITY)
    return request, PAIR.canonical(evidence), summary, expected, identity


def preflight(values=None):
    request, raw, summary, selected, identity = inputs() if values is None else values
    return PAIR.preflight_pair(request, raw, expected_fallback_sha256=PAIR.sha(raw),
        prepared_summary=summary, expected_selected=selected, execution_identity=identity)


def native(envelope):
    return {'schema': 'nico.cpp-clang-fallback-evidence.v7',
        'request_sha256': PAIR.sha(PAIR.canonical(envelope['request'])),
        'records': [{'context_id': row['context_id'], 'invocation': row['invocation'],
            'dropped_arguments': row['dropped_arguments'], 'execution': None,
            'error': 'worker_clang_fallback_deadline', 'plist': '', 'plist_sha256': None,
            'header_trace': '', 'header_trace_sha256': None} for row in envelope['request']['contexts']],
        'duration_ms': 12, 'version': {'duration_ms': 2}}


class PairSelectionTests(unittest.TestCase):
    def test_expected_selected_exact_identity_both_arms_preflight(self):
        values = inputs();before = copy.deepcopy(values)
        envelopes, binding = preflight(values)
        self.assertEqual(values, before)
        self.assertEqual(tuple(row['diagnostic_parallel'] for row in envelopes), (2, 4))
        self.assertEqual(envelopes[0]['request'], envelopes[1]['request'])
        self.assertEqual(envelopes[0]['binding'], envelopes[1]['binding'])
        self.assertEqual([row['index'] for row in envelopes[0]['request']['contexts']], [58, 114, 153, 154])
        self.assertEqual(envelopes[1]['request']['limits'], {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2})
        self.assertFalse(binding['full_native_qualified'])
        self.assertFalse(binding['production_qualified'])
        self.assertEqual(binding['obligations']['unsampled_fallback_contexts'], 572)
        self.assertEqual(binding['execution_identity']['stage_seconds_per_arm'], 1020)

    def test_private_expected_identity_is_not_inferred_from_index(self):
        for field in ('context_id', 'invocation_sha256', 'source_dependencies_sha256', 'generated_dependencies_sha256'):
            values = list(inputs());values[3][1][field] = '0' * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'pair_private_selected_binding'):
                preflight(values)

    def test_raw_retained_hash_binding(self):
        values = inputs()
        with self.assertRaisesRegex(ValueError, 'pair_retained_evidence'):
            PAIR.preflight_pair(values[0], values[1], expected_fallback_sha256='0' * 64,
                prepared_summary=values[2], expected_selected=values[3], execution_identity=values[4])

    def test_full_retained_request_binding(self):
        values = list(inputs());values[0]['contexts'][114]['invocation'].append('-DOWNED_CHANGED=1')
        values[3][1] = PAIR.selected_identity(values[0]['contexts'][114])
        with self.assertRaisesRegex(ValueError, 'sample_reconstructed_request_binding'):
            preflight(values)

    def test_admission_four_is_not_a_production_request(self):
        for parallel in (4, True, 2.0):
            values = list(inputs());values[0]['limits']['parallel'] = parallel
            with self.subTest(parallel=parallel), self.assertRaisesRegex(ValueError, 'sample_request_policy'):
                preflight(values)
        # Inspect the pinned production admission policy without importing
        # NICO or installing its runtime dependencies in these inert controls.
        buffers = FIXTURES.source_buffers()
        raw = buffers['nico/assessment_cpp_clang_fallback.py']
        self.assertEqual(PAIR.sha(raw), PAIR.SAMPLE.SOURCE_PINS['nico/assessment_cpp_clang_fallback.py'])
        tree = ast.parse(raw)
        low = next(node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'LOW_CONTENTION_LIMITS' for target in node.targets))
        self.assertEqual(ast.literal_eval(low), {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2})
        admission = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name == '_request_limits')
        v7 = ast.parse("versions['nico.cpp-clang-fallback-request.v7']=LOW_CONTENTION_LIMITS").body[0]
        self.assertTrue(any(ast.dump(node) == ast.dump(v7) for node in admission.body))
        expected_guards = (
            ast.parse('limits != expected', mode='eval').body,
            ast.parse('type(value) is not int', mode='eval').body,
        )
        for guard in expected_guards:
            self.assertTrue(any(ast.dump(node) == ast.dump(guard) for node in ast.walk(admission)))
        request = preflight()[0][1]['request']
        self.assertEqual(request['limits'], ast.literal_eval(low))
        request['limits']['parallel'] = 4
        self.assertNotEqual(request['limits'], ast.literal_eval(low))
        prefix = PAIR.SAMPLE.verified_program_prefix(FIXTURES.data_only_program(buffers), buffers)
        worker_admission = next(node for node in ast.parse(prefix).body
            if isinstance(node, ast.FunctionDef) and node.name == '_request_limits')
        self.assertEqual(ast.dump(worker_admission), ast.dump(admission))

    def test_diagnostic_parallel_exact_integer(self):
        for parallel in (True, False, 1, 3, 8, 2.0, '4', None):
            with self.subTest(parallel=parallel), self.assertRaisesRegex(ValueError, 'pair_diagnostic_parallel'):
                PAIR.scheduling_parallel(parallel)

    def test_runner_budget_must_not_be_expanded_or_reinterpreted(self):
        for field, invalid in (('outer_seconds', 156 * 60), ('stage_seconds_per_arm', 2040), ('cpu', True),
                               ('memory_bytes', 0), ('image_digest', 'owned:latest')):
            values = list(inputs());values[4][field] = invalid
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'pair_execution_identity'):
                preflight(values)

    def test_exact_resources_and_runtime_identity_reject_changes(self):
        for key, value in (('cpu', 2), ('cpu', 8), ('memory_bytes', 8 * 1024 ** 3),
                           ('memory_bytes', 16 * 1024 ** 3), ('runner_class', 'ubuntu-latest'),
                           ('isolation', 'unconfined'), ('image_digest', 'sha256:' + '0' * 64)):
            values = list(inputs());values[4][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'pair_execution_identity'):
                preflight(values)
            envelope = preflight()[0][0]
            envelope['binding']['execution_identity'][key] = value
            with self.subTest(runtime=key, value=value), self.assertRaisesRegex(ValueError, 'pair_execution_identity'):
                PAIR.check_pair_envelope(envelope)

    def test_sampler_ignores_hostile_bytecode_and_keeps_verified_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'sample.py'
            source.write_text('raise RuntimeError("hostile_bytecode")\n')
            py_compile.compile(str(source), doraise=True)
            source.write_bytes(PAIR.SAMPLE_RAW)
            module, raw = PAIR.verified_sample(source)
            source.write_text('raise RuntimeError("replaced_after_verification")\n')
            self.assertEqual(raw, PAIR.SAMPLE_RAW)
            self.assertEqual(module.LIMITS, PAIR.PAIR_LIMITS)
            with self.assertRaisesRegex(ValueError, 'pair_sample_source_identity'):
                PAIR.verified_sample(source)

    def test_header_generated_obligations_are_immutable(self):
        envelopes, _ = preflight()
        changed = copy.deepcopy(envelopes[1]);changed['request']['header_generated_files'].pop('g0.h')
        with self.assertRaisesRegex(ValueError, 'pair_runtime_binding'):
            PAIR.check_pair_envelope(changed)


class PairProgramTests(unittest.TestCase):
    def test_same_program_preserves_original_production_prefix_and_narrow_clone(self):
        buffers = FIXTURES.source_buffers();original = FIXTURES.data_only_program(buffers)
        program, proof = PAIR.build_worker_program(original, buffers,
            expected_sample_sha256=PAIR.sha(Path(PAIR.SAMPLE.__file__).read_bytes()),
            expected_pair_sha256=PAIR.sha(Path(PAIR.__file__).read_bytes()))
        prefix = PAIR.SAMPLE.verified_program_prefix(original, buffers)
        self.assertTrue(program.startswith(prefix))
        tree = ast.parse(program)
        clones = [row for row in tree.body if isinstance(row, ast.FunctionDef)
            and row.name == 'collect_diagnostic_parallel_fallback']
        self.assertEqual(len(clones), 1)
        self.assertEqual(ast.dump(clones[0]), ast.dump(ast.parse(PAIR.diagnostic_collector_source(prefix)).body[0]))
        self.assertTrue(proof['same_program_both_arms'])
        self.assertTrue(proof['diagnostic_decoder']['parser_header_failure_checks_unchanged'])
        # The diagnostic extension must not rebind production admission limits.
        added = ast.parse(program[len(prefix):])
        targets = [t.id for node in added.body if isinstance(node, ast.Assign)
            for t in node.targets if isinstance(t, ast.Name)]
        self.assertNotIn('LIMITS', targets)
        self.assertNotIn('LOW_CONTENTION_LIMITS', targets)
        self.assertNotIn('ThreadPoolExecutor', targets)
        self.assertNotIn('_request_limits', targets)

    def test_instrumentation_source_must_be_bound(self):
        buffers = FIXTURES.source_buffers();original = FIXTURES.data_only_program(buffers)
        with self.assertRaisesRegex(ValueError, 'pair_instrumentation_source_binding'):
            PAIR.build_worker_program(original, buffers, expected_sample_sha256='0' * 64,
                expected_pair_sha256=PAIR.sha(Path(PAIR.__file__).read_bytes()))

    def test_production_validator_parser_checks_are_ast_preserved(self):
        proof = PAIR.verify_diagnostic_validator(FIXTURES.source_buffers())
        self.assertEqual(proof['changes'], ['name', 'required_keyword_diagnostic_parallel', 'aggregate_worker_slot_duration_bound'])
        self.assertTrue(proof['production_admission_unchanged'])

    def test_production_helpers_import_only_inside_runtime_native_gate(self):
        tree = ast.parse(Path(PAIR.__file__).read_text())
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith('nico.')
            for node in tree.body))
        native_gate = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name == 'validate_pair_native')
        imports = [node for node in native_gate.body if isinstance(node, ast.ImportFrom)]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, 'nico.assessment_cpp_clang_fallback')
        self.assertEqual({alias.name for alias in imports[0].names}, {
            '_request_limits', '_execution', '_decode_plist', '_clang_standard', '_digest', '_canonical',
            'STREAM_LIMIT', 'VERSION', 'CLANG_HEADER_LIMIT', 'CLANG_HEADER_MANIFEST_SHA256',
            'validate_clang_header_tool_receipt', 'validate_clang_header_trace'})

    def test_no_dynamic_exec_eval_in_module(self):
        tree = ast.parse(Path(PAIR.__file__).read_text())
        names = [node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn('exec', names)
        self.assertNotIn('eval', names)


class PairTelemetryTests(unittest.TestCase):
    def fixture(self):
        envelope = preflight()[0][1]
        evidence = PAIR.canonical(native(envelope))
        group = FIXTURES.unknown_group()
        child = {'status': 'UNKNOWN', 'user_seconds': None, 'system_seconds': None,
            'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER', 'observation_ms': 0.1}
        telemetry = {'schema': 'nico.diagnostic.parallel-pair-resources.v1',
            'status': 'COLLECTOR_RETURNED', 'collector_error_type': None,
            'selection': envelope['binding'], 'limits': dict(PAIR.PAIR_LIMITS),
            'diagnostic_parallel': 4, 'envelope_sha256': PAIR.sha(PAIR.canonical(envelope)),
            'collector_call_wall_ms': 12, 'actual_wall_budget_ms': 480000,
            'collector_wall_scope': 'DIAGNOSTIC_PARALLEL_ONLY_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS',
            'children': {'scope': child['scope'], 'includes_version_probe': True, 'per_context_cpu_available': False,
                'before': child, 'after': copy.deepcopy(child), 'delta_status': 'UNKNOWN', 'delta': None},
            'cgroup': {'before': group, 'after': copy.deepcopy(group),
                'delta': PAIR.SAMPLE.counter_deltas(group, group)},
            'evidence_sha256': PAIR.sha(evidence), 'full_native_qualified': False,
            'production_qualified': False, 'historical_replay_credit': False,
            'cache_state': 'UNKNOWN', 'unsampled_status': 'UNMEASURED'}
        return envelope, evidence, telemetry

    def test_missing_resource_observations_stay_unknown(self):
        envelope, evidence, telemetry = self.fixture()
        value = PAIR.validate_pair_telemetry(PAIR.canonical(telemetry), envelope, evidence, actual_wall_budget_ms=480000)
        self.assertEqual(value['children']['delta_status'], 'UNKNOWN')
        self.assertFalse(value['production_qualified'])

    def test_telemetry_bound_to_actual_arm_and_native(self):
        for field, bad in (('diagnostic_parallel', 2), ('evidence_sha256', '0' * 64),
                           ('envelope_sha256', '0' * 64), ('production_qualified', True), ('actual_wall_budget_ms', True)):
            envelope, evidence, telemetry = self.fixture();telemetry[field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'pair_telemetry_identity'):
                PAIR.validate_pair_telemetry(PAIR.canonical(telemetry), envelope, evidence, actual_wall_budget_ms=480000)

    def test_unknown_counters_cannot_be_fabricated(self):
        envelope, evidence, telemetry = self.fixture()
        telemetry['cgroup']['before']['files']['memory.peak']['values'] = {'bytes': 1}
        with self.assertRaisesRegex(ValueError, 'pair_unknown_counter'):
            PAIR.validate_pair_telemetry(PAIR.canonical(telemetry), envelope, evidence, actual_wall_budget_ms=480000)



class PairComparisonTests(unittest.TestCase):
    def test_failure_equal_is_comparison_never_qualification(self):
        envelopes, _ = preflight()
        left = native(envelopes[0]);right = copy.deepcopy(left);right['duration_ms'] = 7
        right['version']['duration_ms'] = 1
        result = PAIR.compare_pair_outputs(PAIR.canonical(left), PAIR.canonical(right), envelopes)
        self.assertTrue(result['semantic_equal'])
        self.assertFalse(result['full_native_qualified'])
        self.assertFalse(result['production_qualified'])

    def test_header_output_and_findings_differences_are_retained(self):
        envelopes, _ = preflight()
        left = native(envelopes[0]);right = copy.deepcopy(left)
        right['records'][0]['header_trace_sha256'] = 'a' * 64
        result = PAIR.compare_pair_outputs(PAIR.canonical(left), PAIR.canonical(right), envelopes)
        self.assertFalse(result['semantic_equal'])
        self.assertFalse(result['contexts'][0]['header_trace_equal'])

    def test_changed_command_or_request_cannot_compare(self):
        envelopes, _ = preflight();left = native(envelopes[0]);right = copy.deepcopy(left)
        right['records'][1]['invocation'].append('-DOWNED_CHANGED=1')
        with self.assertRaisesRegex(ValueError, 'pair_native_context'):
            PAIR.compare_pair_outputs(PAIR.canonical(left), PAIR.canonical(right), envelopes)

    def test_swapped_pair_arms_rejected(self):
        envelopes, _ = preflight();raw = PAIR.canonical(native(envelopes[0]))
        with self.assertRaisesRegex(ValueError, 'pair_comparison_order'):
            PAIR.compare_pair_outputs(raw, raw, tuple(reversed(envelopes)))


if __name__ == '__main__':
    unittest.main()
