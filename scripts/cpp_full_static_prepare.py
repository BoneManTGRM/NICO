"""Prepare a new same-image full-static diagnostic through supported private inputs.

The actual retained receipt anchor is derived from the current trusted private
transport proof and verified provider members; historical metadata stays private.
No CLI, provider transport, image load or native execution path is implemented.
"""
from __future__ import annotations

import importlib.machinery, importlib.util

import argparse

import base64

import hashlib

import json

import linecache

import os

from pathlib import Path

import re

import stat

import sys

import time

import types

HELPER_SHA = '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344'

RECIPE_INPUTS_SHA = '5e77eb4b1a01d2d29829ba2b34de56f599d917f6bdf3d1c41ff43469d8abc290'

RECIPE_HEAD = 'f0919654edd719059ea03319981b13f46ba70a88'

RECIPE_TREE = 'b9e200f62b9b2db9c6488326826ad8ae393418d0'

GUARD_SHA = '3ab2c2b9c1a4c3bd20f0d6af34655a6b53e2f02ebd490554f0b189929fedd7db'

GUARD_BLOB = '101dd7dda7523347d4d148a947adeed376f7e194'

BASELINE_COMPILER_SHA = 'be5b8be8386189af7f51e2ce47681b181a6c71a5e8384146da6deb8289e81276'

CANDIDATE_COMPILER_SHA = '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8'

CANDIDATE_COMPILER_BLOB = 'ebc3bdfdc0d9e86c59a8ff2fded5312e75d5d05b'

BENCHMARK_SHA = '66c3d940128ce3625fad9411448e71c06000a1b045adadde59246ea8ba2637b9'

FROZEN_COMMIT = 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24'

FROZEN_TREE = '186194c9de7f613d2d323db41cb8ce6bf1e3e549'

MAX_FILE = 64 * 1024 * 1024

MAX_META = 8 * 1024 * 1024


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

class PreparationRejected(ValueError):
    pass

def require(ok, code):
    if not ok:
        raise PreparationRejected(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def hexadecimal(value, length, code):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), code)
    return value

def unique(rows):
    output = {}
    for key, value in rows:
        require(key not in output, 'duplicate_json_key')
        output[key] = value
    return output

def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, 'nonfinite_json'))

def regular(path, maximum=MAX_FILE, digest=None, size=None):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path, 'noncanonical_or_symlink_path')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'regular_file_bound')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) <= maximum and len(raw) == before.st_size and
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'file_changed')
    require(digest is None or sha(raw) == digest, 'file_digest')
    require(size is None or type(size) is int and len(raw) == size, 'file_length')
    return raw

def module_from_verified_buffer(path, digest, label):
    raw = regular(path, digest=digest)
    filename = str(Path(path).absolute())
    source = raw.decode('utf-8')
    linecache.cache[filename] = (len(raw), None, source.splitlines(True), filename)
    return _import_verified_buffer(filename, raw, label)

def assert_current_transport(records, pins, *, expected_operation, expected_preparer):
    hexadecimal(expected_operation, 40, 'expected_operation')
    hexadecimal(expected_preparer, 64, 'expected_preparer')
    require(records.get('schema') == 'nico.private.runtime_preparation.v1'
            and records.get('status') == 'PRIVATE_RETAINED_INPUTS_PREPARED'
            and pins.get('schema') == 'nico.c34.same_image_parser_diagnostic_input_pins.v1', 'prepared_transport_schema')
    require(records['source']['commit'] == expected_operation and records['adapter_sha256'] == expected_preparer,
            'current_transport_operation_binding')
    require(records['recipe_source']['commit'] == pins['recipe_source']['commit'] == RECIPE_HEAD
            and records['recipe_source']['tree'] == pins['recipe_source']['tree'] == RECIPE_TREE
            and records['recipe_source']['tracked_files'] == pins['recipe_source']['tracked_files'] == 3305,
            'prepared_recipe_binding')
    require(records.get('decoded_provider_raw_zip_not_old_local_annotation') is True
            and records.get('target_or_native_execution') is False
            and records.get('historical_exact_image_replay_satisfied') is False,
            'transport_scope')
    obligations = records['required_full_obligations_unchanged']
    require(obligations == {'contexts': 577, 'fallback_contexts': 576, 'full_headers_and_generated_inputs': True},
            'transport_obligations')
    rows = pins['baseline']['members']
    require(type(rows) is list and len(rows) == 32 and len({row['path'] for row in rows}) == 32,
            'decoded32_unique_population')
    download = records['downloads']['baseline']
    provider = records['provider_records']['baseline']
    require(download.get('provider_raw_zip_verified') is True
            and type(download['bytes']) is int and download['bytes'] == provider['size_in_bytes']
            and 'sha256:' + download['sha256'] == provider['digest'], 'current_provider_zip_receipt')
    image = pins['image']
    hexadecimal(image['image_config_id'][7:] if image['image_config_id'].startswith('sha256:') else '', 64, 'image_config')
    hexadecimal(image['tar_sha256'], 64, 'image_tar_sha')
    proof = records['complete_archive_proof']
    require(proof['config_id'] == image['image_config_id'] and proof['archive']['sha256'] == image['tar_sha256']
            and proof['archive']['bytes'] == image['tar_bytes'] and proof['all_layer_diffids_verified'] is True
            and proof['safe_unique_outer_regular_or_directory_members'] is True, 'prepared_complete_image_binding')

