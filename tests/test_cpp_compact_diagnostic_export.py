"""Owned offline schema controls. These fixtures are not assessed-run evidence."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'cpp_compact_diagnostic_export.py'
SPEC = importlib.util.spec_from_file_location('owned_compact_export', SOURCE)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)
HEAD, DRIVER, RUN = 'a' * 40, 'b' * 64, '99999999999'
IMAGE, TAR = 'sha256:' + 'c' * 64, 'd' * 64


def fixture():
    """All values here are owned synthetic controls, never real qualification."""
    layers = ['sha256:' + '1' * 64, 'sha256:' + '2' * 64, 'sha256:' + '1' * 64]
    rows = [{'index': i, 'diff_id': layer, 'path': 'blobs/sha256/' + layer[7:],
             'stored_sha256': layer[7:], 'stored_bytes': 100, 'expanded_bytes': 100, 'gzip': False}
            for i, layer in enumerate(layers)]
    outer = {'schema': EXPORT.OUTER_SCHEMA, 'status': 'RETRIEVED_IMAGE_AST_PARSER_DIAGNOSTIC_VERIFIED',
             'production_qualified': False, 'historical_image_recovered': False, 'target_execution': False,
             'analyzer_execution': False, 'registry_push': False, 'release_or_merge': False,
             'new_image_build': False, 'full_native_qualified': False,
             'setup_or_analyzer_throughput_improvement_proved': False,
             'cleanup_verified': True, 'container_create_attempted': True, 'container_create_completed': True,
             'error': None, 'operation': {'head': HEAD, 'tree': '3' * 40, 'run_id': RUN, 'run_attempt': 1,
                                        'driver_sha256': DRIVER,
                                        'archive_helper_sha256': '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344'},
             'unchanged_recipe_source': {'commit': '4' * 40, 'tree': '5' * 40, 'tracked_files': 3305,
                                         'tracked_byte_blob_mode_inventory_sha256': '6' * 64},
             'diagnostic_frozen_target': {'repository': 'bitcoin/bitcoin', 'commit': '7' * 40,
                                          'tree': '8' * 40, 'target_population_sha256': '9' * 64},
             'archive_proof': {'config_id': IMAGE, 'config_sha256': IMAGE[7:],
                               'all_layer_diffids_verified': True,
                               'safe_unique_outer_regular_or_directory_members': True,
                               'target_execution': False, 'layer_reference_count': 3,
                               'unique_layer_members': 2, 'layer_rows': rows,
                               'total_unique_expanded_layer_bytes': 200,
                               'archive': {'sha256': TAR, 'bytes': 300}},
             'loaded_image_inspection': {'Id': IMAGE, 'Os': 'linux', 'Architecture': 'amd64',
                                         'RootFS': {'Type': 'layers', 'Layers': layers}},
             'container_before': {'Image': IMAGE, 'Config': {'User': '1000:1000',
                                 'Entrypoint': ['python3'], 'Env': ['HOME=/work', 'TMPDIR=/work']},
                                 'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True,
                                               'NanoCpus': 4000000000, 'Memory': EXPORT.MEMORY,
                                               'MemorySwap': EXPORT.MEMORY, 'PidsLimit': 256,
                                               'Tmpfs': {'/work': EXPORT.TMPFS_OPTIONS},
                                               'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges']},
                                 'Mounts': [{'Type': 'bind', 'Destination': destination, 'RW': False,
                                             'Source': '/private-control/' + destination[1:]}
                                            for destination in ['/diag', '/evidence', '/identity']]},
             'container_terminal': {'Running': False, 'OOMKilled': False, 'ExitCode': 0},
             'operations': [{'argv': ['docker', 'image', 'load', '--input', '/private-control/image.tar'],
                             'timeout_seconds': 90, 'timed_out': False, 'exit_code': 0},
                            {'argv': ['docker', 'start', '--attach', 'nico-parser-' + RUN + '-1'],
                             'timeout_seconds': 480, 'timed_out': False, 'exit_code': 0},
                            {'argv': ['docker', 'rm', '--force', 'nico-parser-' + RUN + '-1'],
                             'timeout_seconds': 5, 'timed_out': False, 'exit_code': 0}]}
    worker = {'schema': EXPORT.WORKER_SCHEMA, 'status': 'SAME_IMAGE_AST_HELPERS_VERIFIED',
              'production_qualified': False, 'target_execution': False, 'native_execution': False,
              'analyzer_execution': False, 'assessed_compiler_execution': False,
              'full_producer_sequence_executed': False, 'full_native_qualified': False,
              'module_or_PROGRAM_executed': False, 'historical_image_recovered': False,
              'historical001f_measurement': False, 'diagnostic_container_executed': True,
              'actual_retained_outputs_identical': True, 'original_inputs_unchanged': True,
              'forbidden_events': [], 'environment': {'isolated': True, 'no_site': True,
                  'root_read_only': True, 'network_none_verified_by_outer_driver': True,
                  'uid': 1000, 'gid': 1000, 'cpu_max': ['400000', '100000'],
                  'memory_max': str(EXPORT.MEMORY), 'pids_max': '256',
                  'tmpfs_options': ['rw', 'nosuid', 'nodev', 'noexec', 'size=9437184k'],
                  'outer_identity': {'image_config_id': IMAGE, 'image_archive_sha256': TAR,
                                     'complete_archive_verified': True, 'network': 'none',
                                     'read_only': True, 'user': '1000:1000'},
                  'python': '3.10.12 (owned offline fixture)'},
              'execution_wall_limit_seconds': 480,
              'memory_peak_bytes_including_untimed_preparation_and_controls': 1048576,
              'input_provenance': {'runtime_members_verified': 3, 'target_digest_population': 3031,
                  'raw_compiler_records': 577, 'snapshot_files': 143, 'generated_units': 42,
                  'nonempty_dependency_lists': 576, 'fallback_obligations_executed': 0,
                  'snapshot_header_dependencies_verified': False, 'genuine_dummy_error_retained': True,
                  'host_original_32_member_and_provider_zip_verification_required': True,
                  'historical_selection_or_receipt_metadata_mounted': False},
              'required_full_obligations_unchanged': {'contexts': 577, 'fallback_contexts': 576,
                                                     'full_headers_and_generated_inputs': True},
              'fixture_pairs': 41, 'individual_fixture_calls': 82,
              'fixture_checks': [{'name': 'owned-case-' + str(i), 'accepted': i % 2 == 0,
                                  'same_output_or_exact_error': True, 'outcome_sha256': 'e' * 64}
                                 for i in range(41)],
              'outputs_sha256': 'f' * 64,
              'timings': [{'variant': 'baseline', 'dependency_lists': 576,
                           'wall_ms': 1234.5, 'process_cpu_ms': 1222.5},
                          {'variant': 'candidate', 'dependency_lists': 576,
                           'wall_ms': 234.5, 'process_cpu_ms': 222.5}]}
    return outer, worker


def encoded(outer, worker):
    worker_raw = EXPORT.canonical(worker) + b'\n'
    outer = deepcopy(outer)
    outer['container_receipt_sha256'] = hashlib.sha256(worker_raw).hexdigest()
    return EXPORT.canonical(outer) + b'\n', worker_raw


def at(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


class ExportControls(unittest.TestCase):
    def receipt(self, outer, worker):
        return EXPORT.make_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)

    def test_owned_success_is_compact_and_distinguishes_actual_execution(self):
        result = self.receipt(*fixture())
        self.assertLessEqual(len(EXPORT.canonical(result)) + 1, EXPORT.MAX_OUTPUT)
        self.assertEqual(result['operation']['source_sha'], HEAD)
        self.assertEqual(result['operation']['run_id'], RUN)
        self.assertEqual(result['diagnostic_image']['layer_references'], 3)
        self.assertEqual(result['diagnostic_image']['unique_layers'], 2)
        self.assertIs(result['container']['execution_verified'], True)
        self.assertIs(result['limitations']['native_execution'], False)
        self.assertEqual(result['comparison']['fixture_pairs'], 41)
        self.assertEqual(result['comparison']['individual_fixture_calls'], 82)
        self.assertEqual(result['resources']['execution_seconds'], 480)
        self.assertEqual(result['resources']['cleanup_seconds'], 5)

    def test_excluded_payload_never_enters_output(self):
        outer, worker = fixture()
        sentinel = 'PRIVATE_HISTORICAL_SENTINEL_DO_NOT_EXPORT'
        secret = 'OWNED_SECRET_SENTINEL_NOT_A_CREDENTIAL'
        url = 'https://fixture.invalid/archive?sig=OWNED_SIGNED_URL_SENTINEL'
        outer.update({'historical_run_id': sentinel, 'provider_selection': {'url': url, 'token': secret},
                      'old_pins': {'hash': sentinel}, 'full_build_receipt': {'sensitive': secret}})
        outer['operation'].update(runner=sentinel, host_python=secret)
        outer['archive_proof']['private_anchor'] = sentinel
        outer['archive_proof']['archive']['name'] = url
        outer['unchanged_recipe_source']['source_capture'] = secret
        outer['loaded_image_inspection']['Config'] = {'Credentials': secret}
        for row in outer['operations']:
            row['stderr_tail'] = secret + url + sentinel
        for row in outer['container_before']['Mounts']:
            row['Source'] = '/private/' + sentinel
        worker.update({'pins_sha256': sentinel, 'source_captures': [secret, url],
                       'historical_receipt': {'run': sentinel}})
        worker['environment'].update(kernel=[sentinel], executable=secret, hostname=sentinel)
        worker['environment']['python'] = '3.10.12 ' + secret + url + sentinel
        for row in worker['fixture_checks']:
            row['name'] += sentinel
        raw = EXPORT.canonical(self.receipt(outer, worker))
        for forbidden in (sentinel, secret, url, 'provider_selection', 'old_pins', 'full_build_receipt',
                          'stderr_tail', 'source_captures', 'runner', 'hostname', 'argv', 'pins_sha256'):
            self.assertNotIn(forbidden.encode(), raw)

    def test_wrong_raw_receipt_hash_rejected(self):
        outer_raw, worker_raw = encoded(*fixture())
        with self.assertRaisesRegex(EXPORT.ExportError, '^exact_worker_receipt_hash$'):
            EXPORT.make_receipt(outer_raw, worker_raw + b' ', HEAD, DRIVER, RUN)

    def test_archive_expansion_and_repeated_metadata_negative_controls(self):
        for kind, error in [('per-layer', 'proved_layer_expanded_size'),
                            ('aggregate', 'unique_layer_expanded_bound'),
                            ('wrong-total', 'proved_expanded_total'),
                            ('repeated-metadata', 'reused_layer_metadata')]:
            with self.subTest(kind=kind):
                outer, worker = fixture()
                proof = outer['archive_proof']
                if kind == 'per-layer':
                    proof['layer_rows'][0]['expanded_bytes'] = 3 * 1024 ** 3 + 1
                elif kind == 'aggregate':
                    proof['layer_rows'][0]['expanded_bytes'] = 3 * 1024 ** 3 - 100
                    proof['layer_rows'][2]['expanded_bytes'] = 3 * 1024 ** 3 - 100
                    proof['layer_rows'][1]['expanded_bytes'] = 200
                    proof['total_unique_expanded_layer_bytes'] = 3 * 1024 ** 3 + 100
                elif kind == 'wrong-total':
                    proof['total_unique_expanded_layer_bytes'] = 201
                else:
                    proof['layer_rows'][2]['stored_bytes'] = 101
                with self.assertRaisesRegex(EXPORT.ExportError, '^' + error + '$'):
                    self.receipt(outer, worker)

    def test_wrong_expected_operation_rejected(self):
        outer_raw, worker_raw = encoded(*fixture())
        for args in [('0' * 40, DRIVER, RUN), (HEAD, '0' * 64, RUN), (HEAD, DRIVER, '88888888888')]:
            with self.subTest(args=args), self.assertRaisesRegex(EXPORT.ExportError, '^new_operation_binding$'):
                EXPORT.make_receipt(outer_raw, worker_raw, *args)

    def test_negative_matrix_rejects_specific_predicate(self):
        cases = [
            ('outer', ['status'], 'UNPROVEN', 'diagnostic_status'),
            ('outer', ['operation', 'run_attempt'], True, 'new_operation_attempt'),
            ('outer', ['operation', 'archive_helper_sha256'], '0' * 64, 'reviewed_archive_helper'),
            ('outer', ['cleanup_verified'], False, 'outer_completion'),
            ('outer', ['container_create_completed'], False, 'outer_completion'),
            ('outer', ['loaded_image_inspection', 'Id'], 'sha256:' + '0' * 64, 'image_binding'),
            ('outer', ['archive_proof', 'config_sha256'], '0' * 64, 'image_binding'),
            ('outer', ['archive_proof', 'all_layer_diffids_verified'], False, 'every_layer_verification'),
            ('outer', ['archive_proof', 'layer_reference_count'], 2, 'image_layer_count'),
            ('outer', ['archive_proof', 'unique_layer_members'], 3, 'proved_unique_layers'),
            ('outer', ['archive_proof', 'layer_rows', 1, 'diff_id'], 'sha256:' + '0' * 64, 'proved_layer_identity'),
            ('outer', ['archive_proof', 'layer_rows', 1, 'index'], 0, 'proved_layer_index'),
            ('outer', ['archive_proof', 'archive', 'bytes'], 3 * 1024 ** 3 + 1, 'image_archive_size'),
            ('outer', ['container_before', 'HostConfig', 'NanoCpus'], 8000000000, 'actual_cpu'),
            ('outer', ['container_before', 'HostConfig', 'Memory'], EXPORT.MEMORY + 1, 'actual_memory'),
            ('outer', ['container_before', 'HostConfig', 'MemorySwap'], -1, 'actual_swap'),
            ('outer', ['container_before', 'HostConfig', 'PidsLimit'], 512, 'actual_pids'),
            ('outer', ['container_before', 'HostConfig', 'NetworkMode'], 'bridge', 'actual_container_identity'),
            ('outer', ['container_before', 'HostConfig', 'ReadonlyRootfs'], False, 'actual_container_identity'),
            ('outer', ['container_before', 'HostConfig', 'Tmpfs'], {}, 'actual_container_sandbox'),
            ('outer', ['container_before', 'Config', 'Env'], ['GH_TOKEN=OWNED_SENTINEL'], 'container_credential'),
            ('outer', ['container_before', 'Mounts', 0, 'RW'], True, 'minimal_readonly_mounts'),
            ('outer', ['container_before', 'Mounts', 0, 'Destination'], '/unreviewed', 'minimal_readonly_mounts'),
            ('outer', ['container_terminal', 'ExitCode'], 1, 'terminal_exit'),
            ('outer', ['container_terminal', 'Running'], True, 'terminal_running'),
            ('outer', ['container_terminal', 'OOMKilled'], True, 'terminal_oom'),
            ('outer', ['operations', 0, 'timeout_seconds'], 91, 'actual_lifecycle_deadline'),
            ('outer', ['operations', 1, 'timeout_seconds'], 481, 'actual_lifecycle_deadline'),
            ('outer', ['operations', 2, 'timeout_seconds'], 6, 'actual_lifecycle_deadline'),
            ('outer', ['operations', 2, 'exit_code'], 1, 'actual_lifecycle_exit'),
            ('outer', ['operations', 1, 'timed_out'], True, 'actual_lifecycle_timeout'),
            ('outer', ['diagnostic_frozen_target', 'repository'], 'other/repo', 'frozen_repository'),
            ('outer', ['unchanged_recipe_source', 'tracked_files'], 3304, 'recipe_population'),
            ('worker', ['status'], 'UNPROVEN', 'diagnostic_status'),
            ('worker', ['diagnostic_container_executed'], False, 'worker_completion'),
            ('worker', ['actual_retained_outputs_identical'], False, 'worker_completion'),
            ('worker', ['forbidden_events'], ['owned-forbidden-event'], 'diagnostic_failure'),
            ('worker', ['environment', 'outer_identity', 'image_config_id'], 'sha256:' + '0' * 64, 'worker_image_binding'),
            ('worker', ['environment', 'outer_identity', 'image_archive_sha256'], '0' * 64, 'worker_image_binding'),
            ('worker', ['environment', 'uid'], 0, 'worker_uid'),
            ('worker', ['environment', 'cpu_max'], ['max', '100000'], 'worker_cpu_schema'),
            ('worker', ['environment', 'cpu_max'], ['800000', '100000'], 'worker_cpu_limit'),
            ('worker', ['environment', 'memory_max'], 'max', 'worker_cgroup_limits'),
            ('worker', ['environment', 'tmpfs_options'], ['rw', 'size=9437184k'], 'worker_tmpfs'),
            ('worker', ['environment', 'python'], 'not-python', 'python_version'),
            ('worker', ['execution_wall_limit_seconds'], 481, 'worker_wall_limit'),
            ('worker', ['memory_peak_bytes_including_untimed_preparation_and_controls'], EXPORT.MEMORY + 1, 'worker_memory_peak'),
            ('worker', ['input_provenance', 'raw_compiler_records'], 576, 'retained_input_count'),
            ('worker', ['input_provenance', 'snapshot_files'], 142, 'retained_input_count'),
            ('worker', ['input_provenance', 'generated_units'], 41, 'retained_input_count'),
            ('worker', ['input_provenance', 'nonempty_dependency_lists'], 575, 'retained_input_count'),
            ('worker', ['input_provenance', 'fallback_obligations_executed'], 1, 'retained_input_count'),
            ('worker', ['input_provenance', 'snapshot_header_dependencies_verified'], True, 'retained_header_state'),
            ('worker', ['input_provenance', 'genuine_dummy_error_retained'], False, 'genuine_error'),
            ('worker', ['input_provenance', 'historical_selection_or_receipt_metadata_mounted'], True, 'private_history_mount'),
            ('worker', ['required_full_obligations_unchanged', 'contexts'], 576, 'context_obligation'),
            ('worker', ['fixture_pairs'], 82, 'fixture_pairs'),
            ('worker', ['individual_fixture_calls'], 41, 'fixture_calls'),
            ('worker', ['fixture_checks', 1, 'name'], 'owned-case-0', 'fixture_check_population'),
            ('worker', ['fixture_checks', 1, 'same_output_or_exact_error'], False, 'fixture_check_verdict'),
            ('worker', ['timings', 0, 'variant'], 'candidate', 'timing_population'),
            ('worker', ['timings', 1, 'dependency_lists'], 575, 'timing_list_count'),
            ('worker', ['timings', 1, 'wall_ms'], -1, 'timing_value'),
            ('worker', ['timings', 1, 'wall_ms'], True, 'timing_value'),
            ('worker', ['timings', 1, 'process_cpu_ms'], 480001, 'timing_value')]
        for scope, path, replacement, error in cases:
            with self.subTest(scope=scope, path=path):
                outer, worker = fixture()
                at(outer if scope == 'outer' else worker, path, replacement)
                with self.assertRaisesRegex(EXPORT.ExportError, '^' + error + '$'):
                    self.receipt(outer, worker)

    def test_all_prohibited_execution_flags_are_strict_false(self):
        outer_keys = ['production_qualified', 'historical_image_recovered', 'target_execution',
                      'analyzer_execution', 'registry_push', 'release_or_merge', 'new_image_build',
                      'full_native_qualified', 'setup_or_analyzer_throughput_improvement_proved']
        worker_keys = ['production_qualified', 'target_execution', 'native_execution', 'analyzer_execution',
                       'assessed_compiler_execution', 'full_producer_sequence_executed', 'full_native_qualified',
                       'module_or_PROGRAM_executed', 'historical_image_recovered', 'historical001f_measurement']
        for scope, keys in [('outer', outer_keys), ('worker', worker_keys)]:
            for key in keys:
                for replacement in (True, 0, None):
                    with self.subTest(scope=scope, key=key, replacement=replacement):
                        outer, worker = fixture()
                        (outer if scope == 'outer' else worker)[key] = replacement
                        with self.assertRaisesRegex(EXPORT.ExportError, '^' + scope + '_forbidden_claim$'):
                            self.receipt(outer, worker)

    def test_lifecycle_missing_duplicate_or_out_of_order_rejected(self):
        for kind in ('missing', 'duplicate', 'reversed', 'after-cleanup'):
            with self.subTest(kind=kind):
                outer, worker = fixture()
                if kind == 'missing':
                    outer['operations'].pop(2)
                elif kind == 'duplicate':
                    outer['operations'].insert(0, deepcopy(outer['operations'][0]))
                elif kind == 'reversed':
                    outer['operations'].reverse()
                else:
                    outer['operations'].append({'argv': ['owned-later-operation']})
                with self.assertRaisesRegex(EXPORT.ExportError, '^actual_lifecycle_records$'):
                    self.receipt(outer, worker)

    def test_nonfinite_and_duplicate_json_keys_rejected_without_leaking_values(self):
        for raw, error in [(b'{"owned":NaN}', 'nonfinite_json'), (b'{"owned":Infinity}', 'nonfinite_json'),
                           (b'{"owned":-Infinity}', 'nonfinite_json'),
                           (b'{"owned":1,"owned":"OWNED_SECRET_SENTINEL"}', 'duplicate_json_key')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(EXPORT.ExportError, '^' + error + '$'):
                EXPORT.decode(raw)

    def test_missing_required_evidence_rejected(self):
        outer, worker = fixture()
        del outer['diagnostic_frozen_target']
        with self.assertRaisesRegex(EXPORT.ExportError, '^malformed_required_evidence$'):
            self.receipt(outer, worker)

    def test_input_bound_and_symlink_rejected(self):
        with self.assertRaisesRegex(EXPORT.ExportError, '^input_byte_bound$'):
            EXPORT.decode(b' ' * (EXPORT.MAX_INPUT + 1))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'owned.json'
            target.write_bytes(b'{}')
            self.assertEqual(EXPORT.bounded_file(target), b'{}')
            link = root / 'link.json'
            link.symlink_to(target)
            with self.assertRaisesRegex(EXPORT.ExportError, '^input_path$'):
                EXPORT.bounded_file(link)

    def test_new_bound_failure_keeps_only_safe_operation_and_error(self):
        outer, worker = fixture()
        outer['status'] = 'UNPROVEN'
        outer['error'] = {'type': 'ValueError', 'message': 'operation_failed:docker'}
        worker['status'] = 'UNPROVEN'
        worker['error_type'] = 'MemoryError'
        result = EXPORT.failure_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)
        self.assertEqual(result['status'], 'UNPROVEN')
        self.assertEqual(result['actual_operation_bindings'], 'verified')
        self.assertEqual(result['operation']['source_sha'], HEAD)
        self.assertEqual(result['error'], {'type': 'ValueError', 'code': 'operation_failed_docker'})
        self.assertEqual(result['worker_error_type'], 'MemoryError')
        self.assertNotIn('worker_receipt_sha256', result['operation'])
        self.assertNotIn('comparison', result)
        self.assertNotIn('diagnostic_image', result)
        self.assertNotIn('container', result)

    def test_missing_early_failure_records_unavailable_bindings(self):
        for outer_raw in (None, b'not json', EXPORT.canonical({'status': 'UNPROVEN'})):
            with self.subTest(outer_raw=outer_raw):
                result = EXPORT.failure_receipt(outer_raw, None, HEAD, DRIVER, RUN)
                self.assertEqual(result['status'], 'UNPROVEN')
                self.assertEqual(result['stage'], 'private_preparation_or_driver_not_reached')
                self.assertEqual(result['actual_operation_bindings'], 'unavailable')
                self.assertNotIn('operation', result)
                self.assertNotIn(HEAD.encode(), EXPORT.canonical(result))

    def test_wrong_failure_binding_does_not_record_operation(self):
        for path, replacement in [(['operation', 'head'], '0' * 40),
                                  (['operation', 'driver_sha256'], '0' * 64),
                                  (['operation', 'run_id'], '88888888888'),
                                  (['operation', 'run_attempt'], True)]:
            with self.subTest(path=path):
                outer, worker = fixture()
                outer['status'] = 'UNPROVEN'
                at(outer, path, replacement)
                result = EXPORT.failure_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)
                self.assertEqual(result['actual_operation_bindings'], 'unavailable')
                self.assertNotIn('operation', result)

    def test_failure_secrets_signed_urls_and_history_map_to_fixed_code(self):
        secrets = ['OWNED_SECRET_SENTINEL', 'https://fixture.invalid/archive?sig=OWNED_SIGNED_URL',
                   'private_historical_run_sentinel', 'operation_failed:OWNED_SECRET_SENTINEL']
        for secret in secrets:
            with self.subTest(secret=secret):
                outer, worker = fixture()
                outer['status'] = worker['status'] = 'UNPROVEN'
                outer['error'] = {'type': secret, 'message': secret, 'raw_history': secret}
                outer['cleanup_error'] = {'type': secret, 'message': secret}
                outer['operation']['runner'] = secret
                outer['old_pins'] = {'private_hash': secret}
                worker['error_type'] = secret
                result = EXPORT.failure_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)
                self.assertEqual(result['error'], {'code': 'diagnostic_failed'})
                self.assertEqual(result['cleanup_error'], {'code': 'diagnostic_cleanup_failed'})
                self.assertNotIn('worker_error_type', result)
                self.assertNotIn(secret.encode(), EXPORT.canonical(result))
                self.assertLessEqual(len(EXPORT.canonical(result)) + 1, EXPORT.MAX_OUTPUT)

    def test_failure_worker_error_requires_exact_failure_schema(self):
        outer, worker = fixture()
        outer['status'] = 'UNPROVEN'
        worker['error_type'] = 'ValueError'
        result = EXPORT.failure_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)
        self.assertNotIn('worker_error_type', result)
        worker['status'] = 'UNPROVEN'
        worker['schema'] = 'owned-incorrect-schema'
        result = EXPORT.failure_receipt(*encoded(outer, worker), HEAD, DRIVER, RUN)
        self.assertNotIn('worker_error_type', result)

    def test_main_absent_or_malformed_outer_writes_bounded_unavailable_failure(self):
        for malformed in (False, True):
            with self.subTest(malformed=malformed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                outer, worker, output = root / 'outer.json', root / 'worker.json', root / 'new.json'
                if malformed:
                    outer.write_bytes(b'{"PRIVATE_HISTORICAL_SECRET":not-json}')
                argv = ['exporter', '--outer', str(outer), '--worker', str(worker),
                        '--expected-source', HEAD, '--expected-driver-sha256', DRIVER,
                        '--expected-run-id', RUN, '--output', str(output)]
                with patch.object(EXPORT.sys, 'argv', argv), redirect_stdout(io.StringIO()):
                    EXPORT.main()
                raw = output.read_bytes()
                result = EXPORT.decode(raw)
                self.assertEqual(result['status'], 'UNPROVEN')
                self.assertEqual(result['actual_operation_bindings'], 'unavailable')
                self.assertNotIn('operation', result)
                self.assertNotIn(b'PRIVATE_HISTORICAL_SECRET', raw)
                self.assertLessEqual(len(raw), EXPORT.MAX_OUTPUT)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_main_invalid_success_still_raises_and_writes_no_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outer, worker = fixture()
            worker['native_execution'] = True
            outer_raw, worker_raw = encoded(outer, worker)
            outer_path, worker_path, output = root / 'outer.json', root / 'worker.json', root / 'new.json'
            outer_path.write_bytes(outer_raw)
            worker_path.write_bytes(worker_raw)
            argv = ['exporter', '--outer', str(outer_path), '--worker', str(worker_path),
                    '--expected-source', HEAD, '--expected-driver-sha256', DRIVER,
                    '--expected-run-id', RUN, '--output', str(output)]
            with patch.object(EXPORT.sys, 'argv', argv), self.assertRaisesRegex(EXPORT.ExportError, '^worker_forbidden_claim$'):
                EXPORT.main()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
