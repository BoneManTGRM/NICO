"""Closed-allowlist LOCAL export of a newly retained full-static diagnostic pair.

This helper never imports NICO, executes target code, invokes Docker, downloads
anything, or copies an opaque caller receipt. Root must review and execute it.
"""

import importlib.machinery, importlib.util
from pathlib import Path, PurePosixPath
import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import ast
import zlib

MAX_ARTIFACT_BYTES = 48 * 1024 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_EXPORTED_BYTES = 300 * 1024 * 1024
KEYS = {'project-static-environment', 'project-static-evidence', 'project-static-clang-fallback'}
SCHEMAS = {
    'project-static-environment': {'nico.cpp-static-environment.v2', 'nico.cpp-static-environment-failure.v1'},
    'project-static-evidence': {'nico.cpp-project-static-evidence.v4', 'nico.cpp-project-static-failure.v1'},
    'project-static-clang-fallback': {'nico.cpp-clang-fallback-evidence.v7', 'nico.cpp-clang-fallback-failure.v1'},
}
OPERATION_IDS = {'static-image', 'static-create', 'static-start', 'static-private',
    'static-boundary-before', 'static-source', 'static-boundary', 'static-storage',
    'static-restore', *KEYS}
HASH = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
ID = re.compile(r'[A-Za-z0-9_.:-]{1,160}\Z')
PRIVATE_MARKERS = (b'/workspace/', b'/codex/', b'/Users/', b'/home/',
    b'sediment://', b'X-Amz-Credential=', b'X-Amz-Signature=',
    b'Authorization: Bearer ', b'agent.tinyfish.ai/profiles/')
FLAGS = {'extended_compiler_budget': True, 'compiler_environment': True,
         'header_provenance': True, 'collect_completed_compiler_failures': True}
LIMITS = {'stage_execution_seconds': 1020, 'stage_wall_seconds': 1030,
    'primary_wall_seconds': 540, 'primary_case_seconds': 90, 'primary_parallel': 4,
    'fallback_wall_seconds': 480, 'fallback_case_seconds': 120, 'fallback_parallel': 2,
    'cpus': '4', 'memory_bytes': 12884901888, 'pids': '256', 'tmpfs_bytes': 9663676416}
FROZEN_HEAD = 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24'
FROZEN_TREE = '186194c9de7f613d2d323db41cb8ce6bf1e3e549'
FIXED_IMAGE = 'sha256:2de94c121db7ae46df5415a40b33cd2d057fcc3b7bf9aa9d51756ecb4412447e'
BASELINE_COMPILER_SHA = 'be5b8be8386189af7f51e2ce47681b181a6c71a5e8384146da6deb8289e81276'


# Exact fixed require literals from reviewed caller/helper/scope, not error text patterns.
PARENT_VALIDATION_CODES = {
    'CallerRejected': frozenset({
        'actual_operation_authority', 'actual_operation_transport_proof', 'actual_scope_result_contract',
        'actual_source_git_blob', 'canonical_path', 'connected_fresh_worker',
        'data_only_exact_target_population', 'data_only_target_member', 'duplicate_json_key',
        'executing_caller_actual_git_bytes', 'expected_whole_proof_length', 'file_changed',
        'file_digest', 'file_length', 'fixed_image_identity',
        'fresh_process_output_bound', 'fresh_runner_image_preexisting_or_daemon_unavailable', 'fresh_static_process_not_captured',
        'fresh_variant_source_and_scope_contract', 'frozen_target_identity', 'host_load_store_reserve',
        'independent_image_build_binding', 'independent_prior_retrieval_binding', 'isolated_cp311_required',
        'loaded_complete_image_identity', 'loaded_image_changed_after_pair', 'new_data_only_target_required',
        'new_output_required', 'nonfinite_json', 'operation_failed',
        'operation_git_entry', 'operation_output_bound', 'original_git_bytes_and_modes',
        'private_prepared_directory', 'private_receipt_bound', 'private_runner_temp_roots',
        'private_scope_context', 'private_source_copy_binding', 'private_worker_context',
        'private_worker_settings', 'receipt_temporary_exists', 'regular_file_bound',
        'required_cli_argument', 'retained3031_inventory', 'separate_private_output',
        'supported_private_preparation_scope', 'target_expected_commit', 'target_expected_tree',
        'target_git_exact_member', 'target_git_exact_population', 'target_git_original_blob_and_mode',
        'target_inventory_blob', 'target_inventory_member', 'target_inventory_population',
        'target_inventory_tree', 'target_source_commit', 'target_source_tree',
        'trusted_retained_inventory_anchor', 'whole_image_archive_binding', 'worker_actual_source_binding',
        'worker_cli_is_exclusive',
    }),
    'Rejected': frozenset({
        'diagnostic_artifact_bound_invalid', 'diagnostic_artifact_overwrite_rejected', 'diagnostic_receipt_bound_exceeded',
        'duplicate_json_key', 'file_changed_or_oversized', 'file_digest_mismatch',
        'file_size_mismatch', 'file_type_or_size_invalid', 'private_new_output_required',
        'symlink_or_noncanonical_path', 'target_actual_git_tree_mismatch', 'target_executable_mode_mismatch',
        'target_git_blob_mismatch', 'target_git_entry_invalid', 'target_inventory_binding_invalid',
        'target_owner_executable_mode_mismatch', 'target_tree_duplicate', 'target_tree_path_collision',
        'unexpected_stage_result', 'unsafe_relative_path',
    }),
    'ValueError': frozenset({
        'archive_changed', 'archive_changed_during_layer_verification', 'archive_config_digest',
        'archive_config_platform_rootfs', 'archive_duplicate_or_special_member', 'archive_inspected_diffids',
        'archive_layer_missing', 'archive_layer_population', 'archive_manifest_fields',
        'archive_manifest_population', 'archive_member_count', 'archive_member_size',
        'archive_metadata_short_read', 'archive_metadata_size', 'archive_path',
        'archive_size', 'base_config_descriptor', 'base_config_platform_rootfs',
        'base_locator', 'base_manifest_digest', 'base_manifest_layers',
        'base_manifest_schema', 'base_recipe_binding', 'base_repository',
        'build_arguments', 'build_log_retention_limit', 'command_output_limit',
        'compact_receipt_limit', 'config_id', 'cross_job_image_anchor',
        'cross_job_receipt_anchor', 'diagnostic_image_configuration', 'duplicate_json_key',
        'file_changed', 'file_size_or_type', 'fresh_runner_image_preexisting_or_daemon_unavailable',
        'host_python_version', 'image_identity_platform_size', 'image_layers',
        'image_population', 'layer_blob_locator_digest', 'layer_diffid_mismatch',
        'layer_expanded_size', 'layers_total_expanded_size', 'loaded_complete_image_identity',
        'manifest_missing', 'new_output_required', 'operation_authority_identity',
        'operation_workflow_source_identity', 'pinned_base_layer_prefix', 'pinned_provision_or_build_failed',
        'pins_source_identity', 'provision_block_scope', 'provision_lock_changed',
        'provision_receipt_invalid', 'regular_path_required', 'retrieve_arguments',
        'retrieved_archive_changed', 'retrieved_receipt_binding', 'retrieved_root_path',
        'source_commit', 'source_tree', 'trusted_recipe_pin',
        'trusted_source_blob', 'trusted_source_mode', 'trusted_source_population',
        'trusted_source_type', 'unsafe_archive_path', 'unsafe_source_path',
        'untracked_cppcheck_build_input', 'wheel_identity',
    }),
}
SAFE_PARENT_EXCEPTION_TYPES = frozenset({
    'CallerRejected', 'Rejected', 'ValueError', 'TypeError', 'KeyError',
    'OverflowError', 'RecursionError', 'OSError', 'FileNotFoundError',
    'PermissionError', 'RuntimeError', 'JSONDecodeError', 'CalledProcessError',
    'TimeoutExpired',
})



class _VerifiedBufferLoader(importlib.machinery.SourceFileLoader):
    """Import one already verified source buffer, never cached bytecode."""
    def __init__(self, name, path, raw):
        super().__init__(name, str(path))
        self.verified_raw = raw

    def get_data(self, path):
        if path != self.path:
            raise OSError('verified_source_bytecode_unavailable')
        return self.verified_raw

    def set_data(self, path, data, **kwargs):
        # No bytecode cache or source mutation is part of this diagnostic.
        return None


def _import_verified_buffer(path, raw, label, namespace=None):
    loader = _VerifiedBufferLoader(label, path, raw)
    spec = importlib.util.spec_from_loader(label, loader)
    module = importlib.util.module_from_spec(spec)
    if namespace is not None:
        module.__dict__.update(namespace)
    loader.exec_module(module)
    return module

class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def bad_constant(value):
        raise Rejected('nonfinite_json_number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def safe_relative(value):
    require(isinstance(value, str) and value and '\\' not in value and '\0' not in value,
            'unsafe_relative_path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and p.as_posix() == value and
            all(x not in {'', '.', '..', '.git'} for x in value.split('/')), 'unsafe_relative_path')
    return value


def regular(path, maximum, expected=None):
    path = Path(path)
    require(path.absolute() == path.resolve(strict=True), 'symlink_or_noncanonical_path')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= maximum, 'file_type_or_size_invalid')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) == info.st_size <= maximum, 'file_changed_or_oversized')
    if expected is not None:
        require(isinstance(expected, dict) and set(expected) == {'bytes', 'sha256'}, 'file_binding_invalid')
        require(type(expected['bytes']) is int and expected['bytes'] == len(raw), 'file_size_mismatch')
        require(isinstance(expected['sha256'], str) and HASH.fullmatch(expected['sha256'])
                and expected['sha256'] == digest(raw), 'file_digest_mismatch')
    return raw


def checked_hash(value):
    require(isinstance(value, str) and HASH.fullmatch(value), 'digest_field_invalid')
    return value


def scalar(value, kind):
    if kind == 'bool':
        require(type(value) is bool, 'boolean_field_invalid')
    elif kind == 'number':
        require(type(value) in {int, float} and math.isfinite(value) and value >= 0, 'duration_or_count_invalid')
    elif kind == 'exit':
        require(value is None or type(value) is int, 'exit_field_invalid')
    elif kind == 'id':
        require(isinstance(value, str) and ID.fullmatch(value), 'identifier_field_invalid')
    return value


def error_projection(value):
    if value is None:
        return None
    require(isinstance(value, str), 'error_field_invalid')
    if re.fullmatch(r'worker_[a-z0-9_]{1,160}', value):
        return {'code': value}
    return {'opaque_text_sha256': digest(value.encode())}


def parent_error_projection(value):
    """Retain diagnosis without copying a caller's arbitrary private error text.

    A typed fixed-literal match identifies the observed message, not its actual
    callsite or the cause of the failed target copy. The raw caller receipt SHA
    remains the independent byte binding for both classified and opaque errors.
    """
    if value is None:
        return None
    result = {'opaque_error_canonical_sha256': digest(canonical(value)),
        'classification': 'OPAQUE_PARENT_ERROR_SHAPE',
        'exception_type': None, 'exception_type_sha256': None,
        'message_sha256': None, 'validation_code': None,
        'message_hash_encoding': 'UTF8_SURROGATEPASS',
        'verified_failure_callsite_or_cause': False}
    if (not isinstance(value, dict) or set(value) != {'type', 'message'}
            or type(value['type']) is not str or type(value['message']) is not str):
        return result
    kind = value['type']; message = value['message']
    result.update(classification='OPAQUE_PARENT_ERROR',
        exception_type_sha256=digest(kind.encode('utf-8', errors='surrogatepass')),
        message_sha256=digest(message.encode('utf-8', errors='surrogatepass')))
    if kind in SAFE_PARENT_EXCEPTION_TYPES:
        result['exception_type'] = kind
    if message in PARENT_VALIDATION_CODES.get(kind, frozenset()):
        result.update(classification='EXACT_TYPED_FIXED_VALIDATION_LITERAL_MATCH',
                      validation_code=message)
    return result


