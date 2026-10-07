"""Owned source-only controls. Root executes; no Git/Docker/provider/target calls."""
from __future__ import annotations
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = pathlib.Path(__file__).parents[1] / 'scripts'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORTER = load('owned_sample_exporter', SCRIPTS / 'cpp_full_static_diagnostic_export.py')
CALLER = load('owned_envelope_retention_caller', SCRIPTS / 'cpp_same_image_full_static_diagnostic.py')


def sample_path():
    return SCRIPTS / 'cpp_fallback_capacity_sample.py'


class EnvelopeRetentionControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.addCleanup(self.temp.cleanup)

    def test_exact_stdin_buffer_is_retained_and_readback_bound(self):
        raw, reference = CALLER.retain_sample_envelope(self.root, {'x': [1, 2]}, {'scope': False})
        self.assertEqual(raw, CALLER.canonical({'request': {'x': [1, 2]}, 'binding': {'scope': False}}))
        self.assertEqual((self.root / reference['path']).read_bytes(), raw)
        self.assertEqual(reference, {'path': 'sample-envelope.json', 'bytes': len(raw), 'sha256': CALLER.sha(raw)})
        self.assertEqual((self.root / reference['path']).stat().st_mode & 0o777, 0o600)

    def test_envelope_cannot_overwrite_existing_file(self):
        CALLER.retain_sample_envelope(self.root, {}, {})
        with self.assertRaises(FileExistsError):
            CALLER.retain_sample_envelope(self.root, {'changed': True}, {})

    def test_existing_symlink_cannot_redirect_envelope(self):
        outside = self.root / 'untouched'
        outside.write_bytes(b'unchanged')
        (self.root / 'sample-envelope.json').symlink_to(outside)
        with self.assertRaises(FileExistsError):
            CALLER.retain_sample_envelope(self.root, {}, {})
        self.assertEqual(outside.read_bytes(), b'unchanged')

    def test_public_directory_is_rejected_before_write(self):
        self.root.chmod(0o755)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.retain_sample_envelope(self.root, {}, {})
        self.assertFalse((self.root / 'sample-envelope.json').exists())

    def test_oversized_envelope_rejected_before_write(self):
        with patch.object(CALLER, 'MAX_META', 32):
            with self.assertRaises(CALLER.CallerRejected):
                CALLER.retain_sample_envelope(self.root, {'data': 'x' * 64}, {})
        self.assertFalse((self.root / 'sample-envelope.json').exists())


class ClosedExporterControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.expected = {'caller_sha256': EXPORTER.digest((SCRIPTS / 'cpp_same_image_full_static_diagnostic.py').read_bytes()),
                         'sample_sha256': EXPORTER.digest(sample_path().read_bytes())}
        self.validators, self.codes, self.source_checks = EXPORTER.sample_source_validation(
            SCRIPTS / 'cpp_same_image_full_static_diagnostic.py', sample_path(), self.expected)
        ids = [hashlib.sha256(('owned-context-' + str(i)).encode()).hexdigest() for i in range(577)]
        targets = {'src/file_' + str(i) + '.cpp': 'a' * 64 for i in range(3031)}
        generated = {'gen/' + str(i) + '.h': {'bytes': 1, 'sha256': 'b' * 64} for i in range(143)}
        contexts = [{'index': i, 'context_id': ids[i], 'analysis_file': '/work/source/src/file_' + str(i) + '.cpp',
            'invocation': ['clang', '/work/source/src/file_' + str(i) + '.cpp'], 'dropped_arguments': [],
            'source_dependencies': {'src/file_' + str(i) + '.cpp': 'a' * 64}, 'generated_dependencies': {}}
            for i in EXPORTER.SAMPLE_INDEXES]
        self.request = {'schema': 'nico.cpp-clang-fallback-request.v7', 'tool_version': '17.0.6',
            'contexts': contexts, 'required_contexts': ids, 'primary_analyzed_contexts': ids[:479],
            'header_source_targets': targets, 'header_generated_files': generated,
            'header_tool_manifest_sha256': 'b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8',
            'primary_request_sha256': 'c' * 64, 'cppcheck_evidence_sha256': 'd' * 64,
            'compiler_evidence_sha256': 'e' * 64, 'compiler_environment_sha256': 'f' * 64,
            'limits': {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}}
        self.binding = {'schema': 'nico.diagnostic.four-fallback-selection.v1',
            'full_request_sha256': EXPORTER.SAMPLE_FULL_REQUEST,
            'sample_request_sha256': EXPORTER.digest(EXPORTER.canonical(self.request)),
            'required_contexts_sha256': EXPORTER.digest(EXPORTER.canonical(ids)),
            'full_fallback_context_ids_sha256': '1' * 64,
            'header_source_targets_sha256': EXPORTER.digest(EXPORTER.canonical(targets)),
            'header_generated_files_sha256': EXPORTER.digest(EXPORTER.canonical(generated)),
            'sample_contexts_sha256': EXPORTER.digest(EXPORTER.canonical(contexts)),
            'selected': [{'index': c['index'], 'context_id': c['context_id'],
                'invocation_sha256': EXPORTER.digest(EXPORTER.canonical(c['invocation'])),
                'source_dependencies_sha256': EXPORTER.digest(EXPORTER.canonical(c['source_dependencies'])),
                'generated_dependencies_sha256': EXPORTER.digest(EXPORTER.canonical(c['generated_dependencies']))}
                for c in contexts],
            'obligations': {'full_contexts': 577, 'full_fallback_contexts': 576, 'sampled_contexts': 4,
                'unsampled_fallback_contexts': 572, 'unsampled_status': 'UNMEASURED',
                'source_files': 3031, 'snapshot_files': 143, 'generated_units': 42},
            'full_native_qualified': False, 'production_qualified': False, 'cache_state': 'UNKNOWN'}
        self.envelope = {'request': self.request, 'binding': self.binding}
        self.diagnostic = {'sample_binding': self.binding, 'request_binding': {
            'full_request_bound_before_selection': True, 'no_primary_native_execution': True,
            'full_required_fallback_contexts': 576, 'selected_context_indices': EXPORTER.SAMPLE_INDEXES,
            'selected_original_indices': EXPORTER.SAMPLE_INDEXES,
            'selected_context_ids': [c['context_id'] for c in contexts],
            'full_header_source_population': 3031, 'full_header_generated_population': 143,
            'full_fallback_request_sha256': self.binding['full_request_sha256'],
            'sample_request_sha256': self.binding['sample_request_sha256']}}
        for key, value in [('SAMPLE_TARGET_POPULATION', self.binding['header_source_targets_sha256']),
                           ('SAMPLE_GENERATED_POPULATION', self.binding['header_generated_files_sha256'])]:
            patcher = patch.object(EXPORTER, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_checked_source_loads_only_pure_data_definitions(self):
        self.assertIn('validate_sample_telemetry', self.validators)
        self.assertNotIn('run_capacity_sample', self.validators)
        self.assertNotIn('collect_clang_fallback', self.validators)
        self.assertNotIn('build_worker_program', self.validators)

    def program(self):
        return {'original_function_buffers_verified': True, 'producer_source_pins': self.validators['SOURCE_PINS'],
                'sample_module_sha256': self.expected['sample_sha256'], 'new_terminal_only': True,
                'full_native_qualified': False, 'original_program_sha256': '1' * 64,
                'sample_program_sha256': '2' * 64, 'original_prefix_sha256': '3' * 64}

    def test_program_binding_retains_independently_expected_module_sha(self):
        projected = EXPORTER.sample_program_projection(self.program(), self.validators, self.expected)
        self.assertEqual(projected['sample_module_sha256'], self.expected['sample_sha256'])

    def test_program_binding_missing_module_sha_rejected(self):
        program = self.program()
        del program['sample_module_sha256']
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_program_projection(program, self.validators, self.expected)

    def test_program_binding_wrong_module_sha_rejected(self):
        program = self.program()
        program['sample_module_sha256'] = '0' * 64
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_program_projection(program, self.validators, self.expected)

    def test_wrong_sampler_whole_hash_rejected(self):
        expected = dict(self.expected, sample_sha256='0' * 64)
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_source_validation(SCRIPTS / 'cpp_same_image_full_static_diagnostic.py', sample_path(), expected)

    def test_same_length_source_mutation_rejected(self):
        changed = self.root / 'changed_sample.py'
        raw = sample_path().read_bytes()
        changed.write_bytes(raw[:-1] + (b' ' if raw[-1:] != b' ' else b'\n'))
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_source_validation(SCRIPTS / 'cpp_same_image_full_static_diagnostic.py', changed, self.expected)

    def test_selected_request_is_verified_without_copying_private_body(self):
        request, binding, projected = EXPORTER.sample_request_projection(self.envelope, self.diagnostic, self.validators)
        self.assertEqual([row['index'] for row in projected['selected']], [0, 58, 154, 186])
        self.assertNotIn('invocation', projected['selected'][0])
        self.assertNotIn('source_dependencies', projected['selected'][0])
        self.assertFalse(projected['full576_request_bytes_exported'])

    def test_changed_argv_rejected_by_bound_envelope(self):
        self.request['contexts'][0]['invocation'].append('--repair')
        with self.assertRaises(ValueError):
            EXPORTER.sample_request_projection(self.envelope, self.diagnostic, self.validators)

    def test_typed_false_index_is_rejected(self):
        self.binding['selected'][0]['index'] = False
        with self.assertRaises(ValueError):
            EXPORTER.sample_request_projection(self.envelope, self.diagnostic, self.validators)

    def test_wrong_full_request_hash_rejected(self):
        self.binding['full_request_sha256'] = '0' * 64
        self.diagnostic['request_binding']['full_fallback_request_sha256'] = '0' * 64
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_request_projection(self.envelope, self.diagnostic, self.validators)

    def test_coded_native_failure_preserved_without_analysis_credit(self):
        raw = EXPORTER.canonical({'schema': 'nico.cpp-clang-fallback-failure.v1', 'error': 'worker_clang_fallback_unavailable'})
        value = EXPORTER.sample_native_projection(raw, self.request, 480000)
        self.assertTrue(value['raw_exportable'])
        self.assertFalse(value['analysis_or_population_credit'])

    def test_arbitrary_failure_text_is_hash_only(self):
        raw = EXPORTER.canonical({'schema': 'nico.cpp-clang-fallback-failure.v1', 'error': 'private arbitrary traceback text'})
        value = EXPORTER.sample_native_projection(raw, self.request, 480000)
        self.assertFalse(value['raw_exportable'])
        self.assertNotIn('private arbitrary', json.dumps(value))

    def test_unparseable_stdout_cannot_become_analysis_credit(self):
        value = EXPORTER.sample_native_projection(b'Traceback: private text', self.request, 480000)
        self.assertFalse(value['raw_exportable'])
        self.assertFalse(value['analysis_or_population_credit'])

    def test_error_catalog_is_typed_and_unknown_message_is_opaque(self):
        code = next(iter(self.codes))
        value = EXPORTER.sample_error_projection({'type': 'CallerRejected', 'message': code}, self.codes)
        self.assertEqual(value['validation_code'], code)
        wrong = EXPORTER.sample_error_projection({'type': 'OSError', 'message': code}, self.codes)
        self.assertNotEqual(wrong['validation_code'], code)
        secret = EXPORTER.sample_error_projection({'type': 'CallerRejected', 'message': 'private exception text'}, self.codes)
        self.assertNotIn('private exception text', json.dumps(secret))

    def telemetry(self, *, status='UNPROVEN', wall=600000):
        child = {'status': 'UNKNOWN', 'user_seconds': None, 'system_seconds': None,
            'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER', 'observation_ms': 1}
        group = {'scope': 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT',
            'files': {name: {'status': 'UNKNOWN', 'values': None} for name in self.validators['CGROUP_FILES']}, 'observation_ms': 1}
        return {'schema': 'nico.diagnostic.four-fallback-resources.v1', 'status': status,
            'collector_error_type': 'ValueError' if status == 'UNPROVEN' else None,
            'selection': self.binding, 'limits': {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2},
            'collector_call_wall_ms': wall, 'actual_wall_budget_ms': 480000,
            'collector_wall_scope': 'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS',
            'children': {'scope': child['scope'], 'includes_version_probe': True, 'per_context_cpu_available': False,
                'before': child, 'after': copy.deepcopy(child), 'delta_status': 'UNKNOWN', 'delta': None},
            'cgroup': {'before': group, 'after': copy.deepcopy(group),
                'delta': {name: {'status': 'UNKNOWN', 'values': None} for name in self.validators['CGROUP_FILES']}},
            'evidence_sha256': None, 'full_native_qualified': False, 'production_qualified': False,
            'historical_replay_credit': False, 'cache_state': 'UNKNOWN', 'unsampled_status': 'UNMEASURED'}

    def test_failed_late_typed_sidecar_retains_actual_status_without_positive_credit(self):
        raw = EXPORTER.canonical(self.telemetry())
        native = EXPORTER.canonical({'schema': 'nico.cpp-clang-fallback-failure.v1', 'error': 'worker_clang_fallback_unavailable'})
        value = EXPORTER.sample_retained_telemetry(raw, self.envelope, native, 480000, self.validators)
        self.assertEqual(value['status'], 'UNPROVEN')
        self.assertEqual(value['collector_call_wall_ms'], 600000)
        self.assertIsNone(value['evidence_sha256'])
        with self.assertRaises(ValueError):
            self.validators['validate_sample_telemetry'](raw, self.envelope, native, actual_wall_budget_ms=480000)

    def test_counter_delta_invention_rejected(self):
        telemetry = self.telemetry()
        telemetry['cgroup']['delta']['memory.events'] = {'status': 'OBSERVED_DELTA', 'values': {'oom_kill': 1}}
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_retained_telemetry(EXPORTER.canonical(telemetry), self.envelope, b'{}', 480000, self.validators)

    def test_private_exception_field_in_sidecar_rejected(self):
        telemetry = self.telemetry()
        telemetry['error_message'] = 'arbitrary private exception'
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_retained_telemetry(EXPORTER.canonical(telemetry), self.envelope, b'{}', 480000, self.validators)

    def test_sidecar_cannot_upgrade_qualification_flag(self):
        telemetry = self.telemetry()
        telemetry['full_native_qualified'] = True
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.sample_retained_telemetry(EXPORTER.canonical(telemetry), self.envelope, b'{}', 480000, self.validators)

    def test_bound_write_export_checks_every_output_byte(self):
        output = self.root / 'export'
        body = b'{"schema":"owned_fresh_fact"}'
        receipt = EXPORTER.write_sample_export({'schema': 'owned_summary', 'full_native_qualified': False},
            {'artifacts/owned.json': body}, output, [], 'a' * 64)
        manifest = json.loads((output / 'manifest.json').read_bytes())
        for row in manifest['files']:
            raw = (output / row['path']).read_bytes()
            self.assertEqual(row['bytes'], len(raw))
            self.assertEqual(row['sha256'], EXPORTER.digest(raw))
        self.assertFalse(receipt['full_native_or_production_qualification'])
        self.assertFalse((output / 'sample-envelope.json').exists())

    def test_public_summary_refuses_private_host_material(self):
        with self.assertRaises(EXPORTER.Rejected):
            EXPORTER.write_sample_export({'schema': 'owned', 'path': '/workspace/private'}, {}, self.root / 'bad', [], 'a' * 64)


class MissingReceiptControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.receipt = self.root / 'private' / 'sample-caller-receipt.json'
        self.expected = {'caller_receipt_sha256': None, 'current_git_head': 'a' * 40,
            'effective_fallback_baseline': 'f0919654edd719059ea03319981b13f46ba70a88',
            'compiler_overlay_path': 'nico/assessment_cpp_project_compiler.py',
            'compiler_overlay_sha256': EXPORTER.SAMPLE_COMPILER,
            'exporter_sha256': EXPORTER.digest((SCRIPTS / 'cpp_full_static_diagnostic_export.py').read_bytes()),
            'caller_sha256': EXPORTER.digest((SCRIPTS / 'cpp_same_image_full_static_diagnostic.py').read_bytes()),
            'scope_sha256': 'b' * 64, 'sample_sha256': EXPORTER.digest(sample_path().read_bytes()),
            'image_config_digest': EXPORTER.FIXED_IMAGE}

    def invoke(self):
        return EXPORTER.export_missing_sample(self.receipt, self.root / 'export', self.expected,
            caller_source=SCRIPTS / 'cpp_same_image_full_static_diagnostic.py', sample_source=sample_path())

    def test_missing_receipt_records_absence_without_image_target_execution_or_cause(self):
        self.invoke()
        summary = json.loads((self.root / 'export/sample-summary.json').read_bytes())
        self.assertTrue(summary['caller_receipt_observed_absent'])
        self.assertIsNone(summary['caller_receipt_sha256'])
        self.assertIsNone(summary['image_binding'])
        self.assertIsNone(summary['target_binding'])
        self.assertIsNone(summary['missing_receipt_cause'])
        self.assertEqual(summary['actual_operations'], [])
        self.assertEqual(summary['source_image_target_execution_observation_status'], 'UNKNOWN')
        self.assertFalse(summary['full_native_qualified'])

    def test_missing_mode_rejects_actual_existing_receipt(self):
        self.receipt.parent.mkdir()
        self.receipt.write_bytes(b'{}')
        with self.assertRaises(EXPORTER.Rejected):
            self.invoke()
        self.assertFalse((self.root / 'export').exists())

    def test_missing_mode_rejects_supplied_receipt_sha(self):
        self.expected['caller_receipt_sha256'] = 'c' * 64
        with self.assertRaises(EXPORTER.Rejected):
            self.invoke()
        self.assertFalse((self.root / 'export').exists())

    def test_missing_mode_rejects_dangling_symlink_receipt(self):
        self.receipt.parent.mkdir()
        self.receipt.symlink_to(self.root / 'absent')
        with self.assertRaises(EXPORTER.Rejected):
            self.invoke()
        self.assertFalse((self.root / 'export').exists())

    def test_missing_mode_still_rejects_wrong_actual_source_hash(self):
        self.expected['sample_sha256'] = '0' * 64
        with self.assertRaises(EXPORTER.Rejected):
            self.invoke()
        self.assertFalse((self.root / 'export').exists())

    def test_pair_mode_cannot_use_missing_receipt_flag(self):
        argv = ['exporter', '--caller-receipt', str(self.receipt), '--output', str(self.root / 'export'),
                '--missing-caller-receipt']
        for key, value in self.expected.items():
            if key != 'sample_sha256' and value is not None:
                argv.extend(['--expected-' + key.replace('_', '-'), value])
        with patch.object(sys, 'argv', argv), patch.object(EXPORTER, 'export_pair') as pair:
            with self.assertRaises(SystemExit) as error:
                EXPORTER.main()
        self.assertEqual(error.exception.code, 2)
        pair.assert_not_called()


if __name__ == '__main__':
    unittest.main()
