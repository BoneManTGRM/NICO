"""Synthetic local exporter boundary controls; root is the sole executor.

These controls do not import NICO, invoke Docker/native tools, assess a target,
measure production latency, or grant diagnostic/native qualification.
"""
from pathlib import Path
import base64
import copy
import importlib.util
import json
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/cpp_full_static_diagnostic_export.py'
SPEC = importlib.util.spec_from_file_location('owned_static_exporter', MODULE)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
IMAGE = exporter.FIXED_IMAGE


class ExportBoundaryControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.output = self.base / 'export'
        self.variants = []
        self.stage = {}; self.diagnostic = {}
        for variant in ('baseline', 'candidate'):
            directory = self.base / variant
            directory.mkdir()
            artifacts = []
            for key, schema in [
                ('project-static-environment', 'nico.cpp-static-environment.v2'),
                ('project-static-evidence', 'nico.cpp-project-static-evidence.v4'),
                ('project-static-clang-fallback', 'nico.cpp-clang-fallback-evidence.v7'),
            ]:
                value = {'schema': schema, 'request_sha256': '1' * 64, 'duration_ms': 11}
                if key == 'project-static-environment':
                    value.update(image_config_digest=IMAGE, compiler_versions={}, queries={}, headers={}, models={})
                else:
                    value['records'] = [
                        {'context_id': 'context-0', 'invocation': ['PRIVATE_PROGRAM_NOT_EXPORTABLE'],
                         'execution': {'exit_code': 0, 'timed_out': False, 'output_truncated': False,
                                       'duration_ms': 4, 'output': base64.b64encode(b'fresh').decode(),
                                       'output_sha256': exporter.digest(b'fresh')}, 'error': None},
                        {'context_id': 'context-1', 'execution': None, 'error': 'worker_test_deadline'},
                    ]
                raw = exporter.canonical(value)
                path = 'artifacts/' + key + '-' + exporter.digest(raw) + '.json'
                (directory / 'artifacts').mkdir(exist_ok=True)
                (directory / path).write_bytes(raw)
                artifacts.append({'id': key, 'invocation': ['PRIVATE_PROGRAM_NOT_EXPORTABLE'],
                    'output': None, 'output_sha256': exporter.digest(raw), 'exit_code': 0,
                    'timed_out': False, 'output_truncated': False, 'duration_ms': 11,
                    'output_artifact': {'path': path, 'bytes': len(raw), 'sha256': exporter.digest(raw)}})
            image_output = exporter.canonical([{'Id': IMAGE, 'opaque_private_path': '/workspace/private'}])
            image_operation = {'id': 'static-image', 'output': base64.b64encode(image_output).decode(),
                'output_sha256': exporter.digest(image_output), 'exit_code': 0, 'timed_out': False,
                'output_truncated': False, 'duration_ms': 1, 'invocation': ['/workspace/private', 'PROGRAM']}
            self.stage[variant] = {'schema': 'nico.cpp-project-static-stage.v4', 'phase': 'analysis_fallback',
                'complete': False, 'collection_complete': False, 'production_qualified': False,
                'duration_ms': 17, 'error': 'worker_project_static_stage_analysis_incomplete',
                'operations': [image_operation, *artifacts],
                'analysis': {'complete': False, 'required_contexts': ['context-0', 'context-1'],
                    'attempted_contexts': ['context-0'], 'analyzed_contexts': ['context-0'],
                    'findings': [{'private': '/workspace/private'}], 'header_context_evidence_complete': False},
                'compiler_collection': None, 'static_collection': None}
            self.stage[variant].update(cleanup_verified=True, boundary_verified=True,
                scratch_capacity_verified=True, scratch_capacity_bytes=9663676416,
                memory_peak_bytes=123, execution_budget_seconds=1020, wall_budget_seconds=1030,
                resource_profile='cpp-baseline-qualification-v1')
            self.diagnostic[variant] = {
                'schema': 'nico.private.static_stage_diagnostic_result.v1',
                'actual_stage_schema': self.stage[variant]['schema'],
                'actual_stage_error': self.stage[variant]['error'],
                'static_stage_complete': False, 'static_collection_complete_with_findings': False,
                'selected_image': {'selected_config_digest': IMAGE, 'local_image_config_inspection_verified': True},
                'compiled': False, 'tests_executed': False, 'assessment_completed': False,
                'full_native_qualified': False, 'production_qualified': False, 'mock_injection_used': False,
                'api_total_observed_ms': 19,
                'command_intervals': [{'kind': 'primary_static_transport', 'duration_ms': 11,
                                       'scope': '/workspace/private', 'argv_sha256': '2' * 64}],
                'retention_callback_intervals': [], 'observed_api_phase_callbacks': [],
                'historical106850ms_residual_reattributed': False,
                'plan': {'schema': 'nico.private.full_static_adapter_plan.v1',
                    'source_population': 3031, 'snapshot_files': 143, 'generated_units': 42,
                    'compiler_contexts': 577, 'historical_required_fallback_contexts': 576,
                    'flags': dict(exporter.FLAGS), 'limits': dict(exporter.LIMITS),
                    'frozen_target': {'repository': 'bitcoin/bitcoin', 'commit_sha': exporter.FROZEN_HEAD,
                                      'tree_sha': exporter.FROZEN_TREE},
                    'pins': '/workspace/private', 'opaque_old_receipt': '/home/owner/private'},
            }
            self.variants.append({'id': variant, 'directory': str(directory),
                                  'diagnostic_result': None, 'static_stage_receipt': None})
        self.expected = {'caller_receipt_sha256': None, 'current_git_head': '3' * 40,
            'effective_fallback_baseline': 'f0919654edd719059ea03319981b13f46ba70a88',
            'compiler_overlay_path': 'nico/assessment_cpp_project_compiler.py',
            'compiler_overlay_sha256': '4' * 64, 'exporter_sha256': exporter.digest(MODULE.read_bytes()),
            'caller_sha256': '5' * 64, 'scope_sha256': '6' * 64, 'image_config_digest': IMAGE}
        self.outer = {'schema': 'nico.private.full_static_pair_caller.v1',
            'source_binding': {key: self.expected[key] for key in ('current_git_head',
                'effective_fallback_baseline', 'exporter_sha256', 'caller_sha256', 'scope_sha256')},
            'image_binding': {'selected_config_digest': IMAGE, 'fixed_config_digest': IMAGE,
                'loaded_image_inspection_verified': True, 'complete_archive_verified': True,
                'config_and_ordered_rootfs_equal_independent_build_receipt': True,
                'same_selected_image_for_both_variants': True, 'historical_image_recovered': False,
                'matching_historical_live_toolchain_or_header_inputs_inferred': False}, 'variants': self.variants,
            'private_paths': ['/workspace/private'], 'old_compiler_raw': 'OPAQUE_DO_NOT_COPY'}
        self.outer.update(order=['baseline', 'candidate'], single_pair_only=True, cache_state='UNKNOWN',
            job_outer_budget_minutes=155, declared_api_wall_seconds=1030, shared_execution_seconds=1020,
            sequential_pair_policy_execution_upper_seconds=2040, independent1030_hardwall_supervisor_present=False,
            parent_cpu_is_analyzer_cpu=False, overlapping_intervals_additive=False, intervals=[],
            target_binding={'repository': 'bitcoin/bitcoin', 'commit_sha': exporter.FROZEN_HEAD,
                'file_count': 3031, 'bytes': 49729651, 'tree_sha': exporter.FROZEN_TREE,
                'all_original_sha256_git_blob_owner_and_any_executable_modes_verified': True,
                'data_only_copy_no_git': True, 'target_code_imported_compiled_or_run': False})
        self.outer['status'] = 'FULL_STATIC_PAIR_CAPTURED'
        self.outer['image_binding']['config_and_rootfs_sha256'] = '7' * 64
        self.outer['image_binding']['config_and_rootfs_verified_after_pair'] = True
        self.outer['source_binding']['compiler_overlay'] = {'path': self.expected['compiler_overlay_path'],
                                                          'sha256': self.expected['compiler_overlay_sha256']}
        self.outer['source_binding']['all_selected_files_actual_git_blob_bound'] = True
        self.outer['source_binding']['effective_overlay_is_whole_candidate'] = False
        self.outer['source_binding']['baseline_compiler_sha256'] = exporter.BASELINE_COMPILER_SHA
        self.outer['source_binding']['actual_operation'] = {'commit_sha': self.expected['current_git_head']}
        for variant in ('baseline', 'candidate'):
            self.diagnostic[variant]['selected_library'] = {
                'variant': variant, 'selected_library_head': self.expected['effective_fallback_baseline'],
                'selected_library_tree': 'b9e200f62b9b2db9c6488326826ad8ae393418d0',
                'actual_operation': self.outer['source_binding']['actual_operation'],
                'base_inventory_files_verified': 3305, 'base_inventory_sha256': '8' * 64,
                'source_loader_uses_verified_text_not_cached_bytecode': True,
                'matching_whole_library_and_image_source_inferred': False,
                'selected_compiler': {'path': self.expected['compiler_overlay_path'],
                    'sha256': exporter.BASELINE_COMPILER_SHA if variant == 'baseline' else self.expected['compiler_overlay_sha256']}}
        self.receipt = self.base / 'pair-receipt.json'
        self.refresh()

    def tearDown(self):
        self.temporary.cleanup()

    def refresh(self):
        for row in self.variants:
            variant = row['id']; directory = Path(row['directory'])
            if self.stage[variant] is not None:
                raw = exporter.canonical(self.stage[variant]); (directory / 'static-stage-receipt.json').write_bytes(raw)
                row['static_stage_receipt'] = {'bytes': len(raw), 'sha256': exporter.digest(raw)}
            else:
                (directory / 'static-stage-receipt.json').unlink(missing_ok=True)
                row['static_stage_receipt'] = None
            raw = exporter.canonical(self.diagnostic[variant]); (directory / 'diagnostic-result.json').write_bytes(raw)
            row['diagnostic_result'] = {'bytes': len(raw), 'sha256': exporter.digest(raw)}
        self.write_outer()

    def write_outer(self):
        raw = exporter.canonical(self.outer); self.receipt.write_bytes(raw)
        self.expected['caller_receipt_sha256'] = exporter.digest(raw)

    def run_export(self):
        return exporter.export_pair(self.receipt, self.output, self.expected)

    def reject(self, code):
        with self.assertRaisesRegex(exporter.Rejected, code):
            self.run_export()
        self.assertFalse(self.output.exists(), 'Invalid inputs must fail before output mutation')

    def alter_artifact(self, value=None, raw=None):
        operation = self.stage['baseline']['operations'][2]
        directory = Path(self.variants[0]['directory'])
        (directory / operation['output_artifact']['path']).unlink()
        raw = raw if raw is not None else exporter.canonical(value)
        path = 'artifacts/' + operation['id'] + '-' + exporter.digest(raw) + '.json'
        (directory / path).write_bytes(raw)
        operation['output_sha256'] = exporter.digest(raw)
        operation['output_artifact'] = {'path': path, 'bytes': len(raw), 'sha256': exporter.digest(raw)}
        self.refresh()
        return path, raw

    def test_valid_incomplete_retains_exact_fresh_bytes_and_unknown_costs(self):
        result = self.run_export(); self.assertTrue(result['closed_allowlist_all_bytes_readback_verified'])
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertFalse(public['full_native_qualified'])
        self.assertEqual(public['variants'][0]['diagnostic_outcome'], 'VALID_DIAGNOSTIC_INCOMPLETE')
        self.assertIsNone(public['variants'][0]['opaque_subphase_costs']['unstarted_context_costs'])
        raw = (self.output / 'static-summary.json').read_bytes()
        for marker in [b'/workspace/', b'/home/', b'PRIVATE_PROGRAM', b'old_compiler_raw', b'106850']:
            self.assertNotIn(marker, raw)
        self.assertEqual(len(list(self.output.glob('*/artifacts/*.json'))), 6)

    def test_fresh_malformed_stdout_is_retained_without_analysis_credit(self):
        path, raw = self.alter_artifact(raw=b'{truncated fresh worker stdout')
        self.run_export(); self.assertEqual((self.output / 'baseline' / path).read_bytes(), raw)
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        projection = public['variants'][0]['actual_operations'][2]['artifact']['raw_projection']
        self.assertEqual(projection['parse_status'], 'UNPARSEABLE_FRESH_STDOUT_UNPROVEN')
        self.assertFalse(projection['analysis_or_population_credit'])

    def test_wrong_schema_stdout_retained_as_explicit_unproven(self):
        self.alter_artifact(value={'schema': 'nico.cpp-static-environment.v2'})
        self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertEqual(public['variants'][0]['actual_operations'][2]['artifact']['raw_projection']['parse_status'],
                         'SCHEMA_KEY_MISMATCH_UNPROVEN')

    def test_no_stage_callback_absence_is_preserved(self):
        directory = Path(self.variants[0]['directory'])
        for f in (directory / 'artifacts').iterdir(): f.unlink()
        self.stage['baseline'] = None
        self.diagnostic['baseline'].update(actual_stage_schema=None, actual_stage_error='private_runner_invocation_exception')
        self.diagnostic['baseline']['selected_image']['local_image_config_inspection_verified'] = False
        self.refresh(); self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertFalse(public['variants'][0]['static_stage_receipt_present'])
        self.assertEqual(public['variants'][0]['diagnostic_outcome'], 'NO_STAGE_CALLBACK_RETAINED_UNPROVEN')

    def test_provider_or_old_pin_file_not_silently_copied(self):
        (Path(self.variants[0]['directory']) / 'old-pins.json').write_text('{}')
        self.reject('unapproved_variant_file')

    def test_failed_prefix_marks_candidate_not_run_without_synthesizing_receipt(self):
        self.outer['variants'] = [self.variants[0]]
        self.outer['status'] = 'UNPROVEN'; self.write_outer(); self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertEqual(public['variants'][1]['execution_state'], 'NOT_RUN')
        self.assertEqual(len(list(self.output.glob('candidate/artifacts/*.json'))), 0)

    def test_missing_diagnostic_result_remains_absent(self):
        directory = Path(self.variants[0]['directory'])
        (directory / 'diagnostic-result.json').unlink()
        self.variants[0]['diagnostic_result'] = None
        self.write_outer(); self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertFalse(public['variants'][0]['diagnostic_result_present'])
        self.assertIsNone(public['variants'][0]['diagnostic_result_sha256'])
        self.assertEqual(public['variants'][0]['diagnostic_outcome'], 'DIAGNOSTIC_RESULT_ABSENT_UNPROVEN')

    def test_unreferenced_artifact_not_silently_exported(self):
        (Path(self.variants[0]['directory']) / 'artifacts/old-compiler.json').write_text('{}')
        self.reject('unreferenced_or_missing_fresh_artifact')

    def test_digest_tamper_rejected(self):
        row = self.stage['baseline']['operations'][2]
        (Path(self.variants[0]['directory']) / row['output_artifact']['path']).write_bytes(b'tampered')
        self.reject('file_size_mismatch|file_digest_mismatch')

    def test_symlink_artifact_rejected(self):
        row = self.stage['baseline']['operations'][2]; path = Path(self.variants[0]['directory']) / row['output_artifact']['path']
        target = self.base / 'elsewhere'; path.rename(target); path.symlink_to(target)
        self.reject('symlink_or_noncanonical_path')

    def test_unsafe_reference_rejected(self):
        self.stage['baseline']['operations'][2]['output_artifact']['path'] = '../compiler_raw.json'
        self.refresh(); self.reject('unsafe_relative_path')

    def test_reference_key_filename_mismatch_rejected(self):
        self.stage['baseline']['operations'][2]['output_artifact']['path'] = 'artifacts/other.json'
        self.refresh(); self.reject('artifact_filename_key_digest_mismatch')

    def test_duplicate_operation_rejected(self):
        self.stage['baseline']['operations'].append(copy.deepcopy(self.stage['baseline']['operations'][2]))
        self.refresh(); self.reject('operation_id_invalid_or_duplicate')

    def test_missing_external_artifact_retention_preserves_failure_operation(self):
        operation = self.stage['baseline']['operations'][2]
        (Path(self.variants[0]['directory']) / operation['output_artifact']['path']).unlink()
        operation['output_artifact'] = None
        self.stage['baseline']['error'] = 'worker_project_static_stage_artifact_retention_failed'
        self.diagnostic['baseline']['actual_stage_error'] = self.stage['baseline']['error']
        self.refresh(); self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        observed = public['variants'][0]['actual_operations'][2]
        self.assertTrue(observed['artifact_not_retained'])
        self.assertIsNone(observed['stage_output_artifact_ref'])
        self.assertIsNone(observed['populations'])
        self.assertEqual(public['variants'][0]['diagnostic_outcome'], 'BROKEN_STAGE_ARTIFACT_RETENTION_UNPROVEN')

    def test_nonartifact_operation_cannot_copy_reference(self):
        self.stage['baseline']['operations'][0]['output_artifact'] = self.stage['baseline']['operations'][2]['output_artifact']
        self.refresh(); self.reject('non_artifact_operation_reference')

    def test_actual_image_mismatch_rejected(self):
        raw = exporter.canonical([{'Id': 'sha256:' + '9' * 64}])
        self.stage['baseline']['operations'][0]['output'] = base64.b64encode(raw).decode()
        self.stage['baseline']['operations'][0]['output_sha256'] = exporter.digest(raw)
        self.refresh(); self.reject('fresh_stage_image_inspection_mismatch')

    def test_receipt_source_or_exporter_hash_mismatch_rejected(self):
        self.outer['source_binding']['exporter_sha256'] = '9' * 64
        self.write_outer(); self.reject('source_hash_binding_mismatch')

    def test_current_head_mismatch_rejected(self):
        self.outer['source_binding']['current_git_head'] = '9' * 40
        self.write_outer(); self.reject('source_commit_binding_mismatch')

    def test_pair_alias_rejected(self):
        self.variants[1]['directory'] = self.variants[0]['directory']
        self.write_outer(); self.reject('variant_directory_alias')

    def test_qualification_flag_cannot_be_exported_as_true(self):
        self.diagnostic['baseline']['full_native_qualified'] = True
        self.refresh(); self.reject('diagnostic_claim_invalid')

    def test_malformed_population_never_gets_projection_credit(self):
        self.alter_artifact(value={'schema': 'nico.cpp-project-static-evidence.v4', 'request_sha256': '1' * 64,
                                  'duration_ms': 1, 'records': [{'context_id': 'x', 'execution': {}}]})
        self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertEqual(public['variants'][0]['actual_operations'][2]['artifact']['raw_projection']['parse_status'],
                         'INVALID_SCHEMA_DATA_UNPROVEN')

    def test_fresh_private_host_or_access_material_blocks_public_export(self):
        self.alter_artifact(raw=b'{"schema":"worker-failure","error":"/workspace/private?X-Amz-Signature=secret"}')
        self.reject('private_host_path_or_access_material_in_artifact')

    def test_declared_artifact_limit_rejected_before_mutation(self):
        self.stage['baseline']['operations'][2]['output_artifact']['bytes'] = exporter.MAX_ARTIFACT_BYTES + 1
        self.refresh(); self.reject('file_size_mismatch')

    def test_total_export_limit_rejected_before_mutation(self):
        previous = exporter.MAX_TOTAL_EXPORTED_BYTES
        try:
            exporter.MAX_TOTAL_EXPORTED_BYTES = 1
            self.reject('total_export_bound_exceeded')
        finally:
            exporter.MAX_TOTAL_EXPORTED_BYTES = previous

    def test_missing_source_or_image_preflight_exports_failure_hash_only(self):
        self.outer.update(source_binding=None, image_binding=None, status='UNPROVEN',
                          error={'message': '/workspace/private?X-Amz-Signature=secret'}, variants=[])
        self.write_outer(); self.run_export()
        public_raw = (self.output / 'static-summary.json').read_bytes()
        public = json.loads(public_raw)
        self.assertIsNone(public['source_binding'])
        self.assertFalse(public['raw_artifact_bytes_credit'])
        self.assertNotIn(b'/workspace/', public_raw)
        self.assertEqual(len(list(self.output.glob('*/artifacts/*.json'))), 0)

    def test_image_archive_layer_proof_cannot_be_waived(self):
        self.outer['image_binding']['config_and_ordered_rootfs_equal_independent_build_receipt'] = False
        self.write_outer(); self.reject('fixed_loaded_image_binding_mismatch')

    def test_budget_change_cannot_be_exported_as_equivalent(self):
        self.outer['job_outer_budget_minutes'] = 156
        self.write_outer(); self.reject('fixed_pair_order_budget_clock_contract_invalid')

    def test_target_or_api_limit_change_cannot_get_scope_credit(self):
        self.diagnostic['baseline']['plan']['limits']['fallback_parallel'] = 3
        self.refresh(); self.reject('fixed_api_flags_limits_mismatch')

    def test_parent_intervals_preserve_clock_scope_and_no_additive_sum(self):
        self.outer['intervals'] = [{'phase': 'whole_image_setup', 'wall_ms': 11, 'process_cpu_ms': 2,
            'clock_domain': 'this_process_perf_counter_and_process_time',
            'cpu_scope': 'This host process only; excludes analyzer/container and child-process CPU.'}]
        self.write_outer(); self.run_export()
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        self.assertEqual(public['parent_observation_intervals'][0]['wall_ms'], 11)
        self.assertFalse(public['pair_budget_and_order']['overlapping_intervals_additive'])

    def assert_malformed_fresh_artifact_retained_unproven(self, raw):
        path, retained = self.alter_artifact(raw=raw)
        result = self.run_export()
        self.assertTrue(result['closed_allowlist_all_bytes_readback_verified'])
        self.assertEqual((self.output / 'baseline' / path).read_bytes(), retained)
        manifest = json.loads((self.output / 'manifest.json').read_bytes())
        listed = next(row for row in manifest['files'] if row['path'] == 'baseline/' + path)
        self.assertEqual(listed['bytes'], len(retained))
        self.assertEqual(listed['sha256'], exporter.digest(retained))
        public = json.loads((self.output / 'static-summary.json').read_bytes())
        projection = public['variants'][0]['actual_operations'][2]['artifact']['raw_projection']
        self.assertIn(projection['parse_status'], {'SCHEMA_KEY_MISMATCH_UNPROVEN', 'INVALID_SCHEMA_DATA_UNPROVEN',
                                                 'UNPARSEABLE_FRESH_STDOUT_UNPROVEN'})
        self.assertEqual(projection['raw_sha256'], exporter.digest(retained))
        self.assertFalse(projection['analysis_or_population_credit'])
        self.assertNotIn('contexts', projection)
        self.assertNotIn('population', projection)
        self.assertFalse(public['variants'][0]['fresh_artifact_schema_projection_all_valid'])
        self.assertEqual(public['variants'][0]['diagnostic_outcome'], 'RETAINED_FRESH_BYTES_SCHEMA_OR_PROJECTION_UNPROVEN')
        self.assertFalse(public['full_native_qualified'])
        self.assertFalse(public['production_qualified'])

    def test_fresh_schema_array_retains_raw_without_unhashable_escape(self):
        for index, raw in enumerate((b'{"schema":[]}', b'{"schema":[1e999]}')):
            with self.subTest(raw=raw):
                self.output = self.base / ('schema-array-export-' + str(index))
                self.assert_malformed_fresh_artifact_retained_unproven(raw)

    def test_fresh_exponent_overflow_retains_raw_without_canonical_escape(self):
        raw = (b'{"schema":"nico.cpp-project-static-evidence.v4","request_sha256":"' + b'1' * 64
               + b'","duration_ms":1e999,"records":[]}')
        self.assert_malformed_fresh_artifact_retained_unproven(raw)

    def test_fresh_oversized_finite_integer_retains_raw_without_isfinite_escape(self):
        raw = exporter.canonical({'schema': 'nico.cpp-project-static-evidence.v4',
                                  'request_sha256': '1' * 64, 'duration_ms': 10 ** 500, 'records': []})
        self.assert_malformed_fresh_artifact_retained_unproven(raw)

    def test_fresh_depth10000_json_retains_exact_raw_without_recursion_escape(self):
        # Root reproduced this exact depth; no threshold is inferred from the
        # Python recursion setting or from shallower accepted JSON examples.
        raw = b'[' * 10000 + b'0' + b']' * 10000
        self.assert_malformed_fresh_artifact_retained_unproven(raw)


if __name__ == '__main__':
    unittest.main()