def compact_population(value):
    """Accept the runner's explicit count/hash projection, never opaque children."""
    if isinstance(value, (list, dict)) and not (isinstance(value, dict) and set(value) == {'count', 'canonical_sha256'}):
        return {'count': len(value), 'canonical_sha256': digest(canonical(value))}
    require(isinstance(value, dict) and set(value) == {'count', 'canonical_sha256'}, 'population_projection_invalid')
    return {'count': scalar(value['count'], 'number'), 'canonical_sha256': checked_hash(value['canonical_sha256'])}


def analysis_projection(value):
    if value is None:
        return None
    require(isinstance(value, dict), 'analysis_object_invalid')
    result = {}
    for key in ('complete', 'collection_complete', 'static_analysis_executed',
                'header_context_evidence_complete', 'header_population_complete',
                'analyzer_header_coverage_verified'):
        if key in value:
            result[key] = scalar(value[key], 'bool')
    for key in ('required_contexts', 'attempted_contexts', 'analyzed_contexts', 'failed_contexts',
                'unparsed_contexts', 'failures', 'findings', 'limitations', 'header_context_evidence',
                'header_population', 'header_unvisited_files', 'generated_contexts', 'generated_files'):
        if key in value:
            result[key] = compact_population(value[key])
    for key in ('native_evidence_sha256', 'compiler_evidence_sha256',
                'compiler_environment_sha256', 'header_tool_manifest_sha256'):
        if key in value:
            result[key] = checked_hash(value[key])
    return result


def execution_projection(value):
    if value is None:
        return None
    require(isinstance(value, dict), 'execution_object_invalid')
    require(all(k in value for k in ('exit_code', 'timed_out', 'output_truncated', 'duration_ms')),
            'execution_fields_missing')
    result = {k: scalar(value[k], kind) for k, kind in
              [('exit_code', 'exit'), ('timed_out', 'bool'), ('output_truncated', 'bool'), ('duration_ms', 'number')]}
    if 'output_sha256' in value:
        result['output_sha256'] = checked_hash(value['output_sha256'])
    return result


def raw_artifact_projection(key, data, image):
    """Validate key/schema and build timings/header/raw-finding digest projections."""
    require(isinstance(data, dict) and isinstance(data.get('schema'), str)
            and data['schema'] in SCHEMAS[key], 'artifact_schema_key_mismatch')
    result = {'schema': data['schema'], 'raw_canonical_sha256': digest(canonical(data))}
    if data['schema'].endswith('-failure.v1'):
        require(set(data) == {'schema', 'error'}, 'failure_artifact_fields_invalid')
        result['failure'] = error_projection(data['error'])
        return result
    result['request_sha256'] = checked_hash(data.get('request_sha256'))
    result['duration_ms'] = scalar(data.get('duration_ms'), 'number')
    if key == 'project-static-environment':
        require(data.get('image_config_digest') == image, 'environment_image_mismatch')
        for name in ('compiler_versions', 'queries', 'headers', 'models'):
            require(isinstance(data.get(name), dict), 'environment_population_invalid')
            result[name] = compact_population(data[name])
        return result
    records = data.get('records')
    require(isinstance(records, list) and len(records) <= 20000, 'context_population_invalid')
    ids = set(); rows = []; counts = {'ordered': len(records), 'attempted': 0, 'unstarted': 0,
                                    'exit_zero': 0, 'nonzero': 0, 'timed_out': 0, 'truncated': 0}
    for index, row in enumerate(records):
        require(isinstance(row, dict), 'context_record_invalid')
        context = scalar(row.get('context_id'), 'id')
        require(context not in ids, 'duplicate_context_id'); ids.add(context)
        execution = execution_projection(row.get('execution'))
        item = {'index': index, 'context_id': context, 'execution': execution,
                'error': error_projection(row.get('error'))}
        counts['unstarted' if execution is None else 'attempted'] += 1
        if execution is not None:
            counts['exit_zero' if execution['exit_code'] == 0 else 'nonzero'] += 1
            counts['timed_out'] += int(execution['timed_out'])
            counts['truncated'] += int(execution['output_truncated'])
        for name in ('header_trace_sha256', 'xml_sha256', 'plist_sha256'):
            if row.get(name) is not None:
                item[name] = checked_hash(row[name])
        rows.append(item)
    result['contexts'] = rows
    result['population'] = counts
    result['context_records_canonical_sha256'] = digest(canonical(records))
    if 'header_tool_receipt_sha256' in data:
        result['header_tool_receipt_sha256'] = checked_hash(data['header_tool_receipt_sha256'])
    if 'wall_budget_ms' in data:
        result['actual_allocated_wall_budget_ms'] = scalar(data['wall_budget_ms'], 'number')
    return result


def retained_raw_projection(key, raw, image):
    """Error/partial stdout is still fresh evidence; never relabel it analyzed."""
    try:
        value = strict_json(raw)
    except (ValueError, UnicodeError, TypeError, RecursionError) as error:
        return {'parse_status': 'UNPARSEABLE_FRESH_STDOUT_UNPROVEN',
                'parse_error_type': type(error).__name__, 'raw_sha256': digest(raw),
                'analysis_or_population_credit': False}
    try:
        if not isinstance(value, dict) or not isinstance(value.get('schema'), str) or value['schema'] not in SCHEMAS[key]:
            return {'parse_status': 'SCHEMA_KEY_MISMATCH_UNPROVEN', 'raw_sha256': digest(raw),
                    'observed_schema_sha256': digest(canonical(value.get('schema'))) if isinstance(value, dict) else None,
                    'analysis_or_population_credit': False}
        return {'parse_status': 'KEY_SCHEMA_AND_DATA_PROJECTION_VALID',
                **raw_artifact_projection(key, value, image)}
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError) as error:
        return {'parse_status': 'INVALID_SCHEMA_DATA_UNPROVEN',
                'projection_error_type': type(error).__name__, 'raw_sha256': digest(raw),
                'analysis_or_population_credit': False}


def timing_rows(values, kind):
    require(isinstance(values, list) and len(values) <= 10000, 'timing_population_invalid')
    result = []
    for row in values:
        require(isinstance(row, dict), 'timing_record_invalid')
        item = {}
        for key in ('kind', 'phase'):
            if key in row:
                item[key] = scalar(row[key], 'id')
        for key in ('duration_ms', 'runner_elapsed_ms', 'bytes'):
            if key in row:
                item[key] = scalar(row[key], 'number')
        for key in ('argv_sha256', 'sha256'):
            if key in row:
                item[key] = checked_hash(row[key])
        item['observation_scope'] = kind
        result.append(item)
    return result


def process_intervals(values):
    require(isinstance(values, list) and len(values) <= 10000, 'process_intervals_invalid')
    rows = []
    for item in values:
        require(isinstance(item, dict), 'process_interval_invalid')
        row = {}
        for key in ('operation', 'phase'):
            if key in item:
                row[key] = scalar(item[key], 'id')
        for key in ('wall_ms', 'process_cpu_ms'):
            if key in item:
                row[key] = scalar(item[key], 'number')
        if 'clock_domain' in item or 'cpu_scope' in item:
            require(item.get('clock_domain') == 'this_process_perf_counter_and_process_time'
                    and item.get('cpu_scope') == 'This host process only; excludes analyzer/container and child-process CPU.', 'process_clock_scope_invalid')
            row.update(clock_domain='this_process_perf_counter_and_process_time',
                       cpu_scope='HOST_PROCESS_ONLY_EXCLUDES_ANALYZER_CONTAINER_CHILD_CPU')
        for key in ('argv_sha256', 'stdout_sha256', 'stderr_sha256'):
            if key in item:
                row[key] = checked_hash(item[key])
        for key in ('stdout_bytes', 'stderr_bytes'):
            if key in item:
                row[key] = scalar(item[key], 'number')
        if 'exit_code' in item:
            row['exit_code'] = scalar(item['exit_code'], 'exit')
        rows.append(row)
    return rows


def dependency_projection(value):
    if value is None:
        return None
    require(isinstance(value, dict) and isinstance(value.get('whole_proof'), dict)
            and isinstance(value.get('actual_current_validation'), dict)
            and value.get('proof_produced_in_this_process') is False, 'dependency_proof_projection_invalid')
    proof = value['whole_proof']
    return {'proof_bytes': scalar(proof.get('bytes'), 'number'),
            'proof_sha256': checked_hash(proof.get('sha256')),
            'actual_current_validation_canonical_sha256': digest(canonical(value['actual_current_validation'])),
            'recorded_current_validation_result': True, 'proof_produced_in_this_process': False}


def target_projection(value, outer=False):
    if value is None:
        return None
    require(isinstance(value, dict) and value.get('file_count') == 3031
            and value.get('bytes') == 49729651 and value.get('tree_sha') == FROZEN_TREE, 'target_population_binding_invalid')
    mode_key = ('all_original_sha256_git_blob_owner_and_any_executable_modes_verified' if outer else
                'all_original_sha256_git_blob_executable_modes_verified')
    require(value.get(mode_key) is True, 'target_modes_hashes_binding_invalid')
    result = {'file_count': 3031, 'bytes': 49729651, 'tree_sha': FROZEN_TREE,
              'all_original_sha256_git_blob_executable_modes_verified': True}
    if outer:
        require(value.get('repository') == 'bitcoin/bitcoin' and value.get('commit_sha') == FROZEN_HEAD
                and value.get('data_only_copy_no_git') is True
                and value.get('target_code_imported_compiled_or_run') is False, 'target_copy_identity_invalid')
        result.update(repository='bitcoin/bitcoin', commit_sha=FROZEN_HEAD,
                      data_only_copy_no_git=True, target_code_imported_compiled_or_run=False)
    return result


def plan_projection(value):
    if value is None:
        return None
    require(isinstance(value, dict) and value.get('schema') == 'nico.private.full_static_adapter_plan.v1', 'plan_schema_invalid')
    require(value.get('flags') == FLAGS and value.get('limits') == LIMITS
            and all(type(value['flags'][k]) is bool for k in FLAGS)
            and all(type(value['limits'][k]) is type(v) for k, v in LIMITS.items()), 'fixed_api_flags_limits_mismatch')
    expected = {'source_population': 3031, 'snapshot_files': 143, 'generated_units': 42,
                'compiler_contexts': 577, 'historical_required_fallback_contexts': 576}
    require(all(type(value.get(k)) is int and value[k] == v for k, v in expected.items()), 'fixed_plan_population_mismatch')
    target = value.get('frozen_target')
    require(isinstance(target, dict) and target.get('repository') == 'bitcoin/bitcoin'
            and target.get('commit_sha') == FROZEN_HEAD and target.get('tree_sha') == FROZEN_TREE, 'fixed_plan_target_mismatch')
    return {'schema': value['schema'], **expected, 'flags': dict(FLAGS), 'limits': dict(LIMITS),
            'frozen_target': {'repository': 'bitcoin/bitcoin', 'commit_sha': FROZEN_HEAD, 'tree_sha': FROZEN_TREE},
            'input_provenance': 'Retained compiler/configuration/snapshot provenance; no new compilation by this diagnostic'}


def stage_boundary_projection(stage):
    result = {}
    for key in ('cleanup_verified', 'boundary_verified', 'scratch_capacity_verified'):
        if key in stage:
            result[key] = scalar(stage[key], 'bool')
        else:
            result[key] = None
    for key in ('scratch_capacity_bytes', 'memory_peak_bytes'):
        result[key] = scalar(stage[key], 'number') if stage.get(key) is not None else None
    for key, expected in ('execution_budget_seconds', 1020), ('wall_budget_seconds', 1030):
        if key in stage:
            require(type(stage[key]) is int and stage[key] == expected, 'stage_budget_mismatch')
        result[key] = stage.get(key)
    if 'resource_profile' in stage:
        require(stage['resource_profile'] == 'cpp-baseline-qualification-v1', 'stage_resource_profile_mismatch')
    result['resource_profile'] = stage.get('resource_profile')
    return result