def verify_decoded_members(runner, baseline, rows):
    actual = set()
    for path in baseline.rglob('*'):
        require(not path.is_symlink() and (path.is_file() or path.is_dir()), 'decoded_member_type')
        if path.is_file():
            actual.add(path.relative_to(baseline).as_posix())
    require(actual == {row['path'] for row in rows}, 'decoded32_actual_population')
    for row in rows:
        regular(baseline / runner.safe_path(row['path']), digest=row['sha256'], size=row['bytes'])

def source_map_from_listing(runner, root, listing, population):
    """Derive imports from actual trusted Git entries, never an older row map."""
    entries, sources = {}, {}
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        header, name_raw = entry.split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        name = runner.safe_path(name_raw.decode())
        require(name not in entries and kind == 'blob' and mode in {'100644', '100755'}, 'recipe_git_entry')
        hexadecimal(blob, 40, 'recipe_blob_shape')
        raw = regular(root / name)
        require(runner.git_blob(raw) == blob, 'recipe_blob_bytes')
        require(('100755' if (root / name).stat().st_mode & 0o111 else '100644') == mode, 'recipe_mode')
        entries[name] = {'git_blob': blob, 'git_mode': mode, 'sha256': sha(raw), 'bytes': len(raw)}
        if name.startswith('nico/') and name.endswith('.py'):
            sources[name] = (root / name, sha(raw))
    require(len(entries) == population and bool(sources), 'recipe_source_population')
    return entries, sources

def compiler_overlay(runner, entries, sources, operation, variant):
    name = 'nico/assessment_cpp_project_compiler.py'
    require(entries[name]['sha256'] == BASELINE_COMPILER_SHA, 'recipe_compiler_baseline')
    guard = entries['nico/assessment_cpp_clang_fallback.py']
    require(guard['sha256'] == GUARD_SHA and guard['git_blob'] == GUARD_BLOB, 'f091_guard_binding')
    require(variant in {'baseline', 'candidate'}, 'compiler_variant')
    selected = {'path': name, **entries[name], 'kind': 'unchanged_recipe_baseline'}
    if variant == 'candidate':
        path = operation / name
        raw = regular(path, digest=CANDIDATE_COMPILER_SHA)
        require(runner.git_blob(raw) == CANDIDATE_COMPILER_BLOB, 'candidate_compiler_blob')
        sources[name] = (path, CANDIDATE_COMPILER_SHA)
        selected = {'path': name, 'sha256': CANDIDATE_COMPILER_SHA, 'git_blob': runner.git_blob(raw),
                    'bytes': len(raw), 'kind': 'explicit_candidate_overlay'}
    return selected

def bind_library(runner, helper, operation, recipe, records, variant, expected_operation):
    require(not any(name == 'nico' or name.startswith('nico.') for name in sys.modules), 'nico_already_loaded')
    actual_recipe = helper.checked_git_source(recipe, RECIPE_HEAD, RECIPE_TREE, 3305)
    require(actual_recipe == records['recipe_source'], 'actual_recipe_proof_changed')
    actual_operation = helper.checked_git_source(operation, expected_operation)
    require(actual_operation == records['source'], 'actual_operation_proof_changed')
    listing = helper.command(['git', '-C', str(recipe), 'ls-tree', '-rz', '--full-tree', 'HEAD'],
                             maximum=2 * 1024 * 1024)
    entries, sources = source_map_from_listing(runner, recipe, listing, 3305)
    selected = compiler_overlay(runner, entries, sources, operation, variant)
    package = types.ModuleType('nico'); package.__path__ = []
    sys.modules['nico'] = package
    sys.meta_path.insert(0, runner.VerifiedFinder(sources))
    return {'selected_library_head': RECIPE_HEAD, 'selected_library_tree': RECIPE_TREE,
            'base_inventory_files_verified': 3305, 'base_inventory_sha256': actual_recipe['tracked_byte_blob_mode_inventory_sha256'],
            'selected_compiler': selected, 'variant': variant, 'actual_operation': actual_operation,
            'generated_worker_program_source': {'recipe_commit': RECIPE_HEAD, 'recipe_tree': RECIPE_TREE,
                                               'compiler_selection': selected},
            'generated_PROGRAMs_attributed_to_recipe_alone': variant == 'baseline',
            'source_loader_uses_verified_text_not_cached_bytecode': True,
            'matching_whole_library_and_image_source_inferred': False}

