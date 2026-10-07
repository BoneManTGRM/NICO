"""Export one NEW successful diagnostic through an explicit small allowlist.

No provider, Docker, compiler, analyzer or target calls. Private input objects are
validated in place; they are never copied wholesale or pruned into the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

MAX_INPUT = 8 * 1024 * 1024
MAX_OUTPUT = 128 * 1024
MEMORY = 12884901888
TMPFS = 9663676416
TMPFS_OPTIONS = 'rw,nosuid,nodev,noexec,size=9663676416,mode=1777'
OUTER_SCHEMA = 'nico.c34.same_image_parser_outer_receipt.v1'
WORKER_SCHEMA = 'nico.private.runtime_parser_diagnostic.v1'
EXCEPTION_TYPES = frozenset({'ValueError', 'TypeError', 'KeyError', 'RuntimeError', 'OSError',
                            'FileNotFoundError', 'PermissionError', 'TimeoutExpired', 'CalledProcessError',
                            'KeyboardInterrupt', 'SystemExit', 'MemoryError', 'UnicodeError', 'JSONDecodeError'})
# Closed public diagnostic error vocabulary; a regex alone could preserve a
# lower-case secret. Unknown/private strings are mapped to a fixed generic code.
ERROR_CODES = frozenset({'bounded_operation_output', 'compact_receipt_limit', 'canonical_driver_path',
                         'new_output_required', 'exact_image_helper_hash', 'derived_image_identity',
                         'diagnostic_source_binding', 'actual_candidate_git_blob',
                         'mounted_runtime_source_binding', 'container_inspection_population',
                         'actual_fixed_container_binding', 'bounded_container_receipt',
                         'actual_container_diagnostic_receipt', 'container_terminal_state',
                         'diagnostic_cleanup_failed', 'operation_failed_docker'})


class ExportError(ValueError):
    """Fixed safe error code, without raw input values."""


def require(value, code):
    if not value:
        raise ExportError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_INPUT, 'input_byte_bound')
    try:
        result = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: require(False, 'nonfinite_json'))
    except ExportError:
        raise
    except (ValueError, UnicodeError):
        raise ExportError('invalid_json') from None
    require(isinstance(result, dict), 'input_object')
    return result


def hexadecimal(value, length, code):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None, code)
    return value


def integer(value, wanted, code):
    require(type(value) is int and value == wanted, code)
    return value


def positive(value, maximum, code):
    require(type(value) is int and 0 < value <= maximum, code)
    return value


def truth(mapping, name, wanted, code):
    require(mapping.get(name) is wanted, code)


def finite_ms(value):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 480000,
            'timing_value')
    return value


def failure_receipt(outer_raw, worker_raw, expected_source, expected_driver_sha256, expected_run_id):
    """Record only current-operation failure, never historical/private details."""
    expected_source = hexadecimal(expected_source, 40, 'expected_source')
    expected_driver_sha256 = hexadecimal(expected_driver_sha256, 64, 'expected_driver')
    require(type(expected_run_id) is str and re.fullmatch('[1-9][0-9]{0,24}', expected_run_id) is not None,
            'expected_current_run')
    result = {'schema': 'nico.new.same_image_ast_diagnostic.failure.v1', 'status': 'UNPROVEN',
              'stage': 'private_preparation_or_driver_not_reached',
              'actual_operation_bindings': 'unavailable'}
    try:
        outer = decode(outer_raw) if outer_raw is not None else None
    except ExportError:
        outer = None
    if not isinstance(outer, dict) or outer.get('schema') != OUTER_SCHEMA or outer.get('status') != 'UNPROVEN':
        return result
    operation = outer.get('operation')
    if not (isinstance(operation, dict) and operation.get('head') == expected_source
            and operation.get('driver_sha256') == expected_driver_sha256
            and operation.get('run_id') == expected_run_id
            and type(operation.get('run_attempt')) is int and operation['run_attempt'] == 1):
        return result
    result.update(stage='current_diagnostic_driver_failed', actual_operation_bindings='verified')
    result['operation'] = {'source_sha': expected_source, 'run_id': expected_run_id,
                           'run_attempt': 1, 'driver_sha256': expected_driver_sha256}
    tree = operation.get('tree')
    if type(tree) is str and re.fullmatch('[0-9a-f]{40}', tree) is not None:
        result['operation']['source_tree'] = tree
    error = outer.get('error')
    if isinstance(error, dict):
        safe = {'code': 'diagnostic_failed'}
        message = error.get('message')
        if message == 'operation_failed:docker':
            message = 'operation_failed_docker'
        if type(message) is str and re.fullmatch('[a-z0-9_]+', message) is not None and message in ERROR_CODES:
            safe['code'] = message
        if type(error.get('type')) is str and error['type'] in EXCEPTION_TYPES:
            safe['type'] = error['type']
        result['error'] = safe
    if isinstance(outer.get('cleanup_error'), dict):
        result['cleanup_error'] = {'code': 'diagnostic_cleanup_failed'}
        value = outer['cleanup_error'].get('type')
        if type(value) is str and value in EXCEPTION_TYPES:
            result['cleanup_error']['type'] = value
    try:
        worker = decode(worker_raw) if worker_raw is not None else None
    except ExportError:
        worker = None
    if (isinstance(worker, dict) and worker.get('schema') == WORKER_SCHEMA
            and worker.get('status') == 'UNPROVEN' and type(worker.get('error_type')) is str
            and worker['error_type'] in EXCEPTION_TYPES):
        result['worker_error_type'] = worker['error_type']
    require(len(canonical(result)) + 1 <= MAX_OUTPUT, 'compact_output_bound')
    return result


def make_receipt(outer_raw, worker_raw, expected_source, expected_driver_sha256, expected_run_id):
    """Only fixed named scalar/list fields are constructed below."""
    expected_source = hexadecimal(expected_source, 40, 'expected_source')
    expected_driver_sha256 = hexadecimal(expected_driver_sha256, 64, 'expected_driver')
    require(type(expected_run_id) is str and re.fullmatch('[1-9][0-9]{0,24}', expected_run_id) is not None,
            'expected_current_run')
    outer, worker = decode(outer_raw), decode(worker_raw)
    try:
        require(outer.get('schema') == OUTER_SCHEMA and worker.get('schema') == WORKER_SCHEMA,
                'diagnostic_schemas')
        require(outer.get('status') == 'RETRIEVED_IMAGE_AST_PARSER_DIAGNOSTIC_VERIFIED'
                and worker.get('status') == 'SAME_IMAGE_AST_HELPERS_VERIFIED', 'diagnostic_status')
        require(outer['container_receipt_sha256'] == digest(worker_raw), 'exact_worker_receipt_hash')
        for key in ('production_qualified', 'historical_image_recovered', 'target_execution',
                    'analyzer_execution', 'registry_push', 'release_or_merge', 'new_image_build',
                    'full_native_qualified', 'setup_or_analyzer_throughput_improvement_proved'):
            truth(outer, key, False, 'outer_forbidden_claim')
        for key in ('production_qualified', 'target_execution', 'native_execution', 'analyzer_execution',
                    'assessed_compiler_execution', 'full_producer_sequence_executed',
                    'full_native_qualified', 'module_or_PROGRAM_executed',
                    'historical_image_recovered', 'historical001f_measurement'):
            truth(worker, key, False, 'worker_forbidden_claim')
        for key in ('cleanup_verified', 'container_create_attempted', 'container_create_completed'):
            truth(outer, key, True, 'outer_completion')
        for key in ('diagnostic_container_executed', 'actual_retained_outputs_identical', 'original_inputs_unchanged'):
            truth(worker, key, True, 'worker_completion')
        require(outer.get('error') is None and worker.get('forbidden_events') == [], 'diagnostic_failure')
        operation = outer['operation']
        require(operation['head'] == expected_source and operation['driver_sha256'] == expected_driver_sha256
                and operation['run_id'] == expected_run_id, 'new_operation_binding')
        tree = hexadecimal(operation['tree'], 40, 'operation_tree')
        integer(operation['run_attempt'], 1, 'new_operation_attempt')
        require(operation['archive_helper_sha256'] ==
                '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344',
                'reviewed_archive_helper')
        recipe = outer['unchanged_recipe_source']
        recipe_commit = hexadecimal(recipe['commit'], 40, 'recipe_commit')
        recipe_tree = hexadecimal(recipe['tree'], 40, 'recipe_tree')
        integer(recipe['tracked_files'], 3305, 'recipe_population')
        recipe_population = hexadecimal(recipe['tracked_byte_blob_mode_inventory_sha256'], 64, 'recipe_inventory')
        frozen = outer['diagnostic_frozen_target']
        require(frozen['repository'] == 'bitcoin/bitcoin', 'frozen_repository')
        frozen_commit = hexadecimal(frozen['commit'], 40, 'frozen_commit')
        frozen_tree = hexadecimal(frozen['tree'], 40, 'frozen_tree')
        target_population = hexadecimal(frozen['target_population_sha256'], 64, 'frozen_population')
        proof, inspection = outer['archive_proof'], outer['loaded_image_inspection']
        image = inspection['Id']
        require(type(image) is str and re.fullmatch('sha256:[0-9a-f]{64}', image) is not None
                and image == proof['config_id'] and image[7:] == proof['config_sha256']
                and inspection['Os'] == 'linux' and inspection['Architecture'] == 'amd64', 'image_binding')
        truth(proof, 'all_layer_diffids_verified', True, 'every_layer_verification')
        truth(proof, 'safe_unique_outer_regular_or_directory_members', True, 'image_archive_paths')
        truth(proof, 'target_execution', False, 'image_target_execution')
        layers = inspection['RootFS']['Layers']
        require(type(layers) is list and 0 < len(layers) <= 256 and all(type(x) is str and
                re.fullmatch('sha256:[0-9a-f]{64}', x) is not None for x in layers), 'image_layers')
        integer(proof['layer_reference_count'], len(layers), 'image_layer_count')
        unique_layers = positive(proof['unique_layer_members'], len(layers), 'unique_image_layers')
        layer_rows = proof['layer_rows']
        require(type(layer_rows) is list and len(layer_rows) == len(layers), 'proved_layer_rows')
        distinct_layers = {}
        for index, row in enumerate(layer_rows):
            integer(row['index'], index, 'proved_layer_index')
            require(row['diff_id'] == layers[index] and type(row['path']) is str, 'proved_layer_identity')
            hexadecimal(row['stored_sha256'], 64, 'proved_layer_stored_sha')
            positive(row['stored_bytes'], 3 * 1024 ** 3, 'proved_layer_stored_size')
            positive(row['expanded_bytes'], 3 * 1024 ** 3, 'proved_layer_expanded_size')
            require(type(row['gzip']) is bool, 'proved_layer_format')
            metadata = {key: value for key, value in row.items() if key != 'index'}
            if row['path'] in distinct_layers:
                require(metadata == distinct_layers[row['path']], 'reused_layer_metadata')
            else:
                distinct_layers[row['path']] = metadata
        integer(unique_layers, len(distinct_layers), 'proved_unique_layers')
        expanded_total = sum(row['expanded_bytes'] for row in distinct_layers.values())
        positive(expanded_total, 3 * 1024 ** 3, 'unique_layer_expanded_bound')
        integer(proof['total_unique_expanded_layer_bytes'], expanded_total, 'proved_expanded_total')
        archive_sha = hexadecimal(proof['archive']['sha256'], 64, 'image_archive_sha')
        archive_bytes = positive(proof['archive']['bytes'], 3 * 1024 ** 3, 'image_archive_size')
        meta, terminal = outer['container_before'], outer['container_terminal']
        config, host = meta['Config'], meta['HostConfig']
        require(meta['Image'] == image and config['User'] == '1000:1000'
                and config['Entrypoint'] == ['python3'] and host['NetworkMode'] == 'none'
                and host['ReadonlyRootfs'] is True, 'actual_container_identity')
        integer(host['NanoCpus'], 4000000000, 'actual_cpu')
        integer(host['Memory'], MEMORY, 'actual_memory')
        integer(host['MemorySwap'], MEMORY, 'actual_swap')
        integer(host['PidsLimit'], 256, 'actual_pids')
        require(host['Tmpfs'] == {'/work': TMPFS_OPTIONS} and host['CapDrop'] == ['ALL']
                and 'no-new-privileges' in host['SecurityOpt'], 'actual_container_sandbox')
        mounts = meta['Mounts']
        require(type(mounts) is list, 'actual_mounts')
        binds = [m for m in mounts if m.get('Type') == 'bind']
        require(len(binds) == 3 and {m['Destination'] for m in binds} == {'/diag', '/evidence', '/identity'}
                and all(m.get('RW') is False for m in binds), 'minimal_readonly_mounts')
        other = [m for m in mounts if m.get('Type') != 'bind']
        require(len(other) <= 1 and all(m.get('Type') == 'tmpfs' and m.get('Destination') == '/work' for m in other),
                'unexpected_mount')
        for value in config.get('Env', []):
            require(type(value) is str and value.split('=', 1)[0] not in {'GITHUB_TOKEN', 'GH_TOKEN',
                    'ACTIONS_RUNTIME_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_URL'},
                    'container_credential')
        truth(terminal, 'Running', False, 'terminal_running')
        truth(terminal, 'OOMKilled', False, 'terminal_oom')
        integer(terminal['ExitCode'], 0, 'terminal_exit')
        # Validate actual command records in place; no argv/path/stderr is exported.
        operations = outer['operations']
        require(type(operations) is list and 0 < len(operations) <= 64, 'operation_records')
        name = 'nico-parser-' + expected_run_id + '-1'
        load = [(i, row) for i, row in enumerate(operations)
                if row.get('argv', [])[:4] == ['docker', 'image', 'load', '--input']]
        start = [(i, row) for i, row in enumerate(operations)
                 if row.get('argv') == ['docker', 'start', '--attach', name]]
        cleanup = [(i, row) for i, row in enumerate(operations)
                   if row.get('argv') == ['docker', 'rm', '--force', name]]
        require(len(load) == len(start) == len(cleanup) == 1
                and load[0][0] < start[0][0] < cleanup[0][0]
                and cleanup[0][0] == len(operations) - 1
                and len(load[0][1]['argv']) == 5, 'actual_lifecycle_records')
        for row, seconds in ((load[0][1], 90), (start[0][1], 480), (cleanup[0][1], 5)):
            integer(row['timeout_seconds'], seconds, 'actual_lifecycle_deadline')
            truth(row, 'timed_out', False, 'actual_lifecycle_timeout')
            integer(row['exit_code'], 0, 'actual_lifecycle_exit')
        environment = worker['environment']
        truth(environment, 'isolated', True, 'python_isolation')
        truth(environment, 'no_site', True, 'python_site')
        truth(environment, 'root_read_only', True, 'worker_readonly')
        truth(environment, 'network_none_verified_by_outer_driver', True, 'worker_network')
        integer(environment['uid'], 1000, 'worker_uid')
        integer(environment['gid'], 1000, 'worker_gid')
        cpu = environment['cpu_max']
        require(type(cpu) is list and len(cpu) == 2 and all(type(x) is str and x.isdecimal() for x in cpu),
                'worker_cpu_schema')
        quota, period = int(cpu[0]), int(cpu[1])
        require(0 < period <= 1000000 and quota == 4 * period, 'worker_cpu_limit')
        require(environment['memory_max'] == str(MEMORY) and environment['pids_max'] == '256',
                'worker_cgroup_limits')
        options = environment['tmpfs_options']
        require(type(options) is list and all(type(x) is str for x in options)
                and all(x in options for x in ('noexec', 'nosuid', 'nodev'))
                and ('size=9437184k' in options or 'size=9663676416' in options), 'worker_tmpfs')
        identity = environment['outer_identity']
        require(identity['image_config_id'] == image and identity['image_archive_sha256'] == archive_sha
                and identity['complete_archive_verified'] is True and identity['network'] == 'none'
                and identity['read_only'] is True and identity['user'] == '1000:1000', 'worker_image_binding')
        python = environment['python']
        require(type(python) is str, 'python_version')
        version = re.match(r'^([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{1,3})(?:\s|$)', python)
        require(version is not None and int(version[1]) == 3, 'python_version')
        integer(worker['execution_wall_limit_seconds'], 480, 'worker_wall_limit')
        peak = positive(worker['memory_peak_bytes_including_untimed_preparation_and_controls'], MEMORY, 'worker_memory_peak')
        provenance = worker['input_provenance']
        for key, count in [('runtime_members_verified', 3), ('target_digest_population', 3031),
                           ('raw_compiler_records', 577), ('snapshot_files', 143), ('generated_units', 42),
                           ('nonempty_dependency_lists', 576), ('fallback_obligations_executed', 0)]:
            integer(provenance[key], count, 'retained_input_count')
        truth(provenance, 'snapshot_header_dependencies_verified', False, 'retained_header_state')
        truth(provenance, 'genuine_dummy_error_retained', True, 'genuine_error')
        truth(provenance, 'host_original_32_member_and_provider_zip_verification_required', True, 'host_verification_required')
        truth(provenance, 'historical_selection_or_receipt_metadata_mounted', False, 'private_history_mount')
        obligations = worker['required_full_obligations_unchanged']
        integer(obligations['contexts'], 577, 'context_obligation')
        integer(obligations['fallback_contexts'], 576, 'fallback_obligation')
        truth(obligations, 'full_headers_and_generated_inputs', True, 'coverage_obligation')
        integer(worker['fixture_pairs'], 41, 'fixture_pairs')
        integer(worker['individual_fixture_calls'], 82, 'fixture_calls')
        checks = worker['fixture_checks']
        require(type(checks) is list and len(checks) == 41 and len({x['name'] for x in checks}) == 41,
                'fixture_check_population')
        for row in checks:
            require(type(row['accepted']) is bool and row['same_output_or_exact_error'] is True,
                    'fixture_check_verdict')
            hexadecimal(row['outcome_sha256'], 64, 'fixture_outcome_hash')
        outputs_sha = hexadecimal(worker['outputs_sha256'], 64, 'equivalent_output_digest')
        rows = worker['timings']
        require(type(rows) is list and len(rows) == 2 and [x['variant'] for x in rows] == ['baseline', 'candidate'],
                'timing_population')
        timings = []
        for row in rows:
            integer(row['dependency_lists'], 576, 'timing_list_count')
            timings.append({'variant': row['variant'], 'dependency_lists': 576,
                            'wall_ms': finite_ms(row['wall_ms']), 'process_cpu_ms': finite_ms(row['process_cpu_ms'])})
        # Construct only this NEW receipt; no raw source object enters it.
        result = {
            'schema': 'nico.new.same_image_ast_diagnostic.compact.v1',
            'status': 'NEW_DIAGNOSTIC_AST_COMPARISON_VERIFIED',
            'operation': {'source_sha': expected_source, 'source_tree': tree, 'run_id': expected_run_id,
                          'run_attempt': 1, 'driver_sha256': expected_driver_sha256,
                          'worker_receipt_sha256': digest(worker_raw)},
            'diagnostic_image': {'config_id': image, 'archive_sha256': archive_sha, 'archive_bytes': archive_bytes,
                                 'layer_references': len(layers), 'unique_layers': unique_layers,
                                 'complete_archive_and_loaded_identity_verified': True,
                                 'historical_image_recovered': False},
            'public_recipe': {'commit': recipe_commit, 'tree': recipe_tree, 'tracked_files': 3305,
                              'tracked_inventory_sha256': recipe_population},
            'frozen_target': {'repository': 'bitcoin/bitcoin', 'commit': frozen_commit, 'tree': frozen_tree,
                              'target_population_sha256': target_population, 'target_digests': 3031},
            'resources': {'cpus': 4, 'memory_bytes': MEMORY, 'memory_swap_bytes': MEMORY, 'pids': 256,
                          'tmpfs_bytes': TMPFS, 'load_seconds': 90, 'execution_seconds': 480, 'cleanup_seconds': 5,
                          'network': 'none', 'read_only': True, 'user': '1000:1000'},
            'runtime': {'python': {'major': int(version[1]), 'minor': int(version[2]), 'micro': int(version[3])},
                        'cpu_quota_us': quota, 'cpu_period_us': period, 'memory_max_bytes': MEMORY, 'pids_max': 256,
                        'memory_peak_bytes_including_untimed_preparation_and_controls': peak},
            'retained_inputs': {'raw_compiler_records': 577, 'nonempty_dependency_lists': 576,
                                'snapshot_files': 143, 'generated_units': 42, 'genuine_error_input_retained': True,
                                'header_dependencies_verified': False, 'fallback_obligations_executed': 0},
            'comparison': {'fixture_pairs': 41, 'individual_fixture_calls': 82,
                           'all_fixture_outputs_or_errors_equivalent': True,
                           'retained_outputs_equivalent': True, 'original_inputs_unchanged': True,
                           'outputs_sha256': outputs_sha, 'timings': timings},
            'container': {'execution_verified': True, 'running': False, 'exit_code': 0, 'oom_killed': False,
                          'cleanup_verified': True},
            'limitations': {'cache_state': 'unknown', 'order': 'baseline_then_candidate', 'original_cold': False,
                            'whole_producer_sequence': False, 'analyzer_execution': False,
                            'assessed_compiler_execution': False, 'library_module_or_PROGRAM_execution': False,
                            'native_execution': False, 'full_qualification': False,
                            'setup_or_analyzer_throughput_improvement_proved': False,
                            'context_obligations': 577, 'fallback_obligations': 576,
                            'full_headers_and_generated_inputs_still_required': True,
                            'production_qualified': False}}
        require(len(canonical(result)) + 1 <= MAX_OUTPUT, 'compact_output_bound')
        return result
    except ExportError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        raise ExportError('malformed_required_evidence') from None


def bounded_file(path):
    path = path.absolute()
    require(path.resolve(strict=True) == path, 'input_path')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_INPUT, 'input_file_bound')
        raw = stream.read(MAX_INPUT + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= MAX_INPUT and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'input_file_changed')
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outer', required=True, type=Path)
    parser.add_argument('--worker', required=True, type=Path)
    parser.add_argument('--expected-source', required=True)
    parser.add_argument('--expected-driver-sha256', required=True)
    parser.add_argument('--expected-run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    outer_raw = bounded_file(args.outer) if args.outer.exists() else None
    worker_raw = bounded_file(args.worker) if args.worker.exists() else None
    try:
        outer = decode(outer_raw) if outer_raw is not None else None
    except ExportError:
        outer = None
    if isinstance(outer, dict) and outer.get('status') != 'UNPROVEN':
        result = make_receipt(outer_raw, worker_raw, args.expected_source,
                              args.expected_driver_sha256, args.expected_run_id)
    else:
        result = failure_receipt(outer_raw, worker_raw, args.expected_source,
                                 args.expected_driver_sha256, args.expected_run_id)
    raw = canonical(result) + b'\n'
    require(len(raw) <= MAX_OUTPUT, 'compact_output_bound')
    output = args.output.absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == output.parent, 'new_output_path')
    with output.open('xb') as stream:
        os.chmod(output, 0o600)
        stream.write(raw)
    print('{"status":"NEW_DIAGNOSTIC_COMPACT_RECEIPT_WRITTEN","full_qualification":false}')


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"status":"UNPROVEN","full_qualification":false}')
        sys.exit(1)