def verify_variant(row, image, source_binding):
    required = {'id', 'directory', 'diagnostic_result', 'static_stage_receipt'}
    require(isinstance(row, dict) and required.issubset(row)
            and set(row).issubset(required | {'process_receipt', 'stage_receipt_present', 'process_exit_code',
                'settings', 'dependency_before_process', 'fresh_cp311_isolated_process_requested', 'stdout', 'stderr',
                'process_error', 'stage_invocation_attempted'}),
            'variant_contract_invalid')
    variant_id = row['id']; require(variant_id in {'baseline', 'candidate'}, 'variant_id_invalid')
    directory = Path(row['directory'])
    require(directory.is_dir() and directory.absolute() == directory.resolve(strict=True), 'variant_directory_invalid')
    entries = {p.name for p in directory.iterdir()}
    require(entries.issubset({'diagnostic-result.json', 'static-stage-receipt.json', 'process-receipt.json', 'artifacts'}), 'unapproved_variant_file')
    diagnostic_present = row['diagnostic_result'] is not None
    require(('diagnostic-result.json' in entries) is diagnostic_present, 'diagnostic_receipt_presence_mismatch')
    diagnostic_raw = regular(directory / 'diagnostic-result.json', MAX_RECEIPT_BYTES, row['diagnostic_result']) if diagnostic_present else None
    stage_present = row['static_stage_receipt'] is not None
    require(('static-stage-receipt.json' in entries) is stage_present
            and row.get('stage_receipt_present', stage_present) is stage_present, 'stage_receipt_presence_mismatch')
    stage_raw = regular(directory / 'static-stage-receipt.json', MAX_RECEIPT_BYTES, row['static_stage_receipt']) if stage_present else None
    diagnostic = strict_json(diagnostic_raw) if diagnostic_present else {}
    stage = strict_json(stage_raw) if stage_present else None
    require(not diagnostic_present or isinstance(diagnostic, dict) and diagnostic.get('schema') == 'nico.private.static_stage_diagnostic_result.v1', 'diagnostic_schema_invalid')
    require(not stage_present or isinstance(stage, dict) and stage.get('schema') in {'nico.cpp-project-static-stage.v1', 'nico.cpp-project-static-stage.v4'}, 'stage_schema_invalid')
    require((not diagnostic_present or all(diagnostic.get(k) is False for k in ('compiled', 'tests_executed', 'assessment_completed',
            'full_native_qualified', 'production_qualified', 'mock_injection_used'))
            )
            and (not stage_present or stage.get('production_qualified') is False), 'diagnostic_claim_invalid')
    require(not diagnostic_present or not stage_present or diagnostic.get('actual_stage_schema') == stage['schema']
            and diagnostic.get('actual_stage_error') == stage.get('error'), 'diagnostic_stage_mismatch')
    require(not diagnostic_present or stage_present or diagnostic.get('static_stage_complete') is False
            and diagnostic.get('static_collection_complete_with_findings') is False
            and diagnostic.get('actual_stage_schema') is None, 'absent_stage_claim_invalid')
    selected = diagnostic.get('selected_image')
    require(not diagnostic_present or isinstance(selected, dict) and selected.get('selected_config_digest') == image
            and type(selected.get('local_image_config_inspection_verified')) is bool, 'diagnostic_image_binding_invalid')
    library_projection = None
    if diagnostic_present:
        library = diagnostic.get('selected_library')
        compiler_sha = BASELINE_COMPILER_SHA if variant_id == 'baseline' else source_binding['compiler_overlay']['sha256']
        require(isinstance(library, dict) and library.get('variant') == variant_id
                and library.get('selected_library_head') == source_binding['effective_fallback_baseline']
                and library.get('selected_library_tree') == 'b9e200f62b9b2db9c6488326826ad8ae393418d0'
                and library.get('actual_operation') == source_binding.get('actual_operation')
                and library.get('base_inventory_files_verified') == 3305
                and library.get('source_loader_uses_verified_text_not_cached_bytecode') is True
                and library.get('matching_whole_library_and_image_source_inferred') is False,
                'actual_variant_selected_library_binding_invalid')
        compiler = library.get('selected_compiler')
        require(isinstance(compiler, dict) and compiler.get('path') == source_binding['compiler_overlay']['path']
                and compiler.get('sha256') == compiler_sha, 'actual_variant_compiler_binding_invalid')
        library_projection = {'effective_recipe_head': library['selected_library_head'],
            'effective_recipe_tree': library['selected_library_tree'], 'base_inventory_files_verified': 3305,
            'base_inventory_sha256': checked_hash(library.get('base_inventory_sha256')),
            'selected_compiler': {'path': compiler['path'], 'sha256': compiler_sha},
            'source_loader_uses_verified_text_not_cached_bytecode': True,
            'matching_whole_library_and_image_source_inferred': False,
            'actual_operation_proof_canonical_sha256': digest(canonical(library['actual_operation']))}
    process = None
    require(('process-receipt.json' in entries) is (row.get('process_receipt') is not None), 'process_receipt_presence_mismatch')
    if row.get('process_receipt') is not None:
        process_raw = regular(directory / 'process-receipt.json', MAX_RECEIPT_BYTES, row['process_receipt'])
        value = strict_json(process_raw)
        require(isinstance(value, dict) and value.get('schema') == 'nico.private.full_static_process_receipt.v1'
                and value.get('variant') == variant_id and value.get('mock_injection_used') is False
                and all(value.get(k) is False for k in ('full_native_qualified', 'production_qualified',
                    'assessment_completed', 'compiled', 'tests_executed')), 'process_receipt_invalid')
        process = {'receipt_sha256': digest(process_raw)}
        for key in ('duration_ms', 'elapsed_ms', 'wall_elapsed_ms', 'exit_code', 'timed_out', 'output_truncated'):
            if key in value:
                process[key] = scalar(value[key], 'exit' if key == 'exit_code' else 'bool' if key in {'timed_out', 'output_truncated'} else 'number')
        for key in ('stdout_sha256', 'stderr_sha256', 'source_sha256'):
            if key in value:
                process[key] = checked_hash(value[key])
        process['intervals'] = process_intervals(value.get('intervals'))
        process['target_verification_before'] = target_projection(value.get('target_verification'))
        process['target_verification_after'] = target_projection(value.get('target_verification_after_stage'))
        process['dependency_checks'] = {key: dependency_projection(value.get(key)) for key in
            ('dependency_before_preparation', 'dependency_before_stage', 'dependency_after_stage')}
    operations = stage.get('operations') if stage_present else []
    require(isinstance(operations, list) and len(operations) <= 32, 'operations_invalid')
    ids = set(); artifacts = {}; projected = []; inspection = False
    for operation in operations:
        require(isinstance(operation, dict), 'operation_invalid')
        key = operation.get('id'); require(key in OPERATION_IDS and key not in ids, 'operation_id_invalid_or_duplicate'); ids.add(key)
        item = {'id': key, **execution_projection(operation)}
        if key == 'static-image' and operation['exit_code'] == 0 and not operation['timed_out'] and not operation['output_truncated']:
            inspection_raw = base64.b64decode(operation['output'], validate=True)
            require(digest(inspection_raw) == operation.get('output_sha256'), 'image_inspection_output_digest_mismatch')
            observed = strict_json(inspection_raw)
            require(isinstance(observed, list) and len(observed) == 1 and isinstance(observed[0], dict)
                    and observed[0].get('Id') == image, 'fresh_stage_image_inspection_mismatch')
            inspection = True
        reference = operation.get('output_artifact')
        if key in KEYS:
            if reference is None:
                item.update(stage_output_artifact_ref=None, artifact_not_retained=True,
                            artifact_retention='ARTIFACT_NOT_RETAINED', populations=None)
                projected.append(item)
                continue
            require(isinstance(reference, dict) and set(reference) == {'path', 'bytes', 'sha256'}, 'fresh_artifact_reference_missing_or_invalid')
            artifact_hash = checked_hash(reference['sha256'])
            name = safe_relative(reference['path'])
            require(name == f'artifacts/{key}-{artifact_hash}.json', 'artifact_filename_key_digest_mismatch')
            require(artifact_hash == operation.get('output_sha256') and name not in artifacts, 'artifact_operation_digest_mismatch_or_duplicate')
            raw = regular(directory / name, MAX_ARTIFACT_BYTES, {'bytes': reference['bytes'], 'sha256': artifact_hash})
            require(not any(marker in raw for marker in PRIVATE_MARKERS), 'private_host_path_or_access_material_in_artifact')
            projection = retained_raw_projection(key, raw, image)
            artifacts[name] = raw
            item['artifact'] = {'path': variant_id + '/' + name, 'bytes': len(raw), 'sha256': artifact_hash,
                                'key': key, 'raw_projection': projection}
        else:
            require(reference is None, 'non_artifact_operation_reference')
        projected.append(item)
    require(not ids.intersection(KEYS) or inspection, 'static_execution_without_fresh_image_binding')
    artifact_dir = directory / 'artifacts'
    actual_names = set()
    if artifact_dir.exists():
        require(artifact_dir.is_dir() and artifact_dir.absolute() == artifact_dir.resolve(strict=True), 'artifact_directory_invalid')
        for path in artifact_dir.iterdir():
            require(path.is_file() and not path.is_symlink(), 'artifact_nonregular_member')
            actual_names.add('artifacts/' + path.name)
    require(actual_names == set(artifacts), 'unreferenced_or_missing_fresh_artifact')
    stage = stage or {}
    stage_retention_complete = not any(op.get('artifact_not_retained') for op in projected)
    all_schema_projections_valid = all(op['artifact']['raw_projection']['parse_status'] == 'KEY_SCHEMA_AND_DATA_PROJECTION_VALID'
                                      for op in projected if 'artifact' in op)
    summary = {
        'id': variant_id, 'execution_state': 'VARIANT_ROW_RETAINED',
        'diagnostic_result_present': diagnostic_present,
        'diagnostic_result_sha256': digest(diagnostic_raw) if diagnostic_present else None,
        'static_stage_receipt_present': stage_present,
        'static_stage_receipt_sha256': digest(stage_raw) if stage_present else None,
        'actual_stage_schema': stage.get('schema'), 'phase': scalar(stage.get('phase'), 'id') if stage_present else None,
        'actual_stage_error': error_projection(stage.get('error')),
        'retention_integrity': 'VERIFIED_CLOSED_FRESH_ALLOWLIST' if stage_retention_complete else 'INCOMPLETE_STAGE_ARTIFACT_RETENTION',
        'fresh_artifact_schema_projection_all_valid': all_schema_projections_valid,
        'diagnostic_outcome': ('DIAGNOSTIC_RESULT_ABSENT_UNPROVEN' if not diagnostic_present else
            'NO_STAGE_CALLBACK_RETAINED_UNPROVEN' if not stage_present else
            'BROKEN_STAGE_ARTIFACT_RETENTION_UNPROVEN' if not stage_retention_complete else
            'RETAINED_FRESH_BYTES_SCHEMA_OR_PROJECTION_UNPROVEN' if not all_schema_projections_valid else
            'VALID_DIAGNOSTIC_COMPLETE_COLLECTION' if stage.get('collection_complete') is True else 'VALID_DIAGNOSTIC_INCOMPLETE'),
        'static_stage_complete': scalar(stage.get('complete'), 'bool') if stage_present else False,
        'static_collection_complete_with_findings': stage.get('collection_complete') is True,
        'fresh_stage_image_inspection_verified': inspection,
        'actual_stage_duration_ms': scalar(stage.get('duration_ms'), 'number') if stage_present else None,
        'actual_api_total_observed_ms': scalar(diagnostic.get('api_total_observed_ms'), 'number') if diagnostic_present else None,
        'actual_operations': projected,
        'process_observation': process,
        'stage_invocation_attempted': scalar(row['stage_invocation_attempted'], 'bool') if 'stage_invocation_attempted' in row else None,
        'actual_process_exit_code': scalar(row['process_exit_code'], 'exit') if 'process_exit_code' in row else None,
        'actual_selected_library_binding': library_projection,
        'plan': plan_projection(diagnostic.get('plan')),
        'stage_boundary_and_capacity': stage_boundary_projection(stage),
        'analysis': analysis_projection(stage.get('analysis')),
        'compiler_collection_provenance_only': analysis_projection(stage.get('compiler_collection')),
        'static_collection': analysis_projection(stage.get('static_collection')),
        'opaque_subphase_costs': {'request_construction': None, 'validation': None, 'inside_api_retention': None,
                                'cleanup_outside_wrapped_commands': None, 'unstarted_context_costs': None},
        'command_intervals': timing_rows(diagnostic.get('command_intervals', []), 'Runner call elapsed including transport; not CPU time'),
        'retention_callback_intervals': timing_rows(diagnostic.get('retention_callback_intervals', []), 'Runner callback elapsed; not all API retention'),
        'observed_api_phase_callbacks': timing_rows(diagnostic.get('observed_api_phase_callbacks', []), 'Save callback observation; not independent phase timer'),
        'compiled_or_target_tests_executed_by_this_diagnostic': False,
        'full_native_qualified': False, 'production_qualified': False, 'cold_timing_credit': False,
    }
    return summary, {variant_id + '/' + name: raw for name, raw in artifacts.items()}


