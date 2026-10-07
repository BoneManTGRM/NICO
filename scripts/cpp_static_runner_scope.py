"""Reviewed static-runner definitions in an explicitly new diagnostic context.

This module contains selected unchanged function/class buffers. It is not the
historical whole runner, and provides no preparation, CLI or qualification path.
"""
from __future__ import annotations
import argparse, base64, hashlib, importlib, importlib.abc, importlib.util
import json, linecache, os
from pathlib import Path, PurePosixPath
import re, shutil, stat, sys, time, types, uuid
HERE = Path(__file__).resolve().parent
MAX_FILE = 64 * 1024 * 1024
FLAGS = dict(extended_compiler_budget=True, compiler_environment=True,
             header_provenance=True, collect_completed_compiler_failures=True)
LIMITS = dict(stage_execution_seconds=1020, stage_wall_seconds=1030,
              primary_wall_seconds=540, primary_case_seconds=90, primary_parallel=4,
              fallback_wall_seconds=480, fallback_case_seconds=120, fallback_parallel=2,
              cpus='4', memory_bytes=12884901888, pids='256', tmpfs_bytes=9663676416)

class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def git_tree(rows):
    entries = {}
    for row in rows:
        parts = safe_path(row['path']).split('/')
        node = entries
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            require(isinstance(node, dict), 'target_tree_path_collision')
        require(parts[-1] not in node, 'target_tree_duplicate')
        require(row['git_mode'] in {'100644', '100755'} and
                re.fullmatch(r'[0-9a-f]{40}', row['git_blob']), 'target_git_entry_invalid')
        node[parts[-1]] = (row['git_mode'], row['git_blob'])
    def encode(node):
        data = bytearray()
        for name, value in sorted(node.items(), key=lambda item: (item[0] + ('/' if isinstance(item[1], dict) else '')).encode()):
            mode, digest = ('40000', encode(value)) if isinstance(value, dict) else value
            data.extend(mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(digest))
        return hashlib.sha1(b'tree ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    return encode(entries)


def safe_path(name):
    require(isinstance(name, str) and name and '\\' not in name and '\x00' not in name,
            'unsafe_relative_path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name and
            all(part not in ('', '.', '..', '.git') for part in name.split('/')), 'unsafe_relative_path')
    return name


def regular(path, maximum=MAX_FILE, digest=None, size=None):
    path = Path(path)
    require(path.absolute() == path.resolve(strict=True), 'symlink_or_noncanonical_path')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, 'file_type_or_size_invalid')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum and len(data) == info.st_size, 'file_changed_or_oversized')
    require(size is None or len(data) == size, 'file_size_mismatch')
    require(digest is None or sha(data) == digest, 'file_digest_mismatch')
    return data


def strict_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


class VerifiedLoader(importlib.machinery.SourceFileLoader):
    """Import pinned local source with cached bytecode explicitly unavailable."""
    def __init__(self, path, digest, fullname='verified_local_library'):
        super().__init__(fullname, str(path))
        self.digest = digest

    def get_data(self, path):
        if path != self.path:
            raise OSError('verified_source_bytecode_unavailable')
        raw = regular(Path(self.path), digest=self.digest)
        source = raw.decode('utf-8')
        linecache.cache[self.path] = (len(raw), None, source.splitlines(True), self.path)
        return raw

    def set_data(self, path, data, **kwargs):
        return None


class VerifiedFinder(importlib.abc.MetaPathFinder):
    def __init__(self, sources):
        self.sources = sources
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith('nico.'):
            return None
        relative = fullname.replace('.', '/')
        package = relative + '/__init__.py'
        module = relative + '.py'
        name = package if package in self.sources else module
        require(name in self.sources, 'unbound_library_module:' + fullname)
        filename, digest = self.sources[name]
        loader = VerifiedLoader(filename, digest, fullname)
        return importlib.util.spec_from_loader(fullname, loader, is_package=name == package)


