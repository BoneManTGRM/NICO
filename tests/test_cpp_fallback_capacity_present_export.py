"""Owned complete present-export data controls; author has NOT_RUN these.

Root runs against sibling continue37/candidate. No target, Git, provider,
Docker or native execution occurs. Receipt/image/target observations below
are synthetic fixture values, never evidence about a real qualification.
Only three exact owned request/population digest constants are patched.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SCRIPT_ROOT / 'scripts'
if not (SCRIPTS / 'cpp_same_image_full_static_diagnostic.py').is_file():
    # Source-only draft location; root copies this file unchanged into tests/.
    SCRIPTS = SCRIPT_ROOT / 'candidate' / 'scripts'
EXPORTER_PATH = SCRIPTS / 'cpp_full_static_diagnostic_export.py'
CALLER_PATH = SCRIPTS / 'cpp_same_image_full_static_diagnostic.py'
SAMPLE_PATH = SCRIPTS / 'cpp_fallback_capacity_sample.py'
SCOPE_PATH = SCRIPTS / 'cpp_static_runner_scope.py'


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


EXPORTER = load('owned_present_exporter', EXPORTER_PATH)
SAMPLE = load('owned_present_sampler', SAMPLE_PATH)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def execution(output=b'', duration=1):
    return {'exit_code': 0, 'timed_out': False, 'output_truncated': False,
            'duration_ms': duration, 'output': base64.b64encode(output).decode(),
            'output_sha256': sha(output)}


class PresentSampleExportControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.private = self.root / 'private'
        self.directory = self.private / 'context/runs/capacity-sample'
        self.directory.mkdir(parents=True, mode=0o700)
        self.artifacts = self.directory / 'artifacts'
        self.artifacts.mkdir(mode=0o700)
        self.receipt_path = self.private / 'sample-caller-receipt.json'
        self.output = self.root / 'export'
        self.assertEqual(sha(CALLER_PATH.read_bytes()),
            '60cb95c66f6141f6eedbe16cbe57630c4f577e9be56117e3d0ac8cb324edb6ae')
        self.assertEqual(sha(SAMPLE_PATH.read_bytes()),
            '6502680b08f124cfa417019647e7c42f873e7efa9017faa54efd52738cedfe1a')
        self.expected = {
            'current_git_head': 'a' * 40,
            'effective_fallback_baseline': 'f0919654edd719059ea03319981b13f46ba70a88',
            'compiler_overlay_path': 'nico/assessment_cpp_project_compiler.py',
            'compiler_overlay_sha256': EXPORTER.SAMPLE_COMPILER,
            'image_config_digest': EXPORTER.FIXED_IMAGE,
            'caller_sha256': sha(CALLER_PATH.read_bytes()),
            'sample_sha256': sha(SAMPLE_PATH.read_bytes()),
            'scope_sha256': sha(SCOPE_PATH.read_bytes()),
            'exporter_sha256': sha(EXPORTER_PATH.read_bytes()),
        }
        self.full_request = self.owned_full_request()
        full_evidence = {'schema': 'nico.cpp-clang-fallback-evidence.v7',
            'request_sha256': sha(canonical(self.full_request)),
            'records': [{'context_id': context['context_id'],
                'invocation': context['invocation'], 'dropped_arguments': context['dropped_arguments'],
                'execution': None, 'error': 'worker_clang_fallback_unstarted',
                'plist': '', 'plist_sha256': None, 'header_trace': '', 'header_trace_sha256': None}
                for context in self.full_request['contexts']]}
        full_raw = canonical(full_evidence)
        self.request, self.binding = SAMPLE.select_sample(self.full_request, full_raw,
            expected_fallback_sha256=sha(full_raw), prepared_summary={
                'source_population': 3031, 'snapshot_files': 143, 'generated_units': 42,
                'compiler_contexts': 577, 'historical_required_fallback_contexts': 576})
        self.envelope = {'request': self.request, 'binding': self.binding}
        for name, value in (
                ('SAMPLE_FULL_REQUEST', sha(canonical(self.full_request))),
                ('SAMPLE_TARGET_POPULATION', sha(canonical(self.full_request['header_source_targets']))),
                ('SAMPLE_GENERATED_POPULATION', sha(canonical(self.full_request['header_generated_files'])))):
            constant = patch.object(EXPORTER, name, value)
            constant.start()
            self.addCleanup(constant.stop)
        self.native = self.native_fixture()
        self.telemetry = self.telemetry_fixture()
        self.native_raw = canonical(self.native)
        self.telemetry_raw = canonical(self.telemetry)
        self.native_op = self.artifact_operation('fallback-capacity-sample', self.native_raw)
        self.telemetry_op = self.artifact_operation('fallback-capacity-telemetry', self.telemetry_raw)
        image_raw = canonical([{'Id': EXPORTER.FIXED_IMAGE}])
        self.image_op = {'id': 'static-image', **execution(image_raw),
            'invocation_sha256': sha(canonical(['owned-image-inspection'])),
            'output_bytes': len(image_raw), 'output_artifact': None}
        self.target = {'file_count': 3031, 'bytes': 49729651, 'tree_sha': EXPORTER.FROZEN_TREE,
            'all_original_sha256_git_blob_owner_and_any_executable_modes_verified': True,
            'repository': 'bitcoin/bitcoin', 'commit_sha': EXPORTER.FROZEN_HEAD,
            'data_only_copy_no_git': True, 'target_code_imported_compiled_or_run': False}
        child_target = {'file_count': 3031, 'bytes': 49729651, 'tree_sha': EXPORTER.FROZEN_TREE,
            'all_original_sha256_git_blob_executable_modes_verified': True}
        dependency = {'whole_proof': {'bytes': 10, 'sha256': sha(b'owned-data')},
            'actual_current_validation': {'owned_fixture': True}, 'proof_produced_in_this_process': False}
        interval = {'phase': 'owned_data_only_observation', 'wall_ms': 1, 'process_cpu_ms': 0,
            'clock_domain': 'this_process_perf_counter_and_process_time',
            'cpu_scope': 'This host process only; excludes analyzer/container and child-process CPU.'}
        source_rows = {}
        for key, path in EXPORTER.SAMPLE_SOURCE_PATHS.items():
            raw = (SCRIPTS / Path(path).name).read_bytes()
            source_rows[key] = {'path': path, 'bytes': len(raw), 'sha256': sha(raw), 'git_blob': git_blob(raw)}
        self.process = {'schema': 'nico.private.fallback_capacity_sample_process_receipt.v1',
            'variant': 'candidate', 'status': 'FRESH_SAMPLE_PROCESS_CAPTURED', 'error': None,
            'mock_injection_used': False, 'source_rows': source_rows, 'sample_invocation_attempted': True,
            'actual_python': {'version': '3.11.0 owned inert receipt', 'isolated': True, 'no_bytecode': True},
            'intervals': [interval], 'target_verification': child_target,
            'target_verification_after_sample': copy.deepcopy(child_target),
            **{key: copy.deepcopy(dependency) for key in (
                'dependency_before_preparation', 'dependency_before_sample', 'dependency_after_sample')},
            **{key: False for key in ('primary_native_execution', 'compiled', 'tests_executed',
                'full_native_qualified', 'production_qualified', 'assessment_completed')}}
        envelope_reference = self.write(self.directory / 'sample-envelope.json', canonical(self.envelope))
        envelope_reference['path'] = 'sample-envelope.json'
        self.diagnostic = {'schema': 'nico.private.fallback_capacity_sample_diagnostic.v1',
            'status': 'FOUR_CONTEXT_DIAGNOSTIC_CAPTURED', 'error': None, 'phase': 'cleanup',
            'duration_ms': 10, 'intervals': [interval], 'resource_profile': 'cpp-baseline-qualification-v1',
            'limits': dict(EXPORTER.SAMPLE_LIMITS), 'declared_api_wall_seconds': 1030,
            'boundary_verified': True, 'scratch_capacity_verified': True, 'cleanup_verified': True,
            'memory_peak_bytes': 1024, 'scratch_capacity_bytes': EXPORTER.SAMPLE_LIMITS['tmpfs_bytes'],
            'fallback_allocation_ms': 480000, 'sample_envelope': envelope_reference,
            'sample_binding': self.binding, 'operations': [self.image_op, self.native_op, self.telemetry_op],
            'request_binding': {'full_request_bound_before_selection': True, 'no_primary_native_execution': True,
                'full_required_fallback_contexts': 576, 'selected_context_indices': [0, 58, 154, 186],
                'selected_original_indices': [0, 58, 154, 186],
                'selected_context_ids': [row['context_id'] for row in self.request['contexts']],
                'full_header_source_population': 3031, 'full_header_generated_population': 143,
                'full_fallback_request_sha256': self.binding['full_request_sha256'],
                'sample_request_sha256': self.binding['sample_request_sha256']},
            'program_binding': {'original_function_buffers_verified': True,
                'producer_source_pins': dict(SAMPLE.SOURCE_PINS),
                'sample_module_sha256': self.expected['sample_sha256'], 'new_terminal_only': True,
                'full_native_qualified': False, 'original_program_sha256': sha(b'owned-original-program'),
                'sample_program_sha256': sha(b'owned-sample-program'),
                'original_prefix_sha256': sha(b'owned-prefix')},
            **{key: False for key in EXPORTER.SAMPLE_FALSE_DIAGNOSTIC}}
        self.outer = {'schema': 'nico.private.fallback_capacity_sample_caller.v1',
            'status': 'SAMPLE_PROCESS_AND_RETAINED_RESULT_CAPTURED', 'error': None, 'intervals': [interval],
            'source_binding': {'current_git_head': self.expected['current_git_head'],
                'effective_fallback_baseline': self.expected['effective_fallback_baseline'],
                'effective_recipe_tree': 'b9e200f62b9b2db9c6488326826ad8ae393418d0',
                'all_selected_files_actual_git_blob_bound': True, 'effective_overlay_is_whole_candidate': False,
                **{key: self.expected[key] for key in ('caller_sha256', 'scope_sha256', 'exporter_sha256', 'sample_sha256')},
                'compiler_overlay': {'path': self.expected['compiler_overlay_path'],
                    'sha256': self.expected['compiler_overlay_sha256']}},
            'image_binding': {'selected_config_digest': EXPORTER.FIXED_IMAGE,
                'fixed_config_digest': EXPORTER.FIXED_IMAGE, 'loaded_image_inspection_verified': True,
                'complete_archive_verified': True, 'config_and_ordered_rootfs_equal_independent_build_receipt': True,
                'single_verified_selected_image_for_sample': True, 'historical_image_recovered': False,
                'matching_historical_live_toolchain_or_header_inputs_inferred': False,
                'config_and_rootfs_sha256': sha(b'owned-config-rootfs'),
                'config_and_rootfs_verified_after_sample': True},
            'target_binding': self.target, 'selected_context_indices': [0, 58, 154, 186],
            'full_required_fallback_contexts': 576, 'single_sample_only': True, 'cache_state': 'UNKNOWN',
            'job_outer_budget_minutes': 155, 'declared_api_wall_seconds': 1030, 'shared_execution_seconds': 1020,
            'independent1030_hardwall_supervisor_present': False, 'parent_cpu_is_analyzer_cpu': False,
            'overlapping_intervals_additive': False,
            **{key: copy.deepcopy(dependency) for key in (
                'dependency_before_setup', 'dependency_before_process', 'dependency_after_sample')},
            **{key: False for key in EXPORTER.SAMPLE_FALSE_PARENT},
            'sample': {'id': 'capacity-sample', 'directory': str(self.directory), 'process_exit_code': 0,
                'fresh_cp311_isolated_process_requested': True, 'stdout': None, 'stderr': None}}
        self.refresh_receipts()

    def owned_full_request(self):
        ids = [sha(('owned-required-' + str(index)).encode()) for index in range(577)]
        targets = {'src/owned_' + str(index) + '.cpp': sha(('owned-source-' + str(index)).encode())
                   for index in range(3031)}
        generated = {'gen/owned_' + str(index) + '.h': {'bytes': 1, 'sha256': sha(('owned-generated-' + str(index)).encode())}
                     for index in range(143)}
        contexts = [{'index': index, 'context_id': ids[index],
            'analysis_file': '/work/source/src/owned_' + str(index) + '.cpp',
            'invocation': ['clang', '-cc1', '-analyze', '/work/source/src/owned_' + str(index) + '.cpp'],
            'dropped_arguments': [], 'source_dependencies': {
                'src/owned_' + str(index) + '.cpp': targets['src/owned_' + str(index) + '.cpp']},
            'generated_dependencies': {}} for index in range(576)]
        return {'schema': 'nico.cpp-clang-fallback-request.v7', 'tool_version': '17.0.6',
            'primary_request_sha256': sha(b'owned-primary-request'), 'cppcheck_evidence_sha256': sha(b'owned-primary'),
            'compiler_evidence_sha256': sha(b'owned-compiler'), 'compiler_environment_sha256': sha(b'owned-environment'),
            'required_contexts': ids, 'primary_analyzed_contexts': ids[:479], 'contexts': contexts,
            'limits': {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2},
            'header_tool_manifest_sha256': 'b867ac83a8bd89180cb03f6eb74dd9ef3fd4c36fad6ffa9cc292d995721219e8',
            'header_source_targets': targets, 'header_generated_files': generated}

    def native_fixture(self):
        tool = {'schema': 'nico.clang-header-tool.v1', 'manifest_sha256': self.request['header_tool_manifest_sha256'],
            'source_sha256': sha(b'owned-tool-source'), 'sdk_lock_sha256': sha(b'owned-sdk'),
            'runtime_lock_sha256': sha(b'owned-runtime'), 'clang_version': '17.0.6',
            'plugin_sha256': sha(b'owned-plugin'), 'compiler_version': 'owned-compiler-version',
            'qualification_completed': False}
        tool_raw = canonical(tool)
        plist = b'<?xml version="1.0"?><plist version="1.0"><dict><key>diagnostics</key><array/></dict></plist>'
        return {'schema': 'nico.cpp-clang-fallback-evidence.v7', 'request_sha256': sha(canonical(self.request)),
            'analyst_uid': 1001, 'version': execution(b'owned clang version 17.0.6'),
            'duration_ms': 4, 'wall_budget_ms': 480000,
            'header_tool_receipt': base64.b64encode(tool_raw).decode(), 'header_tool_receipt_sha256': sha(tool_raw),
            'records': [{'context_id': context['context_id'], 'invocation': context['invocation'],
                'dropped_arguments': context['dropped_arguments'], 'execution': execution(),
                'plist': base64.b64encode(zlib.compress(plist)).decode(), 'plist_sha256': sha(plist),
                'header_trace': '', 'header_trace_sha256': None, 'error': None}
                for context in self.request['contexts']]}

    def telemetry_fixture(self):
        child = {'status': 'UNKNOWN', 'user_seconds': None, 'system_seconds': None,
            'scope': 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER', 'observation_ms': 1}
        group = {'scope': 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT',
            'files': {name: {'status': 'UNKNOWN', 'values': None} for name in SAMPLE.CGROUP_FILES}, 'observation_ms': 1}
        return {'schema': 'nico.diagnostic.four-fallback-resources.v1', 'status': 'COLLECTOR_RETURNED',
            'collector_error_type': None, 'selection': self.binding, 'limits': dict(SAMPLE.LIMITS),
            'collector_call_wall_ms': 4, 'actual_wall_budget_ms': 480000,
            'collector_wall_scope': 'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS',
            'children': {'scope': child['scope'], 'includes_version_probe': True, 'per_context_cpu_available': False,
                'before': child, 'after': copy.deepcopy(child), 'delta_status': 'UNKNOWN', 'delta': None},
            'cgroup': {'before': group, 'after': copy.deepcopy(group),
                'delta': {name: {'status': 'UNKNOWN', 'values': None} for name in SAMPLE.CGROUP_FILES}},
            'evidence_sha256': sha(canonical(self.native)), 'full_native_qualified': False,
            'production_qualified': False, 'historical_replay_credit': False,
            'cache_state': 'UNKNOWN', 'unsampled_status': 'UNMEASURED'}

    def write(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)
        return {'bytes': len(raw), 'sha256': sha(raw)}

    def artifact_operation(self, key, raw):
        name = 'artifacts/' + key + '-' + sha(raw) + '.json'
        reference = {'path': name, **self.write(self.directory / name, raw)}
        return {'id': key, 'exit_code': 0, 'timed_out': False, 'output_truncated': False,
            'duration_ms': 4, 'invocation_sha256': sha(canonical(['owned-' + key])),
            'output': None, 'output_bytes': len(raw), 'output_sha256': sha(raw), 'output_artifact': reference}

    def refresh_receipts(self):
        self.outer['sample']['process_receipt'] = self.write(self.directory / 'process-receipt.json', canonical(self.process))
        self.outer['sample']['diagnostic_result'] = self.write(self.directory / 'sample-diagnostic-result.json', canonical(self.diagnostic))
        reference = self.write(self.receipt_path, canonical(self.outer))
        self.expected['caller_receipt_sha256'] = reference['sha256']

    def export(self):
        return EXPORTER.export_sample(self.receipt_path, self.output, self.expected,
            caller_source=CALLER_PATH, sample_source=SAMPLE_PATH)

    def test_complete_present_export_joins_exact_fresh_bytes_and_preserves_false_gates(self):
        receipt = self.export()
        summary = json.loads((self.output / 'sample-summary.json').read_bytes())
        self.assertEqual(summary['diagnostic_outcome'], 'FOUR_CONTEXT_DATA_AND_TELEMETRY_CAPTURED_NO_FULL_CREDIT')
        self.assertTrue(summary['telemetry_projection']['positive_host_telemetry_validation'])
        self.assertTrue(summary['native_projection']['complete_four_record_population_bound'])
        rows = summary['native_projection']['contexts']
        self.assertEqual([row['record_position'] for row in rows], [0, 1, 2, 3])
        self.assertEqual([row['original_context_index'] for row in rows], [0, 58, 154, 186])
        self.assertEqual([row['context_id'] for row in rows], [row['context_id'] for row in self.request['contexts']])
        for flag in ('full_native_qualified', 'production_qualified', 'assessment_completed',
                     'static_collection_complete', 'human_approval_created', 'cold_timing_credit'):
            self.assertIs(summary[flag], False)
        self.assertIs(receipt['full_native_or_production_qualification'], False)
        self.assertIs(summary['private_sample_envelope_exported'], False)
        self.assertFalse((self.output / 'sample-envelope.json').exists())
        self.assertEqual((self.output / self.native_op['output_artifact']['path']).read_bytes(), self.native_raw)
        self.assertEqual((self.output / self.telemetry_op['output_artifact']['path']).read_bytes(), self.telemetry_raw)
        manifest = json.loads((self.output / 'manifest.json').read_bytes())
        self.assertEqual(manifest['file_count'], 3)
        self.assertEqual(receipt['file_count_with_manifest'], 4)
        self.assertEqual({row['path'] for row in manifest['files']},
            {'sample-summary.json', self.native_op['output_artifact']['path'], self.telemetry_op['output_artifact']['path']})
        for row in manifest['files']:
            raw = (self.output / row['path']).read_bytes()
            self.assertEqual((len(raw), sha(raw)), (row['bytes'], row['sha256']))
        self.assertEqual(summary['cache_state'], 'UNKNOWN')
        self.assertEqual(summary['request_selection']['obligations']['unsampled_fallback_contexts'], 572)

    def test_wrong_producer_source_identity_rejected_with_current_outer_digest(self):
        self.outer['source_binding']['sample_sha256'] = '0' * 64
        self.refresh_receipts()
        with self.assertRaisesRegex(ValueError, 'sample_source_hash_binding'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_wrong_independent_actual_sampler_source_hash_rejected(self):
        self.expected['sample_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.export()
        self.assertFalse(self.output.exists())

    def test_stale_process_receipt_digest_rejected(self):
        self.process['status'] = 'UNPROVEN'
        self.write(self.directory / 'process-receipt.json', canonical(self.process))
        with self.assertRaises(ValueError):
            self.export()
        self.assertFalse(self.output.exists())

    def test_changed_envelope_argv_rejected_even_with_refreshed_file_references(self):
        self.envelope['request']['contexts'][0]['invocation'].append('--owned-mutation')
        reference = self.write(self.directory / 'sample-envelope.json', canonical(self.envelope))
        self.diagnostic['sample_envelope'] = {'path': 'sample-envelope.json', **reference}
        self.refresh_receipts()
        with self.assertRaisesRegex(ValueError, 'sample_runtime_binding'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_wrong_program_module_binding_rejected_with_refreshed_receipts(self):
        self.diagnostic['program_binding']['sample_module_sha256'] = '0' * 64
        self.refresh_receipts()
        with self.assertRaisesRegex(ValueError, 'sample_program_fixed_source_bindings'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_qualification_upgrade_rejected_with_current_receipt_digest(self):
        self.outer['full_native_qualified'] = True
        self.refresh_receipts()
        with self.assertRaisesRegex(ValueError, 'sample_parent_acceptance_flags'):
            self.export()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