def write_export(public, files, output, paths, caller_hash):
    summary_bytes = canonical(public)
    require(len(summary_bytes) <= MAX_RECEIPT_BYTES, 'public_summary_bound_exceeded')
    require(not any(marker in summary_bytes for marker in PRIVATE_MARKERS), 'public_summary_private_material')
    files = {**files, 'static-summary.json': summary_bytes}
    total = sum(len(value) for value in files.values())
    require(total <= MAX_TOTAL_EXPORTED_BYTES, 'total_export_bound_exceeded')
    output = Path(output).absolute()
    require(not output.exists() and output.parent == output.parent.resolve(strict=True), 'new_export_directory_required')
    require(all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in paths), 'export_input_directory_collision')
    manifest = {'schema': 'nico.full_static_pair_export_manifest.v1',
        'files': [{'path': name, 'bytes': len(data), 'sha256': digest(data)} for name, data in sorted(files.items())],
        'file_count': len(files), 'listed_bytes': total, 'fresh_only': True,
        'caller_receipt_sha256': caller_hash, 'full_native_or_production_qualification': False}
    manifest_bytes = canonical(manifest)
    require(total + len(manifest_bytes) <= MAX_TOTAL_EXPORTED_BYTES, 'total_export_bound_exceeded')
    output.mkdir(mode=0o700)
    for name, data in {**files, 'manifest.json': manifest_bytes}.items():
        path = output / safe_relative(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    for name, data in files.items():
        require(regular(output / name, max(MAX_ARTIFACT_BYTES, MAX_RECEIPT_BYTES)) == data, 'export_readback_mismatch')
    require(regular(output / 'manifest.json', MAX_RECEIPT_BYTES) == manifest_bytes, 'manifest_readback_mismatch')
    return {'schema': 'nico.full_static_pair_export_receipt.v1', 'export_directory': str(output),
            'manifest_sha256': digest(manifest_bytes), 'public_summary_sha256': digest(summary_bytes),
            'file_count_with_manifest': len(files) + 1, 'total_bytes_with_manifest': total + len(manifest_bytes),
            'closed_allowlist_all_bytes_readback_verified': True, 'full_native_or_production_qualification': False}


def export_pair(receipt_path, output, expected):
    raw = regular(receipt_path, MAX_RECEIPT_BYTES,
                  {'bytes': Path(receipt_path).stat().st_size, 'sha256': expected['caller_receipt_sha256']})
    outer = strict_json(raw)
    require(isinstance(outer, dict) and outer.get('schema') == 'nico.private.full_static_pair_caller.v1', 'caller_schema_invalid')
    require(digest(regular(Path(__file__).absolute(), MAX_RECEIPT_BYTES)) == expected['exporter_sha256'], 'exporter_source_hash_mismatch')
    binding = outer.get('source_binding'); image = outer.get('image_binding')
    if not isinstance(binding, dict) or not isinstance(image, dict):
        require(outer.get('status') == 'UNPROVEN', 'unbound_preflight_must_be_unproven')
        failure = {'schema': 'nico.full_static_pair_export_summary.v1', 'caller_receipt_sha256': digest(raw),
            'exporter_sha256': expected['exporter_sha256'],
            'fixed_failure_code': 'SOURCE_OR_IMAGE_PREFLIGHT_BINDING_ABSENT_UNPROVEN',
            'opaque_caller_failure_sha256': digest(canonical(outer.get('error'))),
            'parent_error': parent_error_projection(outer.get('error')),
            'source_binding': None, 'image_binding': None, 'target_binding': None,
            'raw_artifact_bytes_credit': False, 'raw_artifact_count_exported': 0,
            'pair_complete': False, 'assessment_completed': False, 'full_native_qualified': False,
            'production_qualified': False, 'human_approval_created': False, 'cold_timing_credit': False}
        return write_export(failure, {}, output, [], digest(raw))
    for key in ('current_git_head', 'effective_fallback_baseline'):
        require(binding.get(key) == expected[key] and COMMIT.fullmatch(binding[key]), 'source_commit_binding_mismatch')
    require(binding['effective_fallback_baseline'] == 'f0919654edd719059ea03319981b13f46ba70a88', 'effective_fallback_baseline_mismatch')
    for key in ('exporter_sha256', 'caller_sha256', 'scope_sha256'):
        require(binding.get(key) == expected[key] and HASH.fullmatch(binding[key]), 'source_hash_binding_mismatch')
    require(binding.get('all_selected_files_actual_git_blob_bound') is True
            and binding.get('effective_overlay_is_whole_candidate') is False
            and binding.get('baseline_compiler_sha256') == BASELINE_COMPILER_SHA
            and isinstance(binding.get('actual_operation'), dict), 'selected_source_git_binding_unproved')
    overlay = binding.get('compiler_overlay')
    require(isinstance(overlay, dict) and set(overlay) == {'path', 'sha256'}
            and safe_relative(overlay['path']) == expected['compiler_overlay_path']
            and overlay['path'].startswith('nico/') and overlay['path'].endswith('.py')
            and overlay['sha256'] == expected['compiler_overlay_sha256'], 'compiler_overlay_binding_mismatch')
    selected_image = expected['image_config_digest']
    require(selected_image == FIXED_IMAGE
            and image.get('selected_config_digest') == image.get('fixed_config_digest') == selected_image
            and all(image.get(k) is True for k in ('loaded_image_inspection_verified', 'complete_archive_verified',
                'config_and_ordered_rootfs_equal_independent_build_receipt', 'same_selected_image_for_both_variants'))
            and image.get('historical_image_recovered') is False
            and image.get('matching_historical_live_toolchain_or_header_inputs_inferred') is False, 'fixed_loaded_image_binding_mismatch')
    image_config_rootfs_hash = checked_hash(image.get('config_and_rootfs_sha256'))
    image_after_pair_verified = (scalar(image['config_and_rootfs_verified_after_pair'], 'bool')
                                 if 'config_and_rootfs_verified_after_pair' in image else None)
    require(outer.get('order') == ['baseline', 'candidate'] and outer.get('single_pair_only') is True
            and outer.get('cache_state') == 'UNKNOWN' and outer.get('job_outer_budget_minutes') == 155
            and outer.get('declared_api_wall_seconds') == 1030 and outer.get('shared_execution_seconds') == 1020
            and outer.get('sequential_pair_policy_execution_upper_seconds') == 2040
            and outer.get('independent1030_hardwall_supervisor_present') is False
            and outer.get('parent_cpu_is_analyzer_cpu') is False and outer.get('overlapping_intervals_additive') is False,
            'fixed_pair_order_budget_clock_contract_invalid')
    variants = outer.get('variants')
    require(isinstance(variants, list) and len(variants) <= 2
            and all(isinstance(x, dict) for x in variants)
            and [x.get('id') for x in variants] == ['baseline', 'candidate'][:len(variants)]
            and (len(variants) == 2 or outer.get('status') == 'UNPROVEN'), 'exact_pair_variant_order_invalid')
    paths = [Path(x['directory']).resolve(strict=True) for x in variants]
    require(len(paths) < 2 or paths[0] != paths[1] and not paths[0].is_relative_to(paths[1])
            and not paths[1].is_relative_to(paths[0]), 'variant_directory_alias')
    target = target_projection(outer.get('target_binding'), outer=True)
    require(not variants or target is not None, 'executed_variants_without_target_binding')
    summaries = []; files = {}
    for variant in variants:
        summary, retained = verify_variant(variant, selected_image, binding)
        summaries.append(summary); files.update(retained)
    for variant_id in ['baseline', 'candidate'][len(variants):]:
        summaries.append({'id': variant_id, 'execution_state': 'NOT_RUN',
            'diagnostic_result_present': False, 'static_stage_receipt_present': False,
            'actual_operations': [], 'analysis': None, 'process_observation': None,
            'full_native_qualified': False, 'production_qualified': False, 'cold_timing_credit': False})
    public = {
        'schema': 'nico.full_static_pair_export_summary.v1',
        'caller_receipt_sha256': digest(raw),
        'parent_error': parent_error_projection(outer.get('error')),
        'source_binding': {key: binding[key] for key in ('current_git_head', 'effective_fallback_baseline',
                         'exporter_sha256', 'caller_sha256', 'scope_sha256')},
        'one_compiler_overlay': {'path': overlay['path'], 'sha256': checked_hash(overlay['sha256'])},
        'image_binding': {'selected_config_digest': selected_image, 'fixed_config_digest': selected_image,
            'loaded_image_inspection_verified': True, 'complete_archive_verified': True,
            'config_and_ordered_rootfs_equal_independent_build_receipt': True,
            'same_selected_image_for_both_variants': True, 'exact_original001f_image': False,
            'config_and_rootfs_sha256': image_config_rootfs_hash,
            'config_and_rootfs_verified_after_pair': image_after_pair_verified,
            'matching_historical_live_toolchain_or_header_inputs_inferred': False},
        'target_binding': target,
        'parent_dependency_checks': {key: dependency_projection(outer.get(key)) for key in
            ('dependency_before_image_and_target', 'dependency_after_pair')},
        'parent_observation_intervals': process_intervals(outer.get('intervals')),
        'pair_budget_and_order': {'order': ['baseline', 'candidate'], 'single_pair_only': True,
            'cache_state': 'UNKNOWN', 'job_outer_budget_minutes': 155, 'declared_api_wall_seconds': 1030,
            'shared_execution_seconds': 1020, 'sequential_pair_policy_execution_upper_seconds': 2040,
            'independent1030_hardwall_supervisor_present': False,
            'parent_cpu_is_analyzer_cpu': False, 'overlapping_intervals_additive': False,
            'cold_or_report_performance_measurement': False},
        'variants': summaries,
        'declared_variant_order': ['baseline', 'candidate'],
        'executed_variant_rows_retained': len(variants),
        'both_variant_rows_retained': len(variants) == 2,
        'pair_capture_status': scalar(outer.get('status'), 'id'),
        'pair_complete': len(variants) == 2 and outer.get('status') == 'FULL_STATIC_PAIR_CAPTURED',
        'fresh_artifact_closed_allowlist': sorted(KEYS),
        'maximum_artifact_bytes': MAX_ARTIFACT_BYTES, 'maximum_total_exported_bytes': MAX_TOTAL_EXPORTED_BYTES,
        'reused_compiler_raw_old_pins_source_adapter_or_opaque_receipts_exported': False,
        'no_historical_residual_reattribution_claim': True,
        'assessment_completed': False, 'full_native_qualified': False, 'production_qualified': False,
        'human_approval_created': False, 'cold_timing_credit': False,
    }
    return write_export(public, files, output, paths, digest(raw))


SAMPLE_MAX_NATIVE = 32 * 1024 * 1024
SAMPLE_MAX_TELEMETRY = 128 * 1024
SAMPLE_MAX_TOTAL = 64 * 1024 * 1024
SAMPLE_INDEXES = [0, 58, 154, 186]
SAMPLE_OPERATION_IDS = {'static-image', 'static-create', 'static-start', 'static-private',
    'static-boundary-before', 'static-source', 'static-boundary', 'static-storage',
    'static-restore', 'fallback-capacity-sample', 'fallback-capacity-telemetry'}
SAMPLE_ARTIFACTS = {'fallback-capacity-sample': SAMPLE_MAX_NATIVE,
                    'fallback-capacity-telemetry': SAMPLE_MAX_TELEMETRY}
SAMPLE_LIMITS = {'stage_execution_seconds': 1020, 'stage_wall_seconds': 1030,
    'fallback_wall_seconds': 480, 'fallback_case_seconds': 120, 'fallback_parallel': 2,
    'cpus': '4', 'memory_bytes': 12884901888, 'pids': '256', 'tmpfs_bytes': 9663676416}
SAMPLE_FULL_REQUEST = '2bfd399c965282b8dfe3c34b82861feb8377b5f9abe4ba8c0eb9755614d2a6ce'
SAMPLE_TARGET_POPULATION = 'e82d2f98f2fae7a877ba9e81fac6cac5791cf3c54cf3cd5f13d810ad65659ba2'
SAMPLE_GENERATED_POPULATION = '896428a6f2ac9fdbeaa13df999c63347ade97e92364973fbdd1e6c242756f880'
SAMPLE_COMPILER = '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8'
SAMPLE_SOURCE_PATHS = {'caller': 'scripts/cpp_same_image_full_static_diagnostic.py',
    'scope': 'scripts/cpp_static_runner_scope.py', 'sample': 'scripts/cpp_fallback_capacity_sample.py',
    'exporter': 'scripts/cpp_full_static_diagnostic_export.py'}
SAMPLE_FALSE_PARENT = ('primary_native_execution', 'full_native_qualified', 'production_qualified',
                       'assessment_completed', 'static_collection_complete', 'historical_image_recovered')
SAMPLE_FALSE_DIAGNOSTIC = ('primary_native_execution', 'compiled', 'tests_executed', 'full_native_qualified',
    'production_qualified', 'assessment_completed', 'static_collection_complete', 'human_approval_created',
    'cold_timing_credit', 'memory_oom_cause_inferred', 'independent1030_hardwall_supervisor_present')


def sample_source_validation(caller_source, sample_source, expected):
    """Execute only exact checked pure validator definitions, never a module entry."""
    caller_raw = regular(caller_source, MAX_RECEIPT_BYTES,
        {'bytes': Path(caller_source).stat().st_size, 'sha256': expected['caller_sha256']})
    sample_raw = regular(sample_source, MAX_RECEIPT_BYTES,
        {'bytes': Path(sample_source).stat().st_size, 'sha256': expected['sample_sha256']})
    caller_tree = ast.parse(caller_raw)
    route = {}
    for node in caller_tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {'REPOSITORY', 'BRANCH', 'WORKFLOW', 'JOB'}:
                route[name] = ast.literal_eval(node.value)
    require(route == {'REPOSITORY': 'BoneManTGRM/NICO',
        'BRANCH': 'refs/heads/diagnostic/v17-pinned-image-20261007',
        'WORKFLOW': '.github/workflows/cpp-same-image-full-static-diagnostic.yml',
        'JOB': 'same-image-full-static-diagnostic'}, 'sample_checked_caller_fixed_route')
    codes = set()
    for node in ast.walk(caller_tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'require'
                and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                and type(node.args[1].value) is str):
            codes.add(node.args[1].value)
    tree = ast.parse(sample_raw)
    names = ('require', 'canonical', 'sha', 'decode', 'finite_nonnegative', 'parse_cgroup',
             'counter_deltas', 'check_envelope', 'validate_sample_telemetry')
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    require(all(name in nodes for name in names), 'sample_pure_validator_definition_missing')
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {'CGROUP_FILES', 'SOURCE_PINS', 'LIMITS'}:
                constants[name] = ast.literal_eval(node.value)
    require(constants.get('LIMITS') == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
            and constants.get('CGROUP_FILES') == ('cpu.stat', 'memory.events', 'cpu.pressure',
                'memory.pressure', 'io.pressure', 'memory.current', 'memory.peak')
            and isinstance(constants.get('SOURCE_PINS'), dict) and len(constants['SOURCE_PINS']) == 6,
            'sample_validator_fixed_data_scope')
    namespace = {'json': json, 'hashlib': hashlib, 're': re, 'math': math, **constants,
                 'MAX_TELEMETRY': SAMPLE_MAX_TELEMETRY, 'MAX_EVIDENCE': SAMPLE_MAX_NATIVE}
    selected = ast.Module(body=[nodes[name] for name in names], type_ignores=[])
    # Verified source bytes supply definitions only: no imports, module body,
    # PROGRAM builder, native entry, resource snapshots or filesystem calls.
    definitions = ast.unparse(selected).encode('utf-8')
    namespace = _import_verified_buffer(sample_source, definitions,
        'verified_sample_projection_definitions', namespace).__dict__
    return namespace, frozenset(codes), {'caller_source_sha256': digest(caller_raw),
        'sample_source_sha256': digest(sample_raw), 'caller_fixed_literal_catalog_sha256': digest(canonical(sorted(codes))),
        'checked_source_buffers_only': True, 'native_or_target_execution_by_exporter': False,
        'checked_caller_declared_route': route}


def sample_error_projection(value, codes):
    result = parent_error_projection(value)
    if (isinstance(value, dict) and set(value) == {'type', 'message'}
            and value.get('type') == 'CallerRejected' and type(value.get('message')) is str
            and value['message'] in codes):
        result.update(classification='EXACT_TYPED_FIXED_VALIDATION_LITERAL_MATCH',
                      validation_code=value['message'])
    return result


def sample_request_projection(envelope, diagnostic, validators):
    request, binding = validators['check_envelope'](envelope)
    require(binding['full_request_sha256'] == SAMPLE_FULL_REQUEST
            and binding['header_source_targets_sha256'] == SAMPLE_TARGET_POPULATION
            and binding['header_generated_files_sha256'] == SAMPLE_GENERATED_POPULATION,
            'sample_frozen_request_or_population_digest_mismatch')
    required = request['required_contexts']
    require(all(type(value) is str and HASH.fullmatch(value) for value in required)
            and len(set(required)) == 577, 'sample_required_context_id_population')
    private = diagnostic.get('request_binding')
    require(isinstance(private, dict) and private.get('full_request_bound_before_selection') is True
            and private.get('no_primary_native_execution') is True
            and private.get('full_required_fallback_contexts') == 576
            and private.get('selected_context_indices') == private.get('selected_original_indices') == SAMPLE_INDEXES
            and private.get('full_header_source_population') == 3031
            and private.get('full_header_generated_population') == 143
            and private.get('full_fallback_request_sha256') == binding['full_request_sha256']
            and private.get('sample_request_sha256') == binding['sample_request_sha256']
            and diagnostic.get('sample_binding') == binding,
            'sample_diagnostic_request_binding_mismatch')
    rows = []
    for context, selected in zip(request['contexts'], binding['selected']):
        require(type(selected.get('index')) is int and context['context_id'] in required and type(context['context_id']) is str
                and HASH.fullmatch(context['context_id']) and context['context_id'] == selected['context_id'],
                'sample_selected_context_identity')
        source = context.get('analysis_file')
        origin = 'original' if type(source) is str and source.startswith('/work/source/') else 'generated'
        prefix = '/work/source/' if origin == 'original' else '/work/analysis/generated-baseline/'
        require(type(source) is str and source.startswith(prefix), 'sample_selected_analysis_root')
        path = safe_relative(source[len(prefix):])
        member = request['header_source_targets'].get(path) if origin == 'original' else request['header_generated_files'].get(path)
        source_sha = member if origin == 'original' else member.get('sha256') if isinstance(member, dict) else None
        rows.append({'index': selected['index'], 'context_id': selected['context_id'],
            'origin': origin, 'path': path, 'source_sha256': checked_hash(source_sha),
            'invocation_sha256': checked_hash(selected['invocation_sha256']),
            'dropped_arguments_sha256': digest(canonical(context['dropped_arguments'])),
            'source_dependencies_sha256': checked_hash(selected['source_dependencies_sha256']),
            'generated_dependencies_sha256': checked_hash(selected['generated_dependencies_sha256'])})
    require(private.get('selected_context_ids') == [r['context_id'] for r in rows], 'sample_selected_ids_mismatch')
    return request, binding, {'full_fallback_request_sha256': binding['full_request_sha256'],
        'sample_request_sha256': binding['sample_request_sha256'],
        'required_contexts_sha256': binding['required_contexts_sha256'],
        'full_fallback_context_ids_sha256': binding['full_fallback_context_ids_sha256'],
        'header_source_targets_sha256': binding['header_source_targets_sha256'],
        'header_generated_files_sha256': binding['header_generated_files_sha256'],
        'sample_contexts_sha256': binding['sample_contexts_sha256'], 'selected': rows,
        'obligations': dict(binding['obligations']), 'full_request_source_bound_before_selection': True,
        'sample_envelope_independently_checked': True, 'full576_request_bytes_exported': False,
        'unsampled_status': 'UNMEASURED', 'cache_state': 'UNKNOWN'}


def sample_native_projection(raw, request, allocated):
    """Bind every returned selected record; preserve coded genuine native failure."""
    try:
        data = strict_json(raw)
    except (ValueError, UnicodeError, TypeError, RecursionError) as error:
        return {'parse_status': 'UNPARSEABLE_PRIVATE_STDOUT_UNPROVEN', 'raw_sha256': digest(raw),
                'error_type': type(error).__name__, 'raw_exportable': False, 'analysis_or_population_credit': False}
    if isinstance(data, dict) and data.get('schema') == 'nico.cpp-clang-fallback-failure.v1':
        safe = set(data) == {'schema', 'error'} and type(data.get('error')) is str and re.fullmatch(r'worker_clang_fallback_[a-z_]+', data['error'])
        return {'parse_status': 'CODED_NATIVE_FAILURE_UNPROVEN' if safe else 'OPAQUE_NATIVE_FAILURE_UNPROVEN',
                'raw_sha256': digest(raw), 'raw_exportable': bool(safe),
                'failure': error_projection(data['error']) if safe else {'opaque_failure_sha256': digest(canonical(data))},
                'analysis_or_population_credit': False}
    projection = retained_raw_projection('project-static-clang-fallback', raw, FIXED_IMAGE)
    projection['raw_exportable'] = projection['parse_status'] == 'KEY_SCHEMA_AND_DATA_PROJECTION_VALID'
    if not projection['raw_exportable']:
        projection['analysis_or_population_credit'] = False
        return projection
    require(set(data) == {'schema', 'request_sha256', 'analyst_uid', 'version', 'records', 'duration_ms',
        'wall_budget_ms', 'header_tool_receipt', 'header_tool_receipt_sha256'}
        and type(data.get('analyst_uid')) is int and data['analyst_uid'] == 1001,
        'sample_native_closed_top_level_fields')
    receipt = base64.b64decode(data['header_tool_receipt'], validate=True)
    require(len(receipt) <= 65536 and digest(receipt) == data['header_tool_receipt_sha256'],
            'sample_native_header_tool_bytes')
    tool = strict_json(receipt)
    require(isinstance(tool, dict) and set(tool) == {'schema', 'manifest_sha256', 'source_sha256',
        'sdk_lock_sha256', 'runtime_lock_sha256', 'clang_version', 'plugin_sha256', 'compiler_version',
        'qualification_completed'} and tool.get('schema') == 'nico.clang-header-tool.v1'
        and tool.get('qualification_completed') is False, 'sample_native_header_tool_closed_scope')
    sample_execution_bytes(data['version'])
    require(data.get('request_sha256') == digest(canonical(request))
            and type(data.get('wall_budget_ms')) is int and data['wall_budget_ms'] == allocated
            and len(data['records']) == 4, 'sample_native_request_allocation_or_population')
    for expected_row, actual, projected in zip(request['contexts'], data['records'], projection['contexts']):
        require(set(actual) == {'context_id', 'invocation', 'dropped_arguments', 'execution', 'plist',
            'plist_sha256', 'error', 'header_trace', 'header_trace_sha256'}
                and actual.get('context_id') == expected_row['context_id']
                and actual.get('invocation') == expected_row['invocation']
                and actual.get('dropped_arguments') == expected_row['dropped_arguments'],
                'sample_native_selected_record_binding')
        projected['record_position'] = projected.pop('index')
        projected['original_context_index'] = expected_row['index']
        error = actual.get('error')
        require(error is None or type(error) is str and re.fullmatch(r'worker_clang_fallback_[a-z_]+', error),
                'sample_native_error_code_scope')
        if actual['execution'] is not None:
            sample_execution_bytes(actual['execution'])
        for key, maximum in (('plist', 4 * 1024 * 1024), ('header_trace', 1024 * 1024)):
            sample_compressed_bytes(actual[key], actual[key + '_sha256'], maximum)
        if actual['execution'] is None:
            require(error is not None and not actual['plist'] and not actual['header_trace'],
                    'sample_native_unstarted_payload')
    projection['complete_four_record_population_bound'] = True
    projection['whole576_analysis_or_population_credit'] = False
    return projection


def sample_execution_bytes(value):
    require(isinstance(value, dict) and set(value) == {'exit_code', 'timed_out', 'output_truncated',
        'duration_ms', 'output', 'output_sha256'}, 'sample_native_execution_fields')
    execution_projection(value)
    raw = base64.b64decode(value['output'], validate=True)
    require(len(raw) <= 65536 and digest(raw) == value['output_sha256'], 'sample_native_execution_output_bytes')
    return raw


def sample_compressed_bytes(value, expected_hash, maximum):
    require(type(value) is str, 'sample_native_binary_encoding')
    stored = base64.b64decode(value, validate=True)
    require(len(stored) <= 4 * 1024 * 1024, 'sample_native_binary_stored_bound')
    if not stored:
        require(expected_hash is None, 'sample_native_binary_empty_digest')
        return b''
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(stored, maximum + 1)
    except zlib.error as error:
        raise Rejected('sample_native_binary_zlib_invalid') from error
    require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail
            and len(raw) <= maximum and digest(raw) == expected_hash, 'sample_native_binary_bytes')
    return raw