def verify_target_source(path, targets, inventory, expected_tree):
    from nico.assessment_cpp_full_project_execution import _inputs
    from nico.assessment_cpp_full_project import MAX_SOURCE_BYTES
    files = _inputs({'targets': targets, 'configuration': {'source_byte_limit': MAX_SOURCE_BYTES}}, path, lambda: None)
    require(len(inventory) == len(targets) and {row['path']: row['sha256'] for row in inventory} == targets
            and git_tree(inventory) == expected_tree, 'target_inventory_binding_invalid')
    actual = []
    for row in inventory:
        value = files[row['path']]
        require(value['executable'] is (row['git_mode'] == '100755'), 'target_executable_mode_mismatch')
        owner_executable = bool((Path(path) / safe_path(row['path'])).lstat().st_mode & 0o100)
        require(owner_executable is (row['git_mode'] == '100755'), 'target_owner_executable_mode_mismatch')
        data = base64.b64decode(value['base64'], validate=True)
        require(len(data) == row['bytes'] and git_blob(data) == row['git_blob'], 'target_git_blob_mismatch')
        actual.append(dict(row, git_blob=git_blob(data), git_mode='100755' if value['executable'] else '100644'))
    require(git_tree(actual) == expected_tree, 'target_actual_git_tree_mismatch')
    return {'file_count': len(actual), 'bytes': sum(row['bytes'] for row in actual),
            'all_original_sha256_git_blob_executable_modes_verified': True, 'tree_sha': expected_tree,
            'scope': 'Git owner-execute bit and API any-execute bit both match; read-only Unix permissions400/500 are permitted.'}


def compact_stage(value):
    def projection(item):
        if not isinstance(item, dict):
            return item
        return {key: ({'count': len(child), 'canonical_sha256': sha(canonical(child))}
                if isinstance(child, (list, dict)) else child) for key, child in item.items()}
    return {key: projection(child) if key in {'analysis', 'compiler_collection', 'static_collection'} else child
            for key, child in value.items()}