def assert_policy(runner, stage, capacity, fallback):
    require((stage.STAGE_EXECUTION_SECONDS, stage.STAGE_WALL_SECONDS) == (1020, 1030)
            and stage.LIMITS == {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
            and fallback.LOW_CONTENTION_LIMITS == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}
            and stage.STAGE_BUDGET['limits_share_execution_envelope'] is True, 'unchanged_static_policy')
    resources = capacity.resources_for(capacity.BASELINE_QUALIFICATION_PROFILE)
    require(all(resources[key] == runner.LIMITS[key] for key in ('cpus', 'memory_bytes', 'pids', 'tmpfs_bytes')),
            'unchanged_native_resources')

def prepare(args, runner):
    start = time.perf_counter_ns()
    root = args.prepared_inputs
    require(root.is_dir() and root.resolve(strict=True) == root and root.stat().st_mode & 0o077 == 0,
            'private_prepared_root')
    records = decode(regular(root / 'host/preparation.json', MAX_META))
    pins = decode(regular(root / 'host/pins.json', MAX_META))
    # Caller supplies the reviewed preparer identity, and actual operation bytes
    # must match it. Receipt fields cannot create their own trusted source pin.
    regular(args.operation_source / 'scripts/cpp_private_diagnostic_inputs.py',
            digest=hexadecimal(args.expected_preparer_sha256, 64, 'expected_preparer'))
    assert_current_transport(records, pins, expected_operation=args.expected_operation,
                             expected_preparer=args.expected_preparer_sha256)
    baseline = root / 'host/baseline'
    verify_decoded_members(runner, baseline, pins['baseline']['members'])
    helper = module_from_verified_buffer(args.operation_source / 'scripts/cpp_diagnostic_image_rebuild.py',
                                         HELPER_SHA, 'private_exact_archive_and_git_helper')
    recipe_inputs = decode(regular(args.operation_source / 'scripts/cpp_diagnostic_image_inputs.json',
                                  MAX_META, RECIPE_INPUTS_SHA))
    receipt_ref = next(row for row in pins['baseline']['members']
                       if row['path'] == 'cpp-baseline-qualification/receipt.json')
    receipt_anchor = hexadecimal(pins['baseline']['receipt_sha256'], 64, 'trusted_receipt_anchor')
    require(receipt_ref['sha256'] == receipt_anchor and type(receipt_ref['bytes']) is int
            and 0 < receipt_ref['bytes'] <= MAX_FILE,
            'trusted_transport_receipt_member_binding')
    receipt_raw = regular(baseline / 'cpp-baseline-qualification/receipt.json',
                          digest=receipt_anchor, size=receipt_ref['bytes'])
    receipt = decode(receipt_raw); probe = receipt['probe']; target = receipt['source']; targets = target['targets']
    benchmark_raw = regular(args.recipe_source / 'tests/fixtures/cpp/bitcoin-configuration-benchmark.json',
                            MAX_META, BENCHMARK_SHA)
    benchmark = decode(benchmark_raw)
    require(receipt['benchmark_sha256'] == BENCHMARK_SHA and benchmark['repository'] == 'bitcoin/bitcoin'
            and benchmark['commit_sha'] == FROZEN_COMMIT and benchmark['tree_sha'] == FROZEN_TREE,
            'frozen_benchmark_binding')
    require(receipt['producer_source_sha'] == recipe_inputs['recipe_original_producer']
            and probe['image_config_digest'] == pins['baseline']['historical_image_id'], 'retained_producer_binding')
    frozen = pins['frozen_target']
    require(target['repository'] == frozen['repository'] == 'bitcoin/bitcoin'
            and target['commit_sha'] == frozen['commit'] == FROZEN_COMMIT
            and target['tree_sha'] == frozen['tree'] == FROZEN_TREE
            and len(targets) == 3031 and sha(canonical(targets)) == frozen['target_population_sha256'] ==
            probe['source_population_sha256'], 'retained_frozen_target_binding')
    inventory = [{key: row[key] for key in ('path', 'bytes', 'sha256', 'git_blob', 'git_mode')}
                 for row in target['inventory'] if row['git_type'] == 'blob']
    require(len(inventory) == 3031 and {row['path']: row['sha256'] for row in inventory} == targets
            and sum(row['bytes'] for row in inventory) == target['source_bytes'] == 49729651
            and runner.git_tree(inventory) == target['tree_sha'], 'retained_target_inventory')
    library = bind_library(runner, helper, args.operation_source, args.recipe_source, records,
                           args.variant, args.expected_operation)
    from nico.assessment_cpp_full_project import _database
    from nico.assessment_cpp_native_commands import configured_native_commands
    from nico.assessment_cpp_fileapi_membership import runtime_cmake_path
    from nico.assessment_cpp_project_snapshot import validate_project_snapshot
    from nico.assessment_cpp_project_compiler import project_compiler_request
    from nico import assessment_cpp_project_static as stage
    from nico import assessment_cpp_clang_fallback as fallback
    from nico import assessment_worker_capacity_v1 as capacity
    assert_policy(runner, stage, capacity, fallback)
    def artifact(ref):
        return regular(baseline / 'cpp-baseline-qualification' / runner.safe_path(ref['path']),
                       digest=ref['sha256'], size=ref['bytes'])
    database = base64.b64decode(probe['compilation_database'], validate=True)
    cache = base64.b64decode(probe['configuration_cache'], validate=True)
    require(sha(database) == probe['compilation_database_sha256'] and
            sha(cache) == probe['configuration_cache_sha256'], 'retained_database_cache_binding')
    plan = configured_native_commands(artifact(probe['native_command_capture']), artifact(probe['enabled_target_capture']),
        database, targets, source_root='/work/source', build_root='/work/build', client=probe['fileapi_client'],
        cache_sha256=probe['configuration_cache_sha256'], compiler_versions={'C': '14.2.0', 'CXX': '14.2.0'},
        compiler_paths={'C': '/usr/local/bin/gcc', 'CXX': '/usr/local/bin/g++'}, cmake_path=runtime_cmake_path(True))
    analysisdb = base64.b64decode(plan['analysis_database'], validate=True)
    require(sha(analysisdb) == probe['analysis_compilation_database_sha256'], 'retained_analysis_database_binding')
    contexts = _database(analysisdb, None, '/work/build', nested=True, source_targets=targets)
    snapshot = validate_project_snapshot(decode(artifact(probe['generated_context']['artifact'])), contexts)
    compiler_raw = artifact(probe['project_compiler']['artifact'])
    request = project_compiler_request(analysisdb, targets, snapshot, extended_budget=True)
    require(sha(canonical(request)) == decode(compiler_raw)['request_sha256'], 'retained_compiler_request_binding')
    require(len(request['contexts']) == 577 and len(snapshot['files']) == 143
            and len(snapshot['generated_units']) == 42, 'retained_static_input_population')
    # A new rebuilt diagnostic identity; no historical image constants are
    # required by the generic original-definition execution context.
    image = {'selected_config_digest': pins['image']['image_config_id'], 'kind': 'alternate-rebuilt',
             'alternate_rebuilt_label': 'verified pinned diagnostic rebuild',
             'complete_archive_preparation_verified': True, 'archive_sha256': pins['image']['tar_sha256'],
             'historical_exact_image_replay_satisfied': False,
             'exact_original_image_restoration_verified': False}
    summary = {'schema': 'nico.private.full_static_adapter_plan.v1', 'mode': 'plan-only',
               'library': library, 'image': image, 'frozen_target': {key: target[key] for key in
                   ('repository', 'commit_sha', 'tree_sha')}, 'source_population': 3031,
               'snapshot_files': 143, 'generated_units': 42, 'compiler_contexts': 577,
               'historical_required_fallback_contexts': 576, 'flags': runner.FLAGS, 'limits': runner.LIMITS,
               'accepted_historical_diagnosis_reused': True, 'new_population_reconciliation_executed': False,
               'genuine_compiler_failure_preserved': True, 'compiler_input_provenance':
                   {'reused_retained_bytes': True, 'native_sha256': sha(compiler_raw), 'all_compiler_contexts_passed': False},
               'wall_scope': {'declared_api_wall_seconds': 1030, 'shared_execution_seconds': 1020,
                              'independent1030_hardwall_supervisor_present': False,
                              'sequential_pair_policy_execution_upper_seconds': 2040,
                              'job_outer_budget_minutes': 155, 'parent_setup_transfer_retention_cleanup_costs': None},
               'preparation_observed_ms': (time.perf_counter_ns() - start) / 1e6,
               'fresh_static_execution_observed': False, 'compiled': False, 'tests_executed': False,
               'assessment_completed': False, 'full_native_qualified': False, 'production_qualified': False}
    return {'summary': summary, 'targets': targets, 'target_inventory': inventory, 'database': analysisdb,
            'snapshot': snapshot, 'compiler_raw': compiler_raw, 'library': library, 'image': image}