def sample_retained_telemetry(raw, envelope, native_raw, allocated, validators):
    """Closed structural/identity/counter retention; never relax host validation."""
    request, binding = validators['check_envelope'](envelope)
    require(0 < len(raw) <= SAMPLE_MAX_TELEMETRY, 'sample_retained_telemetry_bound')
    value = strict_json(raw)
    keys = {'schema', 'status', 'collector_error_type', 'selection', 'limits', 'collector_call_wall_ms',
        'actual_wall_budget_ms', 'collector_wall_scope', 'children', 'cgroup', 'evidence_sha256',
        'full_native_qualified', 'production_qualified', 'historical_replay_credit', 'cache_state', 'unsampled_status'}
    require(isinstance(value, dict) and set(value) == keys
            and value.get('schema') == 'nico.diagnostic.four-fallback-resources.v1'
            and value.get('selection') == binding and value.get('limits') == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
            and type(value.get('actual_wall_budget_ms')) is int and value['actual_wall_budget_ms'] == allocated
            and type(allocated) is int and 0 < allocated <= 480000
            and validators['finite_nonnegative'](value.get('collector_call_wall_ms'))
            and value.get('collector_wall_scope') == 'UNCHANGED_COLLECTOR_INCLUDING_HEADER_INPUT_CHECKS_VERSION_AND_SELECTED_ANALYZERS'
            and all(value.get(key) is False for key in ('full_native_qualified', 'production_qualified', 'historical_replay_credit'))
            and value.get('cache_state') == 'UNKNOWN' and value.get('unsampled_status') == 'UNMEASURED',
            'sample_retained_telemetry_identity_scope')
    status = value['status']
    require(status == 'COLLECTOR_RETURNED' and value['collector_error_type'] is None
            or status == 'UNPROVEN' and value['collector_error_type'] in {'ValueError', 'OSError', 'KeyError',
                'TypeError', 'KeyboardInterrupt', 'SystemExit', 'OtherException'}, 'sample_retained_telemetry_fixed_error_type')
    if value['evidence_sha256'] is None:
        require(status == 'UNPROVEN', 'sample_retained_telemetry_missing_evidence_identity')
    else:
        require(value['evidence_sha256'] == digest(canonical(strict_json(native_raw))),
                'sample_retained_telemetry_native_identity')
    children = value['children']
    require(isinstance(children, dict) and set(children) == {'scope', 'includes_version_probe', 'per_context_cpu_available',
        'before', 'after', 'delta_status', 'delta'}
        and children.get('scope') == 'ALL_REAPED_CHILDREN_OF_THIS_MEASUREMENT_WORKER'
        and children.get('includes_version_probe') is True and children.get('per_context_cpu_available') is False,
        'sample_retained_children_scope')
    for snapshot in (children['before'], children['after']):
        require(isinstance(snapshot, dict) and set(snapshot) == {'status', 'user_seconds', 'system_seconds', 'scope', 'observation_ms'}
                and snapshot.get('scope') == children['scope'] and validators['finite_nonnegative'](snapshot['observation_ms'])
                and (snapshot['status'] == 'OBSERVED' and validators['finite_nonnegative'](snapshot['user_seconds'])
                    and validators['finite_nonnegative'](snapshot['system_seconds'])
                    or snapshot['status'] == 'UNKNOWN' and snapshot['user_seconds'] is snapshot['system_seconds'] is None),
                'sample_retained_children_snapshot')
    expected = None
    if children['before']['status'] == children['after']['status'] == 'OBSERVED':
        user = children['after']['user_seconds'] - children['before']['user_seconds']
        system = children['after']['system_seconds'] - children['before']['system_seconds']
        if validators['finite_nonnegative'](user) and validators['finite_nonnegative'](system):
            expected = {'user_seconds': user, 'system_seconds': system, 'total_seconds': user + system}
    require(children['delta'] == expected and children['delta_status'] == ('OBSERVED' if expected is not None else 'UNKNOWN'),
            'sample_retained_children_delta')
    group = value['cgroup']
    require(isinstance(group, dict) and set(group) == {'before', 'after', 'delta'}, 'sample_retained_cgroup_scope')
    for snapshot in (group['before'], group['after']):
        require(isinstance(snapshot, dict) and set(snapshot) == {'scope', 'files', 'observation_ms'}
                and snapshot.get('scope') == 'SAME_ANALYST_CONTAINER_CGROUP_INCLUDING_MEASUREMENT_PARENT'
                and validators['finite_nonnegative'](snapshot['observation_ms']) and isinstance(snapshot['files'], dict)
                and set(snapshot['files']) == set(validators['CGROUP_FILES']), 'sample_retained_cgroup_snapshot')
        for name, row in snapshot['files'].items():
            require(isinstance(row, dict) and set(row) == {'status', 'values'}
                    and row['status'] in {'OBSERVED', 'UNKNOWN'}, 'sample_retained_cgroup_status')
            data = row['values']
            if row['status'] == 'UNKNOWN':
                require(data is None, 'sample_retained_unknown_counter')
                continue
            require(isinstance(data, dict), 'sample_retained_counter_map')
            if name.endswith('.pressure'):
                require('some' in data and set(data) <= {'some', 'full'}, 'sample_retained_pressure_scope')
                for numbers in data.values():
                    require(isinstance(numbers, dict) and set(numbers) == {'avg10', 'avg60', 'avg300', 'total'}
                            and type(numbers['total']) is int and 0 <= numbers['total'] < 10 ** 20
                            and all(validators['finite_nonnegative'](numbers[key]) and numbers[key] <= 100
                                for key in ('avg10', 'avg60', 'avg300')), 'sample_retained_pressure_values')
            else:
                reconstructed = str(data.get('bytes', '')) + '\n' if name in {'memory.current', 'memory.peak'} else ''.join(
                    str(key) + ' ' + str(number) + '\n' for key, number in data.items())
                require(validators['parse_cgroup'](name, reconstructed.encode()) == data
                        and all(type(number) is int for number in data.values()), 'sample_retained_counter_values')
    require(group['delta'] == validators['counter_deltas'](group['before'], group['after']), 'sample_retained_cgroup_delta')
    return value


