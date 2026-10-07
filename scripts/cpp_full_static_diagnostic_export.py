"""Closed-allowlist LOCAL export of a newly retained full-static diagnostic pair.

This helper never imports NICO, executes target code, invokes Docker, downloads
anything, or copies an opaque caller receipt. Root must review and execute it.
"""
from pathlib import Path, PurePosixPath
import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caller-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    for name in ('caller-receipt-sha256', 'current-git-head', 'effective-fallback-baseline',
                 'compiler-overlay-path', 'compiler-overlay-sha256', 'exporter-sha256', 'caller-sha256', 'scope-sha256', 'image-config-digest'):
        parser.add_argument('--expected-' + name, required=True)
    args = parser.parse_args()
    expected = {name: getattr(args, 'expected_' + name) for name in
                ('caller_receipt_sha256', 'current_git_head', 'effective_fallback_baseline',
                 'compiler_overlay_path', 'compiler_overlay_sha256', 'exporter_sha256', 'caller_sha256', 'scope_sha256', 'image_config_digest')}
    try:
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