def invoke(prepared, target_source, output, *, stage_function=None, command_function=None):
    """No caller can change actual API flags/caps; dependency injection is for owned controls."""
    from nico.assessment_cpp_project_static import run_project_static_stage
    from nico.assessment_cpp_project_static import PROGRAM as PRIMARY_PROGRAM
    from nico.assessment_cpp_clang_fallback import PROGRAM as FALLBACK_PROGRAM
    from nico.assessment_cpp_full_project_execution import _command
    output = Path(output)
    require(output.absolute() == output.resolve() and output.is_relative_to(HERE / 'runs')
            and not output.exists(), 'private_new_output_required')
    output.mkdir(mode=0o700, parents=True)
    events = []; command_intervals = []; retention_intervals = []; last_stage = [None]
    start = time.monotonic()
    def write(name, value):
        data = canonical(value)
        require(len(data) <= 8 * 1024 * 1024, 'diagnostic_receipt_bound_exceeded')
        temporary = output / (name + '.tmp')
        temporary.write_bytes(data); temporary.replace(output / name)
    def retain(value):
        before = time.monotonic()
        compact = compact_stage(value)
        write('static-stage-receipt.json', compact)
        last_stage[0] = strict_json(canonical(compact))
        events.append({'phase': value['phase'], 'runner_elapsed_ms': round((before - start) * 1000, 3),
                       'scope': 'Observed API save callback; not a separate request/validation timer.'})
        retention_intervals.append({'kind': 'stage_receipt_callback', 'duration_ms': round((time.monotonic() - before) * 1000, 3)})
    def retain_artifact(key, data):
        before = time.monotonic()
        require(key in {'project-static-environment', 'project-static-evidence', 'project-static-clang-fallback'}
                and isinstance(data, bytes) and len(data) <= 48 * 1024 * 1024, 'diagnostic_artifact_bound_invalid')
        digest = sha(data); name = 'artifacts/' + key + '-' + digest + '.json'
        path = output / name; path.parent.mkdir(exist_ok=True, mode=0o700)
        require(not path.exists(), 'diagnostic_artifact_overwrite_rejected')
        path.write_bytes(data)
        retention_intervals.append({'kind': 'artifact_retention_callback', 'duration_ms': round((time.monotonic() - before) * 1000, 3),
                                    'bytes': len(data), 'sha256': digest})
        return {'path': name, 'bytes': len(data), 'sha256': digest}
    def command(argv, **kwargs):
        before = time.monotonic()
        program = argv[argv.index('-c') + 1] if '-c' in argv and argv.index('-c') + 1 < len(argv) else None
        kind = ('primary_static_transport' if program == PRIMARY_PROGRAM else
                'fallback_static_transport' if program == FALLBACK_PROGRAM else 'stage_command')
        cleanup = (argv[:3] == ['docker', 'rm', '--force'] or
                   argv[:2] == ['docker', 'exec'] and argv[-2:] == ['cat', '/sys/fs/cgroup/memory.peak'])
        try:
            return (command_function or _command)(argv, **kwargs)
        finally:
            command_intervals.append({'kind': 'cleanup_command' if cleanup else kind,
                'duration_ms': round((time.monotonic() - before) * 1000, 3),
                'argv_sha256': sha(canonical(argv)), 'scope': 'Runner-observed command call, including transport; not CPU time.'})
    invocation_exception = None
    try:
        result = (stage_function or run_project_static_stage)(target_source, prepared['targets'],
            prepared['image']['selected_config_digest'], prepared['database'], prepared['snapshot'], prepared['compiler_raw'],
            retain=retain, retain_artifact=retain_artifact, checkpoint=lambda: None, command=command, **FLAGS)
        require(isinstance(result, dict) and result.get('production_qualified') is False and
                (result.get('schema') == 'nico.cpp-project-static-stage.v4' or
                 result.get('schema') == 'nico.cpp-project-static-stage.v1' and
                 result.get('complete') is False and bool(result.get('error'))), 'unexpected_stage_result')
    except (Exception, KeyboardInterrupt) as error:
        invocation_exception = {'type': type(error).__name__, 'message': str(error)}
        result = last_stage[0] or {'schema': None, 'phase': 'no_stage_callback_retained', 'operations': [],
                                  'analysis': None, 'production_qualified': False}
        result = dict(result, complete=False,
                      error=result.get('error') or 'private_runner_invocation_exception')
    analysis = result.get('analysis') if isinstance(result.get('analysis'), dict) else {}
    image_verified = False
    image_inspection_error = None
    for row in result.get('operations', []):
        if row.get('id') == 'static-image' and row.get('exit_code') == 0 and not row.get('timed_out') and not row.get('output_truncated'):
            try:
                observed = strict_json(base64.b64decode(row['output'], validate=True))
                image_verified = (isinstance(observed, list) and len(observed) == 1
                                  and isinstance(observed[0], dict)
                                  and observed[0].get('Id') == prepared['image']['selected_config_digest'])
            except (ValueError, KeyError, TypeError) as error:
                image_inspection_error = {'type': type(error).__name__, 'message': str(error)}
    selected_image = dict(prepared['image'], local_image_config_inspection_verified=image_verified,
        exact_original_image_restoration_verified=image_verified and prepared['image']['kind'] == 'exact-retained',
        runner_inspection_error=image_inspection_error,
        live_toolchain_header_input_equivalence_to_retained001f='UNKNOWN_UNTIL_FRESH_RECEIPTS')
    transport_attempted = (any(row.get('id') in {'project-static-evidence', 'project-static-clang-fallback'}
                              for row in result.get('operations', [])) or
                           any(row['kind'] in {'primary_static_transport', 'fallback_static_transport'}
                               for row in command_intervals))
    observed = True if analysis.get('static_analysis_executed') is True else None if transport_attempted else False
    summary = {'schema': 'nico.private.static_stage_diagnostic_result.v1',
        'status': 'STATIC_STAGE_ONLY_COMPLETED' if result.get('complete') is True and not result.get('error') else 'UNPROVEN',
        'plan': prepared['summary'], 'static_stage_complete': result.get('complete') is True,
        'static_collection_complete_with_findings': result.get('collection_complete') is True,
        'actual_stage_schema': result.get('schema'), 'actual_stage_error': result.get('error'),
        'invocation_exception': invocation_exception,
        'selected_library': prepared['library'], 'selected_image': selected_image,
        'fresh_static_execution_observed': observed,
        'fresh_static_transport_attempted': transport_attempted,
        'execution_observation': ('OBSERVED_STATIC_ANALYSIS' if observed is True else
                                 'UNKNOWN_AFTER_STATIC_TRANSPORT_ATTEMPT' if transport_attempted else
                                 'NO_STATIC_TRANSPORT_OBSERVED'),
        'reused_compiler_provenance_only': True, 'compiled': False, 'tests_executed': False,
        'assessment_completed': False, 'full_native_qualified': False, 'production_qualified': False,
        'api_total_observed_ms': round((time.monotonic() - start) * 1000, 3),
        'retention_callback_intervals': retention_intervals, 'command_intervals': command_intervals,
        'observed_api_phase_callbacks': events,
        'opaque_api_subphase_ms': {'request_construction': None, 'validation': None,
                                 'inside_api_retention': None, 'cleanup_outside_wrapped_commands': None},
        'prior_timing_residual_reattributed': False,
        'mock_injection_used': stage_function is not None or command_function is not None}
    write('diagnostic-result.json', summary)
    return summary