def write_sample_export(public, files, output, paths, caller_hash):
    summary_raw = canonical(public)
    require(len(summary_raw) <= MAX_RECEIPT_BYTES and not any(marker in summary_raw for marker in PRIVATE_MARKERS),
            'sample_summary_bound_or_private_material')
    files = {**files, 'sample-summary.json': summary_raw}
    total = sum(map(len, files.values()))
    require(total <= SAMPLE_MAX_TOTAL, 'sample_total_export_bound')
    output = Path(output).absolute()
    require(not output.exists() and output.parent == output.parent.resolve(strict=True)
            and all(not output.is_relative_to(path) and not path.is_relative_to(output) for path in paths),
            'sample_export_new_nonalias_output')
    manifest = {'schema': 'nico.fallback_capacity_sample_export_manifest.v1',
        'files': [{'path': key, 'bytes': len(raw), 'sha256': digest(raw)} for key, raw in sorted(files.items())],
        'file_count': len(files), 'listed_bytes': total, 'caller_receipt_sha256': caller_hash,
        'fresh_only': True, 'private_sample_envelope_exported': False,
        'reused_input_or_opaque_receipt_bytes_exported': False, 'full_native_or_production_qualification': False}
    manifest_raw = canonical(manifest)
    require(total + len(manifest_raw) <= SAMPLE_MAX_TOTAL, 'sample_total_export_bound')
    output.mkdir(mode=0o700)
    for name, raw in {**files, 'manifest.json': manifest_raw}.items():
        path = output / safe_relative(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(raw)
    for name, raw in {**files, 'manifest.json': manifest_raw}.items():
        require(regular(output / name, max(SAMPLE_MAX_NATIVE, MAX_RECEIPT_BYTES)) == raw,
                'sample_export_all_byte_readback')
    return {'schema': 'nico.fallback_capacity_sample_export_receipt.v1', 'manifest_sha256': digest(manifest_raw),
        'public_summary_sha256': digest(summary_raw), 'file_count_with_manifest': len(files) + 1,
        'total_bytes_with_manifest': total + len(manifest_raw), 'closed_allowlist_all_bytes_readback_verified': True,
        'full_native_or_production_qualification': False}


def export_missing_sample(receipt_path, output, expected, *, caller_source, sample_source):
    """Observed absent receipt; execution/cause remain unknown, never fabricated."""
    require(expected.get('caller_receipt_sha256') is None, 'sample_missing_receipt_with_supplied_sha')
    path = Path(receipt_path).absolute()
    require(path == path.resolve() and not path.exists() and not path.is_symlink(),
            'sample_missing_receipt_path_present_or_noncanonical')
    require(digest(regular(Path(__file__).absolute(), MAX_RECEIPT_BYTES)) == expected['exporter_sha256'],
            'sample_exporter_actual_source_hash')
    validators, codes, source_checks = sample_source_validation(caller_source, sample_source, expected)
    require(COMMIT.fullmatch(expected['current_git_head']) and
            expected['effective_fallback_baseline'] == 'f0919654edd719059ea03319981b13f46ba70a88'
            and expected['compiler_overlay_path'] == 'nico/assessment_cpp_project_compiler.py'
            and expected['compiler_overlay_sha256'] == SAMPLE_COMPILER
            and expected['image_config_digest'] == FIXED_IMAGE
            and HASH.fullmatch(expected['scope_sha256']), 'sample_missing_expected_operation_binding')
    public = {'schema': 'nico.fallback_capacity_sample_export_summary.v1',
        'caller_receipt_sha256': None, 'caller_receipt_observed_absent': True,
        'checked_sources': source_checks,
        'expected_operation_binding': {key: expected[key] for key in ('current_git_head',
            'effective_fallback_baseline', 'compiler_overlay_path', 'compiler_overlay_sha256',
            'exporter_sha256', 'caller_sha256', 'scope_sha256', 'sample_sha256', 'image_config_digest')},
        'expected_operation_binding_is_runtime_observation': False,
        'source_binding': None, 'image_binding': None, 'target_binding': None,
        'source_image_target_execution_observation_status': 'UNKNOWN',
        'sample_observation': None, 'actual_operations': [], 'request_selection': None,
        'native_projection': None, 'telemetry_projection': None,
        'diagnostic_outcome': 'CALLER_RECEIPT_ABSENT_UNPROVEN',
        'missing_receipt_cause': None, 'actual_cause_requires_terminal_job_log': True,
        'cache_state': 'UNKNOWN', 'unsampled_status': 'UNMEASURED',
        'assessment_completed': False, 'full_native_qualified': False, 'production_qualified': False,
        'static_collection_complete': False, 'human_approval_created': False, 'cold_timing_credit': False,
        'private_sample_envelope_exported': False, 'reused_input_or_opaque_receipt_bytes_exported': False,
        'maximum_native_bytes': SAMPLE_MAX_NATIVE, 'maximum_telemetry_bytes': SAMPLE_MAX_TELEMETRY,
        'maximum_total_exported_bytes': SAMPLE_MAX_TOTAL}
    return write_sample_export(public, {}, output, [path.parent], None)


def sample_program_projection(program, validators, expected):
    require(isinstance(program, dict) and program.get('original_function_buffers_verified') is True
            and program.get('producer_source_pins') == validators['SOURCE_PINS']
            and program.get('sample_module_sha256') == expected['sample_sha256']
            and HASH.fullmatch(expected['sample_sha256'])
            and program.get('new_terminal_only') is True and program.get('full_native_qualified') is False,
            'sample_program_fixed_source_bindings')
    projected = {key: checked_hash(program.get(key)) for key in
        ('original_program_sha256', 'sample_program_sha256', 'original_prefix_sha256')}
    projected.update(original_function_buffers_verified=True,
        producer_source_pins=dict(validators['SOURCE_PINS']), sample_module_sha256=expected['sample_sha256'])
    return projected


def export_sample(receipt_path, output, expected, *, caller_source, sample_source):
    raw = regular(receipt_path, MAX_RECEIPT_BYTES,
        {'bytes': Path(receipt_path).stat().st_size, 'sha256': expected['caller_receipt_sha256']})
    outer = strict_json(raw)
    require(isinstance(outer, dict) and outer.get('schema') == 'nico.private.fallback_capacity_sample_caller.v1',
            'sample_caller_schema')
    require(digest(regular(Path(__file__).absolute(), MAX_RECEIPT_BYTES)) == expected['exporter_sha256'],
            'sample_exporter_actual_source_hash')
    validators, codes, source_checks = sample_source_validation(caller_source, sample_source, expected)
    require(all(outer.get(key) is False for key in SAMPLE_FALSE_PARENT), 'sample_parent_acceptance_flags')
    public = {'schema': 'nico.fallback_capacity_sample_export_summary.v1', 'caller_receipt_sha256': digest(raw),
        'checked_sources': source_checks, 'parent_error': sample_error_projection(outer.get('error'), codes),
        'sample_capture_status': scalar(outer.get('status'), 'id'), 'source_binding': None, 'image_binding': None,
        'target_binding': None, 'sample_observation': None, 'actual_operations': [], 'request_selection': None,
        'native_projection': None, 'telemetry_projection': None, 'cache_state': 'UNKNOWN',
        'unsampled_status': 'UNMEASURED', 'full_required_fallback_contexts': 576, 'sampled_contexts': 4,
        'assessment_completed': False, 'full_native_qualified': False, 'production_qualified': False,
        'static_collection_complete': False, 'human_approval_created': False, 'cold_timing_credit': False,
        'private_sample_envelope_exported': False, 'reused_input_or_opaque_receipt_bytes_exported': False,
        'maximum_native_bytes': SAMPLE_MAX_NATIVE, 'maximum_telemetry_bytes': SAMPLE_MAX_TELEMETRY,
        'maximum_total_exported_bytes': SAMPLE_MAX_TOTAL}
    files = {}
    parent = Path(receipt_path).absolute().parent
    paths = [parent]
    source = outer.get('source_binding')
    image = outer.get('image_binding')
    if not isinstance(source, dict) or not isinstance(image, dict):
        require(outer.get('status') == 'UNPROVEN' and outer.get('sample') is None,
                'sample_unbound_preflight_scope')
        public['diagnostic_outcome'] = 'SOURCE_OR_IMAGE_PREFLIGHT_ABSENT_UNPROVEN'
        return write_sample_export(public, files, output, paths, digest(raw))
    for key in ('current_git_head', 'effective_fallback_baseline'):
        require(source.get(key) == expected[key] and COMMIT.fullmatch(source[key]), 'sample_source_commit_binding')
    require(source['effective_fallback_baseline'] == 'f0919654edd719059ea03319981b13f46ba70a88'
            and source.get('effective_recipe_tree') == 'b9e200f62b9b2db9c6488326826ad8ae393418d0'
            and source.get('all_selected_files_actual_git_blob_bound') is True
            and source.get('effective_overlay_is_whole_candidate') is False, 'sample_effective_source_scope')
    for key in ('caller_sha256', 'scope_sha256', 'exporter_sha256', 'sample_sha256'):
        require(source.get(key) == expected[key] and HASH.fullmatch(source[key]), 'sample_source_hash_binding')
    overlay = source.get('compiler_overlay')
    require(overlay == {'path': 'nico/assessment_cpp_project_compiler.py', 'sha256': SAMPLE_COMPILER}
            and expected['compiler_overlay_path'] == overlay['path']
            and expected['compiler_overlay_sha256'] == overlay['sha256'], 'sample_compiler_overlay')
    require(expected['image_config_digest'] == FIXED_IMAGE
            and image.get('selected_config_digest') == image.get('fixed_config_digest') == FIXED_IMAGE
            and all(image.get(key) is True for key in ('loaded_image_inspection_verified', 'complete_archive_verified',
                'config_and_ordered_rootfs_equal_independent_build_receipt', 'single_verified_selected_image_for_sample'))
            and image.get('historical_image_recovered') is False
            and image.get('matching_historical_live_toolchain_or_header_inputs_inferred') is False,
            'sample_fixed_complete_image_binding')
    require(outer.get('selected_context_indices') == SAMPLE_INDEXES and outer.get('full_required_fallback_contexts') == 576
            and outer.get('single_sample_only') is True and outer.get('cache_state') == 'UNKNOWN'
            and outer.get('job_outer_budget_minutes') == 155 and outer.get('declared_api_wall_seconds') == 1030
            and outer.get('shared_execution_seconds') == 1020
            and outer.get('independent1030_hardwall_supervisor_present') is False
            and outer.get('parent_cpu_is_analyzer_cpu') is False and outer.get('overlapping_intervals_additive') is False,
            'sample_parent_budget_order_scope')
    public.update(source_binding={key: source[key] for key in ('current_git_head', 'effective_fallback_baseline',
        'effective_recipe_tree', 'caller_sha256', 'scope_sha256', 'exporter_sha256', 'sample_sha256')},
        compiler_overlay=dict(overlay), image_binding={'selected_config_digest': FIXED_IMAGE,
            'complete_archive_verification_recorded': True, 'loaded_config_and_ordered_rootfs_verification_recorded': True,
            'config_and_rootfs_sha256': checked_hash(image.get('config_and_rootfs_sha256')),
            'config_and_rootfs_verified_after_sample': image.get('config_and_rootfs_verified_after_sample') is True,
            'historical_image_recovered': False}, target_binding=target_projection(outer.get('target_binding'), outer=True),
        parent_intervals=process_intervals(outer.get('intervals')), parent_dependency_checks={key: dependency_projection(outer.get(key))
            for key in ('dependency_before_setup', 'dependency_before_process', 'dependency_after_sample')},
        declared_limits=dict(SAMPLE_LIMITS), independent1030_hardwall_supervisor_present=False,
        job_outer_budget_minutes=155, parent_cpu_is_analyzer_cpu=False, overlapping_intervals_additive=False)
    row = outer.get('sample')
    if row is None:
        require(outer.get('status') == 'UNPROVEN', 'sample_absent_process_status')
        public['diagnostic_outcome'] = 'SAMPLE_NOT_RUN_UNPROVEN'
        return write_sample_export(public, files, output, paths, digest(raw))
    require(isinstance(row, dict) and row.get('id') == 'capacity-sample', 'sample_process_row')
    directory = Path(row.get('directory', ''))
    require(directory.is_absolute() and directory == directory.resolve(strict=True)
            and directory == parent / 'context/runs/capacity-sample', 'sample_directory_exact_host_route')
    require(public['target_binding'] is not None, 'sample_process_without_frozen_target')
    paths.append(directory)
    entries = {path.name for path in directory.iterdir()}
    require(entries <= {'sample-diagnostic-result.json', 'process-receipt.json', 'sample-envelope.json', 'artifacts'},
            'sample_directory_closed_members')
    public['sample_observation'] = {'process_exit_code': scalar(row.get('process_exit_code'), 'exit'),
        'fresh_cp311_isolated_process_requested': row.get('fresh_cp311_isolated_process_requested') is True,
        'diagnostic_present': row.get('diagnostic_result') is not None, 'process_receipt_present': row.get('process_receipt') is not None}
    require(row.get('fresh_cp311_isolated_process_requested') is True, 'sample_process_fresh_isolated_request')
    for name in ('stdout', 'stderr'):
        reference = row.get(name)
        if reference is not None:
            log = regular(parent / ('context/capacity-sample-' + name + '.log'), MAX_RECEIPT_BYTES, reference)
            public['sample_observation'][name] = {'bytes': len(log), 'sha256': digest(log), 'raw_exported': False}
    process_ref = row.get('process_receipt')
    require(('process-receipt.json' in entries) is (process_ref is not None), 'sample_process_receipt_presence')
    if process_ref is not None:
        process_raw = regular(directory / 'process-receipt.json', MAX_RECEIPT_BYTES, process_ref)
        process = strict_json(process_raw)
        require(isinstance(process, dict) and process.get('schema') == 'nico.private.fallback_capacity_sample_process_receipt.v1'
                and process.get('variant') == 'candidate' and process.get('mock_injection_used') is False
                and all(process.get(k) is False for k in ('primary_native_execution', 'compiled', 'tests_executed',
                    'full_native_qualified', 'production_qualified', 'assessment_completed')), 'sample_process_scope')
        python = process.get('actual_python')
        require(isinstance(python, dict) and python.get('isolated') is True and python.get('no_bytecode') is True
                and type(python.get('version')) is str and python['version'].startswith('3.11.'),
                'sample_process_actual_python_scope')
        rows = process.get('source_rows')
        if rows is not None:
            require(isinstance(rows, dict), 'sample_process_sources')
            for key, path in SAMPLE_SOURCE_PATHS.items():
                require(isinstance(rows.get(key), dict) and rows[key].get('path') == path
                        and rows[key].get('sha256') == expected[key + '_sha256']
                        and COMMIT.fullmatch(rows[key].get('git_blob', '')), 'sample_process_actual_source_binding')
        public['sample_observation'].update(process_receipt_sha256=digest(process_raw),
            process_error=sample_error_projection(process.get('error'), codes),
            sample_invocation_attempted=scalar(process.get('sample_invocation_attempted'), 'bool'),
            process_intervals=process_intervals(process.get('intervals')),
            target_before=target_projection(process.get('target_verification')),
            target_after=target_projection(process.get('target_verification_after_sample')),
            dependency_checks={key: dependency_projection(process.get(key)) for key in
                ('dependency_before_preparation', 'dependency_before_sample', 'dependency_after_sample')})
    diagnostic_ref = row.get('diagnostic_result')
    require(('sample-diagnostic-result.json' in entries) is (diagnostic_ref is not None), 'sample_diagnostic_presence')
    if diagnostic_ref is None:
        require(not (directory / 'artifacts').exists(), 'sample_artifacts_without_diagnostic')
        public['diagnostic_outcome'] = 'SAMPLE_DIAGNOSTIC_ABSENT_UNPROVEN'
        return write_sample_export(public, files, output, paths, digest(raw))
    diagnostic_raw = regular(directory / 'sample-diagnostic-result.json', MAX_RECEIPT_BYTES, diagnostic_ref)
    diagnostic = strict_json(diagnostic_raw)
    require(isinstance(diagnostic, dict) and diagnostic.get('schema') == 'nico.private.fallback_capacity_sample_diagnostic.v1'
            and all(diagnostic.get(key) is False for key in SAMPLE_FALSE_DIAGNOSTIC)
            and diagnostic.get('limits') == SAMPLE_LIMITS and diagnostic.get('declared_api_wall_seconds') == 1030
            and diagnostic.get('resource_profile') == 'cpp-baseline-qualification-v1', 'sample_diagnostic_scope_and_limits')
    public.update(sample_diagnostic_sha256=digest(diagnostic_raw), phase=scalar(diagnostic.get('phase'), 'id'),
        sample_diagnostic_status=scalar(diagnostic.get('status'), 'id'),
        sample_error=sample_error_projection(diagnostic.get('error'), codes),
        sample_duration_ms=scalar(diagnostic.get('duration_ms'), 'number'),
        sample_intervals=process_intervals(diagnostic.get('intervals')),
        boundary_and_cleanup={key: scalar(diagnostic.get(key), 'bool') for key in
            ('boundary_verified', 'scratch_capacity_verified', 'cleanup_verified')})
    for key in ('memory_peak_bytes', 'scratch_capacity_bytes'):
        if diagnostic.get(key) is not None:
            value = scalar(diagnostic[key], 'number')
            require(type(value) is int and 0 <= value <= SAMPLE_LIMITS['memory_bytes'] if key == 'memory_peak_bytes'
                    else type(value) is int and value == SAMPLE_LIMITS['tmpfs_bytes'], 'sample_resource_observation_bound')
            public['boundary_and_cleanup'][key] = value
        else:
            public['boundary_and_cleanup'][key] = None
    envelope = None
    request = None
    envelope_ref = diagnostic.get('sample_envelope')
    require(('sample-envelope.json' in entries) is (envelope_ref is not None), 'sample_private_envelope_presence')
    if envelope_ref is not None:
        require(isinstance(envelope_ref, dict) and set(envelope_ref) == {'path', 'bytes', 'sha256'}
                and envelope_ref['path'] == 'sample-envelope.json', 'sample_private_envelope_reference')
        envelope_raw = regular(directory / 'sample-envelope.json', MAX_RECEIPT_BYTES,
            {key: envelope_ref[key] for key in ('bytes', 'sha256')})
        envelope = strict_json(envelope_raw)
        request, binding, public['request_selection'] = sample_request_projection(envelope, diagnostic, validators)
        public['private_envelope_verified_bytes'] = len(envelope_raw)
        public['private_envelope_verified_sha256'] = digest(envelope_raw)
        program = diagnostic.get('program_binding')
        if program is not None:
            public['program_binding'] = sample_program_projection(program, validators, expected)
    operations = diagnostic.get('operations')
    require(isinstance(operations, list) and len(operations) <= len(SAMPLE_OPERATION_IDS), 'sample_operations_population')
    artifacts = {}
    native_raw = None
    telemetry_raw = None
    fresh_image = False
    ids = set()
    for operation in operations:
        require(isinstance(operation, dict) and operation.get('id') in SAMPLE_OPERATION_IDS
                and operation['id'] not in ids, 'sample_operation_id_or_duplicate')
        key = operation['id']
        ids.add(key)
        projected = {'id': key, **execution_projection(operation),
            'invocation_sha256': checked_hash(operation.get('invocation_sha256')),
            'output_sha256': checked_hash(operation.get('output_sha256')),
            'output_bytes': scalar(operation.get('output_bytes'), 'number')}
        reference = operation.get('output_artifact')
        if key not in SAMPLE_ARTIFACTS:
            require(reference is None, 'sample_nonartifact_reference')
            encoded = operation.get('output')
            require(type(encoded) is str, 'sample_boundary_output_encoding')
            body = base64.b64decode(encoded, validate=True)
            require(len(body) == operation['output_bytes'] and digest(body) == operation['output_sha256'],
                    'sample_boundary_output_bytes')
            if key == 'static-image' and operation['exit_code'] == 0 and not operation['timed_out'] and not operation['output_truncated']:
                observed = strict_json(body)
                require(isinstance(observed, list) and len(observed) == 1 and observed[0].get('Id') == FIXED_IMAGE,
                        'sample_fresh_image_inspection')
                fresh_image = True
        elif reference is None:
            projected.update(artifact_not_retained=True, raw_exported=False)
        else:
            require(isinstance(reference, dict) and set(reference) == {'path', 'bytes', 'sha256'}, 'sample_artifact_reference')
            name = safe_relative(reference['path'])
            require(name == 'artifacts/' + key + '-' + checked_hash(reference['sha256']) + '.json'
                    and name not in artifacts and reference['sha256'] == operation['output_sha256']
                    and type(operation['output_bytes']) is int and reference['bytes'] == operation['output_bytes'],
                    'sample_artifact_name_operation_binding')
            body = regular(directory / name, SAMPLE_ARTIFACTS[key], {k: reference[k] for k in ('bytes', 'sha256')})
            artifacts[name] = body
            projected['artifact'] = {'path': name, 'bytes': len(body), 'sha256': digest(body)}
            require(operation.get('output') is None, 'sample_external_output_inline_rejected')
            if key == 'fallback-capacity-sample':
                native_raw = body
            else:
                telemetry_raw = body
        public['actual_operations'].append(projected)
    artifact_directory = directory / 'artifacts'
    actual_artifacts = set()
    if artifact_directory.exists():
        require(artifact_directory.is_dir() and artifact_directory == artifact_directory.resolve(strict=True), 'sample_artifact_directory')
        for path in artifact_directory.iterdir():
            require(path.is_file() and not path.is_symlink(), 'sample_artifact_regular_only')
            actual_artifacts.add('artifacts/' + path.name)
    require(actual_artifacts == set(artifacts), 'sample_missing_or_unreferenced_artifact')
    require(not ids.intersection(SAMPLE_ARTIFACTS) or fresh_image and request is not None,
            'sample_native_without_fresh_image_or_envelope')
    allocated = diagnostic.get('fallback_allocation_ms')
    if ids.intersection(SAMPLE_ARTIFACTS):
        require(type(allocated) is int and 0 < allocated <= 480000, 'sample_allocated_budget')
    public['fresh_stage_image_inspection_verified'] = fresh_image
    public['actual_fallback_allocation_ms'] = allocated
    if native_raw is not None:
        public['native_projection'] = sample_native_projection(native_raw, request, allocated)
    telemetry_valid = False
    telemetry_closed_retention = False
    if telemetry_raw is not None and native_raw is not None:
        try:
            retained = sample_retained_telemetry(telemetry_raw, envelope, native_raw, allocated, validators)
            public['telemetry_projection'] = {key: retained[key] for key in ('schema', 'status', 'collector_error_type',
                'collector_call_wall_ms', 'actual_wall_budget_ms', 'collector_wall_scope', 'children', 'cgroup',
                'evidence_sha256', 'cache_state', 'unsampled_status')}
            public['telemetry_projection'].update(closed_identity_and_counter_retention_verified=True,
                positive_host_telemetry_validation=False, observation_scope='RETAINED_DIAGNOSTIC_DATA_NO_QUALIFICATION')
            telemetry_closed_retention = True
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError) as error:
            public['telemetry_projection'] = {'status': 'TELEMETRY_SCOPE_OR_DATA_UNPROVEN',
                'raw_sha256': digest(telemetry_raw), 'error_type': type(error).__name__,
                'actual_telemetry_validation_credit': False}
        try:
            proof = validators['validate_sample_telemetry'](telemetry_raw, envelope, native_raw, actual_wall_budget_ms=allocated)
            require(telemetry_closed_retention, 'sample_positive_telemetry_without_closed_retention')
            public['telemetry_projection']['positive_host_telemetry_validation'] = True
            telemetry_valid = True
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError) as error:
            public['telemetry_projection']['positive_host_telemetry_validation'] = False
            public['telemetry_projection']['positive_validation_failure_type'] = type(error).__name__
    for name, body in artifacts.items():
        native = name.startswith('artifacts/fallback-capacity-sample-')
        safe = not any(marker in body for marker in PRIVATE_MARKERS)
        safe &= bool(public['native_projection'].get('raw_exportable')) if native else telemetry_closed_retention
        for operation in public['actual_operations']:
            if operation.get('artifact', {}).get('path') == name:
                operation['raw_exported'] = safe
                operation['raw_retained_privately'] = True
        if safe:
            files[name] = body
    public['diagnostic_outcome'] = ('FOUR_CONTEXT_DATA_AND_TELEMETRY_CAPTURED_NO_FULL_CREDIT'
        if outer.get('status') == 'SAMPLE_PROCESS_AND_RETAINED_RESULT_CAPTURED' and outer.get('error') is None
            and row.get('process_exit_code') == 0 and public['sample_observation'].get('process_error') is None
            and diagnostic.get('status') == 'FOUR_CONTEXT_DIAGNOSTIC_CAPTURED' and diagnostic.get('error') is None
            and telemetry_valid and public['native_projection'] is not None
            and public['native_projection'].get('raw_exportable') is True
            and diagnostic['cleanup_verified'] is True and diagnostic['boundary_verified'] is True
            and diagnostic['scratch_capacity_verified'] is True
            and image.get('config_and_rootfs_verified_after_sample') is True
        else 'RETAINED_SAMPLE_FAILURE_OR_PARTIAL_DATA_UNPROVEN')
    return write_sample_export(public, files, output, paths, digest(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caller-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sample-mode', action='store_true')
    parser.add_argument('--missing-caller-receipt', action='store_true')
    parser.add_argument('--expected-caller-receipt-sha256')
    parser.add_argument('--caller-source', type=Path)
    parser.add_argument('--sample-source', type=Path)
    parser.add_argument('--expected-sample-sha256')
    for name in ('current-git-head', 'effective-fallback-baseline',
                 'compiler-overlay-path', 'compiler-overlay-sha256', 'exporter-sha256', 'caller-sha256', 'scope-sha256', 'image-config-digest'):
        parser.add_argument('--expected-' + name, required=True)
    args = parser.parse_args()
    expected = {name: getattr(args, 'expected_' + name) for name in
                ('caller_receipt_sha256', 'current_git_head', 'effective_fallback_baseline',
                 'compiler_overlay_path', 'compiler_overlay_sha256', 'exporter_sha256', 'caller_sha256', 'scope_sha256', 'image_config_digest')}
    try:
        if args.sample_mode:
            require(args.caller_source is not None and args.sample_source is not None
                    and args.expected_sample_sha256 is not None, 'sample_export_cli_source_bindings')
            expected['sample_sha256'] = checked_hash(args.expected_sample_sha256)
            if args.missing_caller_receipt:
                require(args.expected_caller_receipt_sha256 is None, 'sample_missing_receipt_with_supplied_sha')
                receipt = export_missing_sample(args.caller_receipt, args.output, expected,
                    caller_source=args.caller_source, sample_source=args.sample_source)
            else:
                require(args.expected_caller_receipt_sha256 is not None, 'sample_present_receipt_requires_actual_sha')
                receipt = export_sample(args.caller_receipt, args.output, expected,
                    caller_source=args.caller_source, sample_source=args.sample_source)
        else:
            require(not args.missing_caller_receipt and args.expected_caller_receipt_sha256 is not None
                    and args.caller_source is None and args.sample_source is None
                    and args.expected_sample_sha256 is None, 'sample_arguments_without_sample_mode')
            receipt = export_pair(args.caller_receipt, args.output, expected)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'EXPORT_VALIDATION_FAILED', 'failure_type': type(error).__name__,
                          'full_native_or_production_qualification': False}))
        raise SystemExit(2)
    print(json.dumps({'status': 'EXPORT_BYTES_READBACK_VERIFIED',
        **{key: receipt[key] for key in ('manifest_sha256', 'public_summary_sha256',
            'file_count_with_manifest', 'total_bytes_with_manifest', 'full_native_or_production_qualification')}}, indent=2))


if __name__ == '__main__':
    main()
