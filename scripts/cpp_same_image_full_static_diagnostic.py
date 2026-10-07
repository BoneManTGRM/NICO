"""Private connected baseline-first full-static pair on one verified loaded image.

The normal job prepares retained inputs and produces the dependency proof before
this caller. This caller has no provider client, dependency installer, image
builder, cache reset, target compiler/runtime entrypoint, or qualification gate.
Every stage call is an unchanged selected-scope invoke in a fresh CP311 process.
"""
from __future__ import annotations

import importlib.machinery, importlib.util

import argparse
import hashlib
import json
import linecache
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import time
import types

MAX_META = 8 * 1024 * 1024
MAX_SOURCE = 64 * 1024 * 1024
MAX_PROOF = 1024 * 1024
HELPER_SHA = '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344'
VERIFIER_SHA = '8c2be8a8ae1cff4366a8d57862bcaefab8873d29910570d3f65329bbb783186c'
WHEEL_MANIFEST_SHA = '2ab68d647ec57ec6e459f4ae7325dade7917d1336252552518019213be7b6d2d'
FIXED_IMAGE = 'sha256:2de94c121db7ae46df5415a40b33cd2d057fcc3b7bf9aa9d51756ecb4412447e'
RECIPE_HEAD = 'f0919654edd719059ea03319981b13f46ba70a88'
RECIPE_TREE = 'b9e200f62b9b2db9c6488326826ad8ae393418d0'
BASELINE_COMPILER_SHA = 'be5b8be8386189af7f51e2ce47681b181a6c71a5e8384146da6deb8289e81276'
CANDIDATE_COMPILER_SHA = '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8'
FROZEN_HEAD = 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24'
FROZEN_TREE = '186194c9de7f613d2d323db41cb8ce6bf1e3e549'
REPOSITORY = 'BoneManTGRM/NICO'
BRANCH = 'refs/heads/diagnostic/v17-pinned-image-20261007'
WORKFLOW = '.github/workflows/cpp-same-image-full-static-diagnostic.yml'
JOB = 'same-image-full-static-diagnostic'
SOURCE_PATHS = {
    'caller': 'scripts/cpp_same_image_full_static_diagnostic.py',
    'scope': 'scripts/cpp_static_runner_scope.py',
    'prepare': 'scripts/cpp_full_static_prepare.py',
    'preparer': 'scripts/cpp_private_diagnostic_inputs.py',
    'exporter': 'scripts/cpp_full_static_diagnostic_export.py',
    'verifier': 'scripts/verify_cpp_host_dependencies.py',
    'wheel_manifest': 'scripts/cpp-static-diagnostic-inputs/host-wheels.json',
    'image_helper': 'scripts/cpp_diagnostic_image_rebuild.py',
}
GHA_IDENTITY_NAMES = (
    'GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_REPOSITORY_ID', 'GITHUB_REF',
    'GITHUB_EVENT_NAME', 'GITHUB_RUN_ATTEMPT', 'GITHUB_RUN_ID', 'GITHUB_JOB',
    'GITHUB_WORKFLOW_SHA', 'GITHUB_WORKFLOW_REF', 'RUNNER_ENVIRONMENT',
    'RUNNER_NAME', 'RUNNER_TEMP',
)
CREDENTIAL_NAMES = (
    'GITHUB_TOKEN', 'GH_TOKEN', 'ACTIONS_RUNTIME_TOKEN',
    'ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_URL',
)



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

class CallerRejected(ValueError):
    """Only safe fixed codes are printed; private receipts retain other details."""


def require(ok, code):
    if not ok:
        raise CallerRejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(rows):
    result = {}
    for name, value in rows:
        require(name not in result, 'duplicate_json_key')
        result[name] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, 'nonfinite_json'))


def hexadecimal(value, length, code):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), code)
    return value


def path_value(value):
    path = Path(value).absolute()
    require(path == path.resolve() and ',' not in str(path), 'canonical_path')
    return path


def fingerprint(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def regular(path, maximum=MAX_SOURCE, digest=None, size=None):
    path = path_value(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'regular_file_bound')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) == before.st_size <= maximum and fingerprint(before) == fingerprint(after)
            and fingerprint(after) == fingerprint(path.stat()), 'file_changed')
    require(digest is None or sha(raw) == digest, 'file_digest')
    require(size is None or type(size) is int and len(raw) == size, 'file_length')
    return raw


def write_private(path, value):
    raw = canonical(value) + b'\n'
    require(len(raw) <= MAX_META, 'private_receipt_bound')
    temporary = path.with_name(path.name + '.tmp')
    require(not temporary.exists(), 'receipt_temporary_exists')
    with temporary.open('xb') as stream:
        os.chmod(temporary, 0o600)
        stream.write(raw)
    temporary.replace(path)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def module_buffer(path, raw, label):
    """Execute precisely one checked public source buffer; no cached imports."""
    source = raw.decode('utf-8')
    linecache.cache[str(path)] = (len(raw), None, source.splitlines(True), str(path))
    return _import_verified_buffer(path, raw, label)


def span(rows, name, function):
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    try:
        return function()
    finally:
        rows.append({'phase': name, 'wall_ms': (time.perf_counter_ns() - wall) / 1e6,
                     'process_cpu_ms': (time.process_time_ns() - cpu) / 1e6,
                     'clock_domain': 'this_process_perf_counter_and_process_time',
                     'cpu_scope': 'This host process only; excludes analyzer/container and child-process CPU.'})


def source_bindings(args, helper):
    operation = helper.checked_git_source(args.operation_source, args.expected_operation)
    records = decode(regular(args.prepared_inputs / 'host/preparation.json', MAX_META))
    require(operation == records['source'], 'actual_operation_transport_proof')
    listing = helper.command(['git', '-C', str(args.operation_source), 'ls-tree', '-rz', '--full-tree', 'HEAD'],
                             maximum=2 * 1024 * 1024)
    blobs = {}
    for entry in listing.split(b'\0'):
        if entry:
            header, name = entry.split(b'\t', 1)
            mode, kind, blob = header.decode().split()
            require(kind == 'blob' and mode in {'100644', '100755'} and name.decode() not in blobs,
                    'operation_git_entry')
            blobs[name.decode()] = (mode, blob)
    selected_paths = dict(SOURCE_PATHS)
    sample_mode = (getattr(args, 'fallback_capacity_sample', None) is True
                   or getattr(args, 'fallback_parallel_pair', None) is True)
    if sample_mode:
        selected_paths['sample'] = 'scripts/cpp_fallback_capacity_sample.py'
    if getattr(args, 'fallback_parallel_pair', None) is True:
        selected_paths['parallel_pair'] = 'scripts/cpp_fallback_parallel_pair.py'
    expected = {'caller': args.expected_caller_sha256, 'scope': args.expected_scope_sha256,
                'prepare': args.expected_prepare_sha256, 'preparer': args.expected_preparer_sha256,
                'exporter': args.expected_exporter_sha256, 'verifier': VERIFIER_SHA,
                'wheel_manifest': WHEEL_MANIFEST_SHA, 'image_helper': HELPER_SHA}
    if sample_mode:
        expected['sample'] = args.expected_sample_sha256
    if getattr(args, 'fallback_parallel_pair', None) is True:
        expected['parallel_pair'] = args.expected_pair_sha256
    rows, buffers = {}, {}
    for key, name in selected_paths.items():
        digest = hexadecimal(expected[key], 64, 'expected_source_sha')
        raw = regular(args.operation_source / name, digest=digest)
        require(name in blobs and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
                == blobs[name][1], 'actual_source_git_blob')
        rows[key] = {'path': name, 'bytes': len(raw), 'sha256': digest,
                     'git_blob': blobs[name][1], 'git_mode': blobs[name][0]}
        buffers[key] = raw
    require(regular(Path(__file__), digest=args.expected_caller_sha256) == buffers['caller'],
            'executing_caller_actual_git_bytes')
    return operation, rows, buffers


def authority(args, helper):
    require(platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 11)
            and sys.flags.isolated == 1 and sys.dont_write_bytecode is True, 'isolated_cp311_required')
    hexadecimal(args.expected_operation, 40, 'expected_operation')
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REPOSITORY_ID') == '1282576027'
            and os.environ.get('GITHUB_REF') == BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_JOB') == JOB
            and re.fullmatch(r'[0-9]+', os.environ.get('GITHUB_RUN_ID', '')) is not None
            and os.environ.get('GITHUB_SHA') == args.expected_operation
            and os.environ.get('GITHUB_WORKFLOW_SHA') == args.expected_operation
            and os.environ.get('GITHUB_WORKFLOW_REF') == REPOSITORY + '/' + WORKFLOW + '@' + BRANCH
            and helper.git_value(args.operation_source, 'HEAD') == args.expected_operation,
            'actual_operation_authority')
    runner_temp = path_value(os.environ['RUNNER_TEMP'])
    require(args.prepared_inputs.is_relative_to(runner_temp) and args.prepared_inputs != runner_temp
            and args.output.is_relative_to(runner_temp) and args.output != runner_temp
            and args.dependency_proof.is_relative_to(runner_temp)
            and args.dependency_proof.stat().st_mode & 0o077 == 0,
            'private_runner_temp_roots')
    require(args.prepared_inputs.is_dir() and args.prepared_inputs.stat().st_mode & 0o077 == 0,
            'private_prepared_directory')
    return {'current_git_head': args.expected_operation,
            'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': 1,
            'workflow_ref': os.environ['GITHUB_WORKFLOW_REF'], 'job': JOB,
            'runner_environment': 'github-hosted', 'runner_name': os.environ.get('RUNNER_NAME')}


def dependencies(args, verifier):
    raw = regular(args.dependency_proof, MAX_PROOF, args.expected_proof_sha256, args.expected_proof_bytes)
    proof = decode(raw)
    current = verifier.validate_current_receipt(proof, VERIFIER_SHA, WHEEL_MANIFEST_SHA)
    return {'whole_proof': {'bytes': len(raw), 'sha256': sha(raw)},
            'actual_current_validation': current, 'proof_produced_in_this_process': False}


def command(argv, rows, name, *, timeout=30, check=True, maximum=MAX_META):
    def run():
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
        require(len(result.stdout) + len(result.stderr) <= maximum, 'operation_output_bound')
        rows.append({'operation': name, 'argv_sha256': sha(canonical(argv)), 'exit_code': result.returncode,
                     'stdout_bytes': len(result.stdout), 'stdout_sha256': sha(result.stdout),
                     'stderr_bytes': len(result.stderr), 'stderr_sha256': sha(result.stderr)})
        require(not check or result.returncode == 0, 'operation_failed')
        return result
    return span(rows, name, run)


def image_binding(args, helper, prepare, operations):
    records_raw = regular(args.prepared_inputs / 'host/preparation.json', MAX_META)
    pins_raw = regular(args.prepared_inputs / 'host/pins.json', MAX_META)
    records, pins = decode(records_raw), decode(pins_raw)
    prepare.assert_current_transport(records, pins, expected_operation=args.expected_operation,
                                     expected_preparer=args.expected_preparer_sha256)
    require(pins['image']['image_config_id'] == FIXED_IMAGE, 'fixed_image_identity')
    require(records.get('public_metadata_export') is False and records.get('new_artifact_upload') is False
            and records['actual_observed_scratch_peak_bytes'] <= 6 * 1024 * 1024 * 1024,
            'supported_private_preparation_scope')
    build_raw = regular(args.prepared_inputs / 'host/image/receipt.json', MAX_META,
                        pins['image']['build_receipt_sha256'])
    retrieval_raw = regular(args.prepared_inputs / 'host/retrieval/receipt.json', MAX_META,
                            pins['image']['prior_retrieval_receipt_sha256'])
    build, retrieval = decode(build_raw), decode(retrieval_raw)
    require(build.get('schema') == 'nico.private.diagnostic_image_rebuild.v1'
            and build.get('status') == 'DIAGNOSTIC_IMAGE_SAVED_UNRETRIEVED'
            and build.get('production_qualified') is False and build.get('target_execution') is False
            and build['operation']['workflow_head'] == pins['image']['build_head']
            and build['operation']['run_id'] == str(pins['image']['run_id'])
            and build['operation']['run_attempt'] == 1 and build['operation']['helper_sha256'] == HELPER_SHA
            and build['recipe_source']['commit'] == RECIPE_HEAD
            and build['recipe_source']['tree'] == RECIPE_TREE
            and build['image_config_id'] == FIXED_IMAGE == build['image_inspection']['Id']
            and build['image_inspection']['RootFS']['Layers'] == pins['image']['expected_layers'],
            'independent_image_build_binding')
    require(retrieval.get('status') == 'DIAGNOSTIC_IMAGE_RETRIEVED_COMPLETE_IDENTITY_VERIFIED'
            and retrieval.get('production_qualified') is False and retrieval.get('target_execution') is False
            and retrieval.get('complete_image_archive_verified') is True
            and retrieval.get('supported_storage_retrieval_verified') is True
            and retrieval['build_receipt_sha256'] == pins['image']['build_receipt_sha256']
            and retrieval['operation']['workflow_head'] == pins['image']['build_head']
            and retrieval['operation']['run_id'] == str(pins['image']['run_id'])
            and retrieval['operation']['run_attempt'] == 1
            and retrieval['image_config_id'] == FIXED_IMAGE,
            'independent_prior_retrieval_binding')
    proof = span(operations, 'whole_image_archive_verification', lambda: helper.archive_proof(
        args.prepared_inputs / 'host/image/image.tar', FIXED_IMAGE, pins['image']['expected_layers']))
    require(proof == build['archive_proof'] == retrieval['archive_proof'] == records['complete_archive_proof']
            and proof['archive']['sha256'] == pins['image']['tar_sha256']
            and proof['archive']['bytes'] == pins['image']['tar_bytes'], 'whole_image_archive_binding')
    reserve = records['preflights'][-1]['separately_supplied_load_store_reserve_bytes']
    import shutil
    free = shutil.disk_usage(args.prepared_inputs).free
    require(type(reserve) is int and reserve > 0 and free >= reserve, 'host_load_store_reserve')
    absent = command(['docker', 'image', 'inspect', FIXED_IMAGE], operations, 'image_absence_preflight', check=False)
    require(absent.returncode != 0 and b'No such image' in absent.stderr,
            'fresh_runner_image_preexisting_or_daemon_unavailable')
    loaded = command(['docker', 'image', 'load', '--input', str(args.prepared_inputs / 'host/image/image.tar')],
                     operations, 'image_load', timeout=90)
    observed = span(operations, 'loaded_image_config_rootfs_verification', lambda: helper.inspection(FIXED_IMAGE))
    require(observed['RootFS']['Layers'] == build['image_inspection']['RootFS']['Layers']
            and observed['Config'] == build['image_inspection']['Config'], 'loaded_complete_image_identity')
    write_private(args.output / 'private-image-binding.json',
                  {'build_receipt_sha256': sha(build_raw), 'retrieval_receipt_sha256': sha(retrieval_raw),
                   'pins_sha256': sha(pins_raw), 'preparation_sha256': sha(records_raw),
                   'whole_archive_proof': proof, 'loaded_image_inspection': observed,
                   'host_load_store_reserve_bytes': reserve, 'host_free_disk_before_load': free,
                   'load_stdout_sha256': sha(loaded.stdout), 'historical_exact_image_replay_satisfied': False})
    return {'selected_config_digest': FIXED_IMAGE, 'fixed_config_digest': FIXED_IMAGE,
            'loaded_image_inspection_verified': True, 'complete_archive_verified': True,
            'config_and_ordered_rootfs_equal_independent_build_receipt': True,
            'config_and_rootfs_sha256': sha(canonical({'Config': observed['Config'], 'RootFS': observed['RootFS']})),
            'same_selected_image_for_both_variants': True, 'historical_image_recovered': False,
            'matching_historical_live_toolchain_or_header_inputs_inferred': False}


def target_member(path, row, scope):
    raw = regular(path, digest=row['sha256'], size=row['bytes'])
    require(scope.git_blob(raw) == row['git_blob']
            and row['git_mode'] in {'100644', '100755'}
            and bool(path.stat().st_mode & 0o111) is (row['git_mode'] == '100755')
            and bool(path.stat().st_mode & 0o100) is (row['git_mode'] == '100755'),
            'original_git_bytes_and_modes')
    return raw


def checked_target_checkout(source, helper, scope, inventory, *, expected_commit, expected_tree, expected_population):
    """Verify exactly an already trusted target inventory, without a name alphabet.

    Canonical safe paths and exact inventory membership admit the pinned target's
    literal @ locale names. No new filename, blob, mode, or source population can
    be authorized by this checker. Production passes the unchanged frozen pins;
    explicit parameters permit owned tiny-Git controls only.
    """
    hexadecimal(expected_commit, 40, 'target_expected_commit')
    hexadecimal(expected_tree, 40, 'target_expected_tree')
    require(type(expected_population) is int and expected_population > 0
            and type(inventory) is list and len(inventory) == expected_population, 'target_inventory_population')
    expected = {}
    for row in inventory:
        name = scope.safe_path(row['path'])
        require(name not in expected and row['git_mode'] in {'100644', '100755'}, 'target_inventory_member')
        hexadecimal(row['git_blob'], 40, 'target_inventory_blob')
        expected[name] = row
    require(scope.git_tree(inventory) == expected_tree, 'target_inventory_tree')
    require(helper.git_value(source, 'HEAD') == expected_commit, 'target_source_commit')
    require(helper.git_value(source, 'HEAD^{tree}') == expected_tree, 'target_source_tree')
    # Preserve the original clean-index/worktree guard, including nonzero failure.
    subprocess.run(['git', '-C', str(source), 'diff-index', '--quiet', 'HEAD', '--'], check=True, timeout=30)
    listing = helper.command(['git', '-C', str(source), 'ls-tree', '-rz', '--full-tree', 'HEAD'],
                             maximum=2 * 1024 * 1024)
    actual, rows = set(), []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        header, name_raw = entry.split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        name = scope.safe_path(name_raw.decode())
        require(name in expected and name not in actual and kind == 'blob', 'target_git_exact_member')
        row = expected[name]
        require(mode == row['git_mode'] and blob == row['git_blob'], 'target_git_original_blob_and_mode')
        raw = target_member(Path(source) / name, row, scope)
        actual.add(name)
        rows.append({'path': name, 'git_blob': blob, 'git_mode': mode,
                     'bytes': len(raw), 'sha256': sha(raw), 'git_normalization': None})
    require(actual == set(expected) and len(rows) == expected_population, 'target_git_exact_population')
    return {'commit': expected_commit, 'tree': expected_tree, 'tracked_files': len(rows),
            'tracked_byte_blob_mode_inventory_sha256': sha(canonical(rows)),
            'checkout_eol_differences': []}


def copy_target(args, helper, scope):
    """Use checkout bytes; never Git archive export-subst or target execution."""
    pins = decode(regular(args.prepared_inputs / 'host/pins.json', MAX_META))
    receipt_row = next(row for row in pins['baseline']['members']
                       if row['path'] == 'cpp-baseline-qualification/receipt.json')
    require(receipt_row['sha256'] == pins['baseline']['receipt_sha256']
            and type(receipt_row['bytes']) is int and 0 < receipt_row['bytes'] <= MAX_SOURCE,
            'trusted_retained_inventory_anchor')
    receipt = decode(regular(args.prepared_inputs / 'host/baseline' / receipt_row['path'],
                             digest=receipt_row['sha256'], size=receipt_row['bytes']))
    original = receipt['source']
    require(original['repository'] == 'bitcoin/bitcoin' and original['commit_sha'] == FROZEN_HEAD
            and original['tree_sha'] == FROZEN_TREE, 'frozen_target_identity')
    inventory = [{key: row[key] for key in ('path', 'bytes', 'sha256', 'git_blob', 'git_mode')}
                 for row in original['inventory'] if row['git_type'] == 'blob']
    require(len(inventory) == len(original['targets']) == 3031
            and sum(row['bytes'] for row in inventory) == original['source_bytes'] == 49729651
            and {row['path']: row['sha256'] for row in inventory} == original['targets']
            and scope.git_tree(inventory) == FROZEN_TREE, 'retained3031_inventory')
    checkout = checked_target_checkout(args.target_checkout, helper, scope, inventory,
        expected_commit=FROZEN_HEAD, expected_tree=FROZEN_TREE, expected_population=3031)
    target = args.output / 'context/target'
    require(not target.exists(), 'new_data_only_target_required')
    target.mkdir(mode=0o700)
    for row in inventory:
        name = scope.safe_path(row['path'])
        path = args.target_checkout / name
        raw = target_member(path, row, scope)
        output = target / name
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(raw)
        output.chmod(0o500 if row['git_mode'] == '100755' else 0o400)
    actual = set()
    for path in target.rglob('*'):
        require(not path.is_symlink() and (path.is_dir() or path.is_file())
                and '.git' not in path.relative_to(target).parts, 'data_only_target_member')
        if path.is_file():
            actual.add(path.relative_to(target).as_posix())
    require(actual == set(original['targets']), 'data_only_exact_target_population')
    for row in inventory:
        path = target / row['path']
        target_member(path, row, scope)
    return {'directory': str(target), 'checkout_proof': checkout,
            'repository': 'bitcoin/bitcoin', 'commit_sha': FROZEN_HEAD,
            'file_count': 3031, 'bytes': 49729651, 'tree_sha': FROZEN_TREE,
            'all_original_sha256_git_blob_owner_and_any_executable_modes_verified': True,
            'data_only_copy_no_git': True, 'target_code_imported_compiled_or_run': False}


def child_environment():
    # No credential/cookie/provider token or arbitrary Python search path is copied.
    allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'TZ') + GHA_IDENTITY_NAMES
    return {name: os.environ[name] for name in allowed if name in os.environ}


def entry_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-settings', type=Path, help=argparse.SUPPRESS)
    for name in ('operation-source', 'recipe-source', 'prepared-inputs', 'target-checkout',
                 'output', 'dependency-proof'):
        parser.add_argument('--' + name, type=Path)
    for name in ('expected-operation', 'expected-caller-sha256', 'expected-scope-sha256',
                 'expected-prepare-sha256', 'expected-preparer-sha256', 'expected-exporter-sha256',
                 'expected-proof-sha256'):
        parser.add_argument('--' + name)
    parser.add_argument('--expected-proof-bytes', type=int)
    parser.add_argument('--fallback-capacity-sample', action='store_const', const=True, default=None)
    parser.add_argument('--expected-sample-sha256')
    parser.add_argument('--fallback-parallel-pair', action='store_const', const=True, default=None)
    parser.add_argument('--expected-pair-sha256')
    parser.add_argument('--pair-outer-deadline-monotonic', type=float)
    return parser.parse_args()


def normalize(args):
    for name in ('operation_source', 'recipe_source', 'prepared_inputs', 'target_checkout',
                 'output', 'dependency_proof'):
        require(getattr(args, name, None) is not None, 'required_cli_argument')
        setattr(args, name, path_value(getattr(args, name)))
    for name in ('expected_caller_sha256', 'expected_scope_sha256', 'expected_prepare_sha256',
                 'expected_preparer_sha256', 'expected_exporter_sha256', 'expected_proof_sha256'):
        hexadecimal(getattr(args, name, None), 64, 'expected_digest_argument')
    pair_mode = getattr(args, 'fallback_parallel_pair', None) is True
    require(not (pair_mode and getattr(args, 'fallback_capacity_sample', None) is True), 'exclusive_diagnostic_modes')
    if pair_mode:
        hexadecimal(getattr(args, 'expected_pair_sha256', None), 64, 'expected_pair_source_digest')
        deadline = getattr(args, 'pair_outer_deadline_monotonic', None)
        require(type(deadline) is float and 0 < deadline - time.monotonic() <= 155 * 60,
                'pair_authoritative_outer_deadline')
    else:
        require(getattr(args, 'expected_pair_sha256', None) is None
            and getattr(args, 'pair_outer_deadline_monotonic', None) is None, 'pair_source_without_pair_mode')
    if getattr(args, 'fallback_capacity_sample', None) is True or pair_mode:
        hexadecimal(getattr(args, 'expected_sample_sha256', None), 64, 'expected_sample_source_digest')
    else:
        require(getattr(args, 'expected_sample_sha256', None) is None, 'sample_source_without_sample_mode')
    require(type(args.expected_proof_bytes) is int and 0 < args.expected_proof_bytes <= MAX_PROOF,
            'expected_whole_proof_length')
    require(not args.output.is_relative_to(args.operation_source)
            and not args.output.is_relative_to(args.recipe_source)
            and not args.output.is_relative_to(args.target_checkout)
            and not args.output.is_relative_to(args.prepared_inputs), 'separate_private_output')
    return args


def worker(settings_path):
    settings_raw = regular(settings_path, MAX_META)
    require(settings_path.stat().st_mode & 0o077 == 0, 'private_worker_settings')
    settings = decode(settings_raw)
    if settings.get('schema') == 'nico.private.fallback_capacity_sample_worker_settings.v1':
        return sample_worker(settings_path, settings_raw, settings)
    require(settings.get('schema') == 'nico.private.full_static_worker_settings.v1'
            and settings.get('variant') in {'baseline', 'candidate'}
            and settings.get('parent_pid') == os.getppid(), 'connected_fresh_worker')
    args = normalize(argparse.Namespace(**settings['arguments']))
    intervals = []
    context = args.output / 'context'
    require(context.is_dir() and context.stat().st_mode & 0o077 == 0
            and Path(__file__).parent == context, 'private_worker_context')
    args.variant = settings['variant']
    output = context / 'runs' / args.variant
    process_receipt = {'schema': 'nico.private.full_static_process_receipt.v1', 'status': 'UNPROVEN',
        'variant': args.variant, 'fresh_process_pid': os.getpid(), 'parent_pid': os.getppid(),
        'actual_python': {'executable': sys.executable, 'version': sys.version,
                         'isolated': sys.flags.isolated == 1, 'no_bytecode': sys.dont_write_bytecode is True},
        'source_rows': None, 'target_verification': None,
        'dependency_before_preparation': None, 'dependency_before_stage': None,
        'intervals': intervals, 'mock_injection_used': False, 'full_native_qualified': False,
        'production_qualified': False, 'assessment_completed': False, 'compiled': False, 'tests_executed': False,
        'stage_invocation_attempted': False, 'error': None}
    # Keep the original invoke output nonexistent until its own creation guard.
    early_path = context / (args.variant + '-process-receipt.json')
    write_private(early_path, process_receipt)
    try:
        helper_raw = regular(args.operation_source / SOURCE_PATHS['image_helper'], digest=HELPER_SHA)
        helper = module_buffer(args.operation_source / SOURCE_PATHS['image_helper'], helper_raw, 'exact_image_helper')
        authority(args, helper)
        operation, source_rows, buffers = span(intervals, 'actual_source_binding', lambda: source_bindings(args, helper))
        require(source_rows == settings['source_rows'] and operation == settings['operation'], 'worker_actual_source_binding')
        require(regular(context / 'cpp_static_runner_scope.py') == buffers['scope'], 'private_scope_context')
        process_receipt['source_rows'] = source_rows
        scope = module_buffer(context / 'cpp_static_runner_scope.py', buffers['scope'], 'exact_selected_static_scope')
        prepare = module_buffer(args.operation_source / SOURCE_PATHS['prepare'], buffers['prepare'], 'exact_generic_prepare')
        verifier = module_buffer(args.operation_source / SOURCE_PATHS['verifier'], buffers['verifier'], 'exact_dependency_verifier')
        process_receipt['dependency_before_preparation'] = span(intervals, 'host_dependency_validation_before_preparation', lambda:
            dependencies(args, verifier))
        prepared = span(intervals, 'full_static_preparation', lambda: prepare.prepare(args, scope))
        target = context / 'target'
        process_receipt['target_verification'] = span(intervals, 'original_api_input_and_target_verification_before_stage', lambda:
            scope.verify_target_source(target, prepared['targets'], prepared['target_inventory'], FROZEN_TREE))
        process_receipt['dependency_before_stage'] = span(intervals, 'host_dependency_validation_before_stage', lambda:
            dependencies(args, verifier))
        process_receipt['stage_invocation_attempted'] = True
        write_private(early_path, process_receipt)
        # The original invoke default path calls the actual stage and actual command.
        # No stage_function or command_function argument is supplied.
        summary = span(intervals, 'actual_static_api_and_scope_retention', lambda: scope.invoke(prepared, target, output))
        process_receipt['dependency_after_stage'] = span(intervals, 'host_dependency_validation_after_stage',
                                                        lambda: dependencies(args, verifier))
        process_receipt['target_verification_after_stage'] = span(intervals, 'original_target_verification_after_stage', lambda:
            scope.verify_target_source(target, prepared['targets'], prepared['target_inventory'], FROZEN_TREE))
        require(summary.get('mock_injection_used') is False and summary.get('full_native_qualified') is False
                and summary.get('production_qualified') is False and summary['selected_image']['selected_config_digest'] == FIXED_IMAGE,
                'actual_scope_result_contract')
        process_receipt.update(status='FRESH_STATIC_PROCESS_CAPTURED',
                               static_stage_complete=summary['static_stage_complete'],
                               stage_diagnostic_status=summary['status'])
    except BaseException as error:
        process_receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        # An absent callback/receipt is retained as absence, never synthesized.
        if not output.exists():
            output.mkdir(mode=0o700, parents=True)
        write_private(output / 'process-receipt.json', process_receipt)


def pair(args):
    args = normalize(args)
    require(not args.output.exists(), 'new_output_required')
    args.output.mkdir(mode=0o700)
    intervals = []
    result = {'schema': 'nico.private.full_static_pair_caller.v1', 'status': 'UNPROVEN',
              'order': ['baseline', 'candidate'], 'single_pair_only': True, 'cache_state': 'UNKNOWN',
              'source_binding': None, 'image_binding': None, 'variants': [], 'intervals': intervals,
              'full_native_qualified': False, 'production_qualified': False, 'assessment_completed': False,
              'compiler_or_runtime_execution_credit': False, 'historical_image_recovered': False,
              'effective_overlay_is_whole_candidate': False,
              'declared_api_wall_seconds': 1030, 'shared_execution_seconds': 1020,
              'independent1030_hardwall_supervisor_present': False,
              'sequential_pair_policy_execution_upper_seconds': 2040, 'job_outer_budget_minutes': 155,
              'parent_cpu_is_analyzer_cpu': False, 'overlapping_intervals_additive': False, 'error': None}
    write_private(args.output / 'pair-receipt.json', result)
    try:
        helper_path = args.operation_source / SOURCE_PATHS['image_helper']
        helper = module_buffer(helper_path, regular(helper_path, digest=HELPER_SHA), 'exact_archive_source_helper')
        result['operation'] = authority(args, helper)
        operation, source_rows, buffers = span(intervals, 'actual_source_binding', lambda: source_bindings(args, helper))
        result['source_binding'] = {'current_git_head': args.expected_operation,
            'effective_fallback_baseline': RECIPE_HEAD,
            'compiler_overlay': {'path': 'nico/assessment_cpp_project_compiler.py', 'sha256': CANDIDATE_COMPILER_SHA},
            'baseline_compiler_sha256': BASELINE_COMPILER_SHA, 'caller_sha256': source_rows['caller']['sha256'],
            'scope_sha256': source_rows['scope']['sha256'], 'prepare_sha256': source_rows['prepare']['sha256'],
            'preparer_sha256': source_rows['preparer']['sha256'], 'exporter_sha256': source_rows['exporter']['sha256'],
            'all_selected_files_actual_git_blob_bound': True, 'actual_operation': operation,
            'effective_overlay_is_whole_candidate': False}
        context = args.output / 'context'
        context.mkdir(mode=0o700)
        for key, name in (('caller', 'cpp_same_image_full_static_diagnostic.py'),
                          ('scope', 'cpp_static_runner_scope.py')):
            path = context / name
            with path.open('xb') as stream:
                stream.write(buffers[key])
            path.chmod(0o400)
            require(regular(path) == buffers[key], 'private_source_copy_binding')
        scope = module_buffer(context / 'cpp_static_runner_scope.py', buffers['scope'], 'exact_scope_for_data_copy')
        prepare = module_buffer(args.operation_source / SOURCE_PATHS['prepare'], buffers['prepare'], 'exact_full_static_prepare')
        verifier = module_buffer(args.operation_source / SOURCE_PATHS['verifier'], buffers['verifier'], 'exact_host_dependency_verifier')
        result['dependency_before_image_and_target'] = span(intervals, 'host_dependency_validation_before_setup',
                                                            lambda: dependencies(args, verifier))
        result['image_binding'] = image_binding(args, helper, prepare, intervals)
        result['target_binding'] = span(intervals, 'full3031_git_checkout_verification_and_data_only_copy', lambda:
            copy_target(args, helper, scope))
        write_private(args.output / 'pair-receipt.json', result)
        # Neither variant shares a NICO import cache or Python module object.
        arguments = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
                     if key != 'worker_settings'}
        for variant in ('baseline', 'candidate'):
            gate = span(intervals, 'host_dependency_validation_before_' + variant + '_process', lambda: dependencies(args, verifier))
            settings_path = context / (variant + '-settings.json')
            settings_ref = write_private(settings_path, {'schema': 'nico.private.full_static_worker_settings.v1',
                'variant': variant, 'parent_pid': os.getpid(), 'arguments': arguments,
                'source_rows': source_rows, 'operation': operation})
            argv = [sys.executable, '-I', '-B', str(context / 'cpp_same_image_full_static_diagnostic.py'),
                    '--worker-settings', str(settings_path)]
            # Only the existing outer155min job bounds a blocked host process.
            # This is deliberately not a newly invented independent1030 supervisor.
            process = span(intervals, 'fresh_' + variant + '_process', lambda:
                subprocess.run(argv, capture_output=True, check=False, env=child_environment()))
            directory = context / 'runs' / variant
            row = {'id': variant, 'directory': str(directory), 'process_exit_code': process.returncode,
                   'settings': settings_ref, 'dependency_before_process': gate,
                   'fresh_cp311_isolated_process_requested': True, 'diagnostic_result': None,
                   'static_stage_receipt': None, 'process_receipt': None, 'stage_receipt_present': False}
            for key, name in (('diagnostic_result', 'diagnostic-result.json'),
                              ('static_stage_receipt', 'static-stage-receipt.json'),
                              ('process_receipt', 'process-receipt.json')):
                if (directory / name).exists():
                    raw = regular(directory / name, MAX_META)
                    row[key] = {'bytes': len(raw), 'sha256': sha(raw)}
            row['stage_receipt_present'] = row['static_stage_receipt'] is not None
            if row['process_receipt'] is not None:
                detail = decode(regular(directory / 'process-receipt.json', MAX_META,
                                        row['process_receipt']['sha256'], row['process_receipt']['bytes']))
                row['stage_invocation_attempted'] = detail.get('stage_invocation_attempted')
                error = detail.get('error')
                if isinstance(error, dict) and type(error.get('type')) is str and type(error.get('message')) is str:
                    row['process_error'] = {'type': error['type'],
                                            'message_sha256': sha(error['message'].encode('utf-8'))}
            for name, raw in (('stdout', process.stdout), ('stderr', process.stderr)):
                require(len(raw) <= MAX_META, 'fresh_process_output_bound')
                with (context / (variant + '-' + name + '.log')).open('xb') as stream:
                    os.chmod(stream.fileno(), 0o600)
                    stream.write(raw)
                row[name] = {'bytes': len(raw), 'sha256': sha(raw)}
            result['variants'].append(row)
            write_private(args.output / 'pair-receipt.json', result)
            # A genuine partial/failed stage returns a captured diagnostic with exit0;
            # infrastructure/dependency failure forbids the next variant.
            require(process.returncode == 0 and row['diagnostic_result'] is not None
                    and row['process_receipt'] is not None, 'fresh_static_process_not_captured')
            diagnostic = decode(regular(directory / 'diagnostic-result.json', MAX_META,
                                        row['diagnostic_result']['sha256'], row['diagnostic_result']['bytes']))
            require(diagnostic.get('schema') == 'nico.private.static_stage_diagnostic_result.v1'
                    and diagnostic.get('mock_injection_used') is False
                    and diagnostic.get('full_native_qualified') is False and diagnostic.get('production_qualified') is False
                    and diagnostic.get('compiled') is False and diagnostic.get('tests_executed') is False
                    and diagnostic['selected_image']['selected_config_digest'] == FIXED_IMAGE
                    and diagnostic['selected_library']['variant'] == variant
                    and diagnostic['selected_library']['actual_operation'] == operation
                    and diagnostic['selected_library']['selected_library_head'] == RECIPE_HEAD
                    and diagnostic['selected_library']['selected_library_tree'] == RECIPE_TREE
                    and diagnostic['selected_library']['selected_compiler']['sha256'] ==
                        (BASELINE_COMPILER_SHA if variant == 'baseline' else CANDIDATE_COMPILER_SHA)
                    and diagnostic['plan']['limits'] == scope.LIMITS and diagnostic['plan']['flags'] == scope.FLAGS,
                    'fresh_variant_source_and_scope_contract')
        result['dependency_after_pair'] = span(intervals, 'host_dependency_validation_after_pair', lambda:
            dependencies(args, verifier))
        image_after = span(intervals, 'loaded_image_config_rootfs_verification_after_pair', lambda: helper.inspection(FIXED_IMAGE))
        require(sha(canonical({'Config': image_after['Config'], 'RootFS': image_after['RootFS']}))
                == result['image_binding']['config_and_rootfs_sha256'], 'loaded_image_changed_after_pair')
        result['image_binding']['config_and_rootfs_verified_after_pair'] = True
        result['status'] = 'FULL_STATIC_PAIR_CAPTURED'
        result['static_stage_pair_complete'] = all(decode(regular(
            Path(row['directory']) / 'diagnostic-result.json', MAX_META))['static_stage_complete'] is True
            for row in result['variants'])
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        write_private(args.output / 'pair-receipt.json', result)
    # Only aggregate scope/status reaches ordinary logs. All raw evidence stays private.
    print(json.dumps({'status': result['status'], 'pair_order': ['baseline', 'candidate'],
                      'static_stage_pair_complete': result['static_stage_pair_complete'],
                      'cache_state': 'UNKNOWN', 'full_native_qualified': False, 'production_qualified': False}))


SAMPLE_INPUTS = {
    'environment': {'file': 'environment.json', 'bytes': 23853193,
        'sha256': '39c5e0dc127ae3d7b425fc1cc9d35f63d2e37b893bbc4a464134e194d995e27b'},
    'primary': {'file': 'primary.json', 'bytes': 9512434,
        'sha256': 'a6fb7909318c253014daec86a32f70455ae77c8a0208cfeaedf2d4ec30f57508'},
    'fallback': {'file': 'fallback.json', 'bytes': 2513517,
        'sha256': '0251cdd017b9c0c4257182651fcdcf2ae102dd931f8f39d8c62f164e5d80577f'},
}
SAMPLE_SOURCE_PATHS = (
    'nico/assessment_cpp_clang_fallback.py',
    'nico/assessment_cpp_project_compiler.py',
    'nico/assessment_cpp_compiler_evidence.py',
    'nico/assessment_cpp_generated_context.py',
    'nico/assessment_cpp_clang_header_evidence.py',
    'nico/assessment_cpp_project_snapshot.py',
)
SAMPLE_INDICES = [0, 58, 154, 186]
SAMPLE_INPUT_RUN = {'run_id': 37659207160, 'attempt': 1,
    'source': 'a5835f2dbb2b671443356de2d0808bdbc731dd6d', 'variant': 'candidate',
    'input_semantics': 'Previously retained fresh environment/primary/fallback bytes; no new primary execution.'}


def sample_inputs(args):
    """Only the three already retained exact native artifacts, in private preparation."""
    directory = args.prepared_inputs / 'host/capacity-sample'
    require(directory.is_dir() and directory.resolve(strict=True) == directory
            and directory.stat().st_mode & 0o077 == 0, 'private_sample_input_directory')
    require({path.name for path in directory.iterdir()} == {row['file'] for row in SAMPLE_INPUTS.values()},
            'sample_input_exact_population')
    inputs, refs = {}, {}
    for key, row in SAMPLE_INPUTS.items():
        raw = regular(directory / row['file'], 48 * 1024 * 1024, row['sha256'], row['bytes'])
        inputs[key] = raw
        refs[key] = {'bytes': len(raw), 'sha256': sha(raw)}
    return inputs, refs


def reconstruct_sample_request(prepared, inputs, sample, *, full_only=False):
    """Use the actual verified f091+89 constructors before any native dispatch."""
    from nico.assessment_cpp_project_compiler import project_compiler_request
    from nico.assessment_cpp_static_environment import environment_request, validate_environment
    from nico.assessment_cpp_project_static import project_static_request, validate_project_static
    from nico.assessment_cpp_clang_fallback import clang_fallback_request
    compiler_request = project_compiler_request(prepared['database'], prepared['targets'], prepared['snapshot'],
                                               extended_budget=True)
    env_request = environment_request(compiler_request, prepared['compiler_raw'], FIXED_IMAGE,
        collect_completed_compiler_failures=True, snapshot=prepared['snapshot'])
    environment = validate_environment(inputs['environment'], env_request)
    require(environment['image_config_digest'] == FIXED_IMAGE, 'sample_environment_fixed_image')
    primary_request = project_static_request(prepared['database'], prepared['targets'], prepared['snapshot'],
        prepared['compiler_raw'], extended_compiler_budget=True, environment=environment,
        header_provenance=True, collect_completed_compiler_failures=True)
    primary = validate_project_static(inputs['primary'], primary_request)
    full_request = clang_fallback_request(primary_request, primary, extended_budget=True,
                                         contention_aware=True, multi_file_diagnostics=True)
    require(len(primary_request['contexts']) == 577 and len(full_request['contexts']) == 576
            and len(primary_request['generated_files']) == 143
            and full_request['limits'] == {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2},
            'sample_full_request_population_and_limits')
    if full_only:
        return primary_request, full_request, {
            'compiler_request_sha256': sha(canonical(compiler_request)),
            'environment_request_sha256': sha(canonical(env_request)),
            'primary_request_sha256': sha(canonical(primary_request)),
            'full_fallback_request_sha256': sha(canonical(full_request)),
            'full_required_fallback_contexts': 576, 'full_request_bound_before_selection': True,
            'no_primary_native_execution': True, 'full_header_source_population': len(full_request['header_source_targets']),
            'full_header_generated_population': len(full_request['header_generated_files'])}
    selected_request, binding = sample.select_sample(full_request, inputs['fallback'],
        expected_fallback_sha256=SAMPLE_INPUTS['fallback']['sha256'], prepared_summary=prepared['summary'])
    require(selected_request['contexts'] == [full_request['contexts'][index] for index in SAMPLE_INDICES]
            and {key: value for key, value in selected_request.items() if key != 'contexts'} ==
                {key: value for key, value in full_request.items() if key != 'contexts'},
            'sample_selection_only_exact_contexts')
    return primary_request, selected_request, binding, {
        'compiler_request_sha256': sha(canonical(compiler_request)),
        'environment_request_sha256': sha(canonical(env_request)),
        'primary_request_sha256': sha(canonical(primary_request)),
        'full_fallback_request_sha256': sha(canonical(full_request)),
        'sample_request_sha256': sha(canonical(selected_request)),
        'full_required_fallback_contexts': 576, 'selected_context_indices': list(SAMPLE_INDICES),
        'selected_context_ids': [row['context_id'] for row in selected_request['contexts']],
        'selected_original_indices': [row['index'] for row in selected_request['contexts']],
        'full_request_bound_before_selection': True, 'no_primary_native_execution': True,
        'full_header_source_population': len(selected_request['header_source_targets']),
        'full_header_generated_population': len(selected_request['header_generated_files'])}


def sample_source_buffers(args):
    # The separately Git-bound module enforces six fixed whole-file pins and
    # exact original PROGRAM definitions. No receipt chooses these source pins.
    buffers = {}
    for name in SAMPLE_SOURCE_PATHS:
        root = args.operation_source if name == 'nico/assessment_cpp_project_compiler.py' else args.recipe_source
        buffers[name] = regular(root / name)
    return buffers


def retain_sample_envelope(output, request, binding, *, pair_envelope=None):
    require(output.absolute() == output.resolve(strict=True) and output.is_dir()
            and output.stat().st_mode & 0o077 == 0, 'private_sample_envelope_directory')
    raw = canonical({'request': request, 'binding': binding} if pair_envelope is None else pair_envelope)
    require(0 < len(raw) <= MAX_META, 'sample_envelope_retention_bound')
    path = output / 'sample-envelope.json'
    with path.open('xb') as stream:
        os.chmod(stream.fileno(), 0o600)
        stream.write(raw)
    reference = {'path': 'sample-envelope.json', 'bytes': len(raw), 'sha256': sha(raw)}
    require(regular(path, MAX_META, reference['sha256'], reference['bytes']) == raw,
            'sample_envelope_retention_readback')
    return raw, reference


def invoke_capacity_sample(args, prepared, target, output, sample, *, pair_arm=None):
    """Same private static boundary, only the four-context collector is dispatched."""
    import base64
    from uuid import uuid4
    from nico.assessment_cpp_full_project import MAX_SOURCE_BYTES, _json
    from nico.assessment_cpp_full_project_execution import (_command, _inputs, ANALYSIS_USER,
        ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM, boundary_valid)
    from nico.assessment_cpp_configuration_probe import SCRATCH_PROGRAM
    from nico.assessment_cpp_project_snapshot import PROJECT_RESTORE_PROGRAM
    from nico.assessment_cpp_project_static import STAGE_EXECUTION_SECONDS, STAGE_WALL_SECONDS
    from nico.assessment_cpp_clang_fallback import PROGRAM, STREAM_LIMIT, validate_clang_fallback
    from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, resources_for, docker_resource_args
    require(output.absolute() == output.resolve() and output.is_relative_to(args.output / 'context/runs')
            and not output.exists(), 'sample_new_private_output')
    output.mkdir(mode=0o700, parents=True)
    start = time.monotonic()
    deadline = start + STAGE_EXECUTION_SECONDS
    name = 'nico-project-static-' + uuid4().hex
    profile = BASELINE_QUALIFICATION_PROFILE
    resources = resources_for(profile)
    created = False
    intervals = []
    result = {'schema': 'nico.private.fallback_capacity_sample_diagnostic.v1', 'status': 'UNPROVEN',
        'phase': 'validate_inputs', 'operations': [], 'intervals': intervals, 'input_artifacts': None,
        'input_operation': dict(SAMPLE_INPUT_RUN), 'request_binding': None, 'program_binding': None,
        'sample_binding': None, 'sample_envelope': None, 'fallback_evidence': None, 'telemetry': None, 'sample_analysis': None,
        'resource_profile': profile, 'limits': {'stage_execution_seconds': 1020, 'stage_wall_seconds': 1030,
            'fallback_wall_seconds': 480, 'fallback_case_seconds': 120,
            'fallback_parallel': 2 if pair_arm is None else pair_arm['envelope']['diagnostic_parallel'],
            'cpus': '4', 'memory_bytes': 12884901888, 'pids': '256', 'tmpfs_bytes': 9663676416},
        'declared_api_wall_seconds': 1030, 'independent1030_hardwall_supervisor_present': False,
        'primary_native_execution': False, 'compiled': False, 'tests_executed': False,
        'full_native_qualified': False, 'production_qualified': False, 'assessment_completed': False,
        'static_collection_complete': False, 'human_approval_created': False, 'cold_timing_credit': False,
        'memory_peak_bytes': None, 'memory_oom_cause_inferred': False, 'cleanup_verified': False,
        'boundary_verified': False, 'scratch_capacity_verified': False, 'error': None}

    def save():
        result['duration_ms'] = int((time.monotonic() - start) * 1000)
        write_private(output / 'sample-diagnostic-result.json', result)

    def checkpoint():
        if time.monotonic() >= deadline:
            raise CallerRejected('sample_shared_stage_deadline')

    def observe(key, argv, *, data=None, maximum=65536, seconds=15, artifact=False, must_succeed=True):
        checkpoint()
        before = time.monotonic()
        observed = _command(argv, checkpoint=lambda: None, input_bytes=data,
            timeout=min(seconds, deadline - before), limit=maximum, native_exit=True)
        raw = observed['output']
        operation = {'id': key, 'invocation_sha256': sha(canonical(argv)),
            'exit_code': observed['exit_code'], 'timed_out': observed['timed_out'],
            'output_truncated': observed['output_truncated'],
            'duration_ms': int((time.monotonic() - before) * 1000),
            'output': None if artifact else base64.b64encode(raw).decode('ascii'),
            'output_sha256': sha(raw), 'output_bytes': len(raw), 'output_artifact': None}
        result['operations'].append(operation)
        save()
        if artifact:
            require(type(raw) is bytes and len(raw) <= maximum, 'sample_artifact_bound')
            digest = sha(raw)
            path = output / ('artifacts/' + key + '-' + digest + '.json')
            path.parent.mkdir(mode=0o700, exist_ok=True)
            with path.open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(raw)
            operation['output_artifact'] = {'path': path.relative_to(output).as_posix(),
                                            'bytes': len(raw), 'sha256': digest}
            save()
        # Actual returned bytes are retained before late-deadline rejection.
        checkpoint()
        if must_succeed:
            require(observed['exit_code'] == 0 and not observed['timed_out'] and not observed['output_truncated'],
                    'sample_static_boundary_operation_failed')
        return observed

    save()
    try:
        checkpoint()
        inputs, refs = span(intervals, 'exact_retained_a583_sample_inputs', lambda: sample_inputs(args))
        result['input_artifacts'] = refs
        if pair_arm is None:
            primary_request, request, binding, request_binding = span(intervals, 'reconstruct_full576_before_selection',
                lambda: reconstruct_sample_request(prepared, inputs, sample))
        else:
            require(getattr(args, 'fallback_parallel_pair', None) is True
                and pair_arm['input_artifacts'] == refs, 'pair_arm_retained_inputs')
            request, binding = sample.check_pair_envelope(pair_arm['envelope'])
            primary_request, request_binding = pair_arm['primary_request'], pair_arm['request_binding']
            require(args.pair_outer_deadline_monotonic - time.monotonic() >= STAGE_EXECUTION_SECONDS + 10,
                    'pair_arm_outer_stage_fit')
            deadline = min(deadline, args.pair_outer_deadline_monotonic - 10)
            result['diagnostic_parallel_pair'] = True
            result['pair_preflight_sha256'] = pair_arm['preflight_sha256']
        envelope_raw, envelope_reference = span(intervals, 'private_sample_envelope_retention',
            lambda: retain_sample_envelope(output, request, binding,
                pair_envelope=None if pair_arm is None else pair_arm['envelope']))
        result.update(request_binding=request_binding, sample_binding=binding, sample_envelope=envelope_reference)
        save()
        if pair_arm is None:
            program, program_binding = span(intervals, 'fixed_whole_source_PROGRAM_telemetry_binding',
                lambda: sample.build_worker_program(PROGRAM, sample_source_buffers(args),
                    expected_sample_sha256=args.expected_sample_sha256))
        else:
            program, program_binding = pair_arm['program'], pair_arm['program_binding']
            require(sha(program.encode()) == program_binding['pair_program_sha256'], 'pair_same_program_bytes')
        result['program_binding'] = program_binding
        files = span(intervals, 'original_static_API_inputs', lambda: _inputs(
            {'targets': prepared['targets'], 'configuration': {'source_byte_limit': MAX_SOURCE_BYTES}}, target, checkpoint))
        checkpoint()
        result['phase'] = 'sandbox'
        metadata = _json(observe('static-image', ['docker', 'image', 'inspect', FIXED_IMAGE])['output'])
        require(isinstance(metadata, list) and len(metadata) == 1 and metadata[0].get('Id') == FIXED_IMAGE,
                'sample_stage_image_mismatch')
        created = True
        observe('static-create', ['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(profile, executable=False), '--log-driver=none',
            '--env=HOME=/work', '--env=TMPDIR=/work', '--entrypoint=sleep', FIXED_IMAGE, str(STAGE_WALL_SECONDS + 5)])
        observe('static-start', ['docker', 'start', name])
        private = _json(observe('static-private', ['docker', 'exec', '--user=' + ANALYSIS_USER, name,
            'python3', '-I', '-S', '-c', ANALYSIS_SETUP_PROGRAM])['output'])
        require(private == {'uid': 1001, 'gid': 1001, 'private': True}, 'sample_stage_private_boundary')
        boundary_before = _json(observe('static-boundary-before', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM])['output'])
        require(boundary_valid(boundary_before, source_required=False, profile=profile, executable=False),
                'sample_stage_boundary_before')
        payload = canonical(files)
        transferred = _json(observe('static-source', ['docker', 'exec', '--user=0:0', '--interactive', name,
            'python3', '-I', '-S', '-c', INPUT_PROGRAM, str(len(payload))], data=payload,
            maximum=4 * 1024 * 1024, seconds=30)['output'])
        require(transferred == prepared['targets'], 'sample_stage_full_source_transfer')
        boundary = _json(observe('static-boundary', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM])['output'])
        require(boundary_valid(boundary, profile=profile, executable=False), 'sample_stage_boundary')
        result['boundary_verified'] = True
        storage = _json(observe('static-storage', ['docker', 'exec', name,
            'python3', '-I', '-S', '-c', SCRATCH_PROGRAM])['output'])
        require(type(storage.get('capacity_bytes')) is int and storage['capacity_bytes'] == resources['tmpfs_bytes']
                and type(storage.get('available_bytes')) is int
                and 64 * 1024 * 1024 <= storage['available_bytes'] <= storage['capacity_bytes'],
                'sample_stage_scratch_capacity')
        result['scratch_capacity_verified'] = True
        result['scratch_capacity_bytes'] = storage['capacity_bytes']
        restore = {'schema': 'nico.cpp-project-restore.v1', 'files': prepared['snapshot']['files'],
                   'file_population_sha256': prepared['snapshot']['file_population_sha256']}
        restored = _json(observe('static-restore', ['docker', 'exec', '--user=' + ANALYSIS_USER,
            '--interactive', name, 'python3', '-I', '-S', '-c', PROJECT_RESTORE_PROGRAM],
            data=canonical(restore), maximum=4 * 1024 * 1024, seconds=30)['output'])
        require(restored == {'files': primary_request['generated_files'],
                            'file_population_sha256': primary_request['snapshot_population_sha256']},
                'sample_stage_full_generated_restore')
        result['phase'] = 'four_context_fallback'
        checkpoint()
        allocation_ms = min(request['limits']['wall_seconds'] * 1000,
            int((deadline - time.monotonic()) * 1000) - (STAGE_WALL_SECONDS - STAGE_EXECUTION_SECONDS) * 1000)
        require(allocation_ms > 0, 'sample_shared_stage_deadline')
        if pair_arm is not None:
            require(allocation_ms == 480000, 'pair_exact_fallback_allocation')
        result['fallback_allocation_ms'] = allocation_ms
        save()
        observed = observe('fallback-capacity-sample', ['docker', 'exec', '--user=' + ANALYSIS_USER,
            '--interactive', name, 'python3', '-I', '-S', '-c', program, str(allocation_ms)],
            data=envelope_raw, maximum=STREAM_LIMIT,
            seconds=request['limits']['wall_seconds'] + 10, artifact=True, must_succeed=False)
        result['fallback_evidence'] = result['operations'][-1]['output_artifact']
        # Retrieve a fixed private sidecar after returned collector bytes are
        # retained, even if they contain a genuine failed/partial native result.
        sidecar_program = ('import os,stat,sys\n'
            'p="/work/analysis/capacity-sample-telemetry.json"\n'
            'fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)\n'
            's=os.fstat(fd)\n'
            'assert stat.S_ISREG(s.st_mode) and s.st_uid==1001 and 0<s.st_size<=8388608\n'
            'with os.fdopen(fd,"rb") as f: b=f.read(8388609)\n'
            'assert len(b)==s.st_size<=8388608\n'
            'sys.stdout.buffer.write(b)\n')
        if pair_arm is not None:
            require(sidecar_program.count('/work/analysis/capacity-sample-telemetry.json') == 1, 'pair_sidecar_program')
            sidecar_program = sidecar_program.replace('/work/analysis/capacity-sample-telemetry.json', sample.SIDECAR)
        telemetry = observe('fallback-capacity-telemetry', ['docker', 'exec', '--user=' + ANALYSIS_USER,
            name, 'python3', '-I', '-S', '-c', sidecar_program], maximum=MAX_META, seconds=10,
            artifact=True, must_succeed=False)
        result['telemetry'] = result['operations'][-1]['output_artifact']
        require(observed['exit_code'] == 0 and not observed['timed_out'] and not observed['output_truncated'],
                'sample_collector_native_output_incomplete')
        proof = span(intervals, 'original_sample_native_validator', lambda:
            validate_clang_fallback(observed['output'], request, primary_request, wall_budget_ms=allocation_ms)
            if pair_arm is None else sample.validate_pair_native(observed['output'], pair_arm['envelope'],
                primary_request, wall_budget_ms=allocation_ms))
        result['sample_analysis'] = {'required_contexts': proof['required_contexts'],
            'attempted_contexts': proof['attempted_contexts'], 'analyzed_contexts': proof['analyzed_contexts'],
            'complete_for_four_context_sample': proof['complete'], 'findings': len(proof['findings']),
            'limitations': proof['limitations'], 'native_evidence_sha256': proof['native_evidence_sha256'],
            'whole576_acceptance_credit': False}
        require(telemetry['exit_code'] == 0 and not telemetry['timed_out'] and not telemetry['output_truncated'],
                'sample_telemetry_sidecar_unavailable')
        telemetry_proof = span(intervals, 'closed_sample_telemetry_validator', lambda:
            sample.validate_sample_telemetry(telemetry['output'], {'request': request, 'binding': binding},
                observed['output'], actual_wall_budget_ms=allocation_ms) if pair_arm is None
            else sample.validate_pair_telemetry(telemetry['output'], pair_arm['envelope'], observed['output'],
                actual_wall_budget_ms=allocation_ms))
        require(isinstance(telemetry_proof, dict), 'sample_telemetry_validation_shape')
        result['telemetry_validation'] = telemetry_proof
        result['status'] = 'FOUR_CONTEXT_DIAGNOSTIC_CAPTURED'
        result['phase'] = 'sample_returned'
        checkpoint()
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if created:
            try:
                peak = _command(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'],
                    checkpoint=lambda: None, timeout=2, limit=1024, native_exit=True)
                if peak['exit_code'] == 0 and not peak['timed_out'] and not peak['output_truncated']:
                    value = int(peak['output'].strip())
                    if 0 <= value <= resources['memory_bytes']:
                        result['memory_peak_bytes'] = value
            except (Exception, KeyboardInterrupt):
                pass
            try:
                removed = _command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                                   timeout=5, limit=4096, native_exit=True)
                result['cleanup_verified'] = removed['exit_code'] == 0 and not removed['timed_out'] and not removed['output_truncated']
            except (Exception, KeyboardInterrupt):
                pass
        if created and not result['cleanup_verified']:
            result['error'] = result['error'] or {'type': 'CallerRejected', 'message': 'sample_stage_cleanup_failed'}
        if result['error']:
            result['status'] = 'UNPROVEN'
        save()
    return result



def invoke_capacity_pair(args, prepared, target, output, parallel_pair):
    """Preflight one complete immutable pair, then dispatch fresh containers in order."""
    from nico.assessment_cpp_clang_fallback import PROGRAM
    from nico.assessment_cpp_project_static import STAGE_EXECUTION_SECONDS, STAGE_WALL_SECONDS
    from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, resources_for
    require(getattr(args, 'fallback_parallel_pair', None) is True and not output.exists()
        and output.is_relative_to(args.output / 'context/runs'), 'pair_new_private_output')
    output.mkdir(mode=0o700, parents=True)
    result = {'schema': 'nico.private.fallback_capacity_sample_diagnostic.v1', 'status': 'UNPROVEN',
        'diagnostic_parallel_pair': True, 'phase': 'pair_preflight', 'arms': [], 'comparison': None,
        'primary_native_execution': False, 'compiled': False, 'tests_executed': False,
        'full_native_qualified': False, 'production_qualified': False, 'assessment_completed': False,
        'static_collection_complete': False, 'full_required_fallback_contexts': 576,
        'selected_context_indices': list(parallel_pair.SELECTED_INDICES), 'cache_state': 'UNKNOWN',
        'stage_seconds_per_arm': 1020, 'fallback_seconds_per_arm': 480, 'case_seconds': 120,
        'job_outer_budget_minutes': 155, 'pair_outer_deadline_monotonic': args.pair_outer_deadline_monotonic,
        'outer_deadline_scope': 'RUNNER_FIRST_SHELL_MONOTONIC_GUARD_PLUS_EXISTING_GHA_JOB_TIMEOUT',
        'single_pair_only': True, 'error': None}
    path = output / 'sample-diagnostic-result.json'
    write_private(path, result)
    try:
        inputs, refs = sample_inputs(args)
        primary_request, full_request, request_binding = reconstruct_sample_request(
            prepared, inputs, parallel_pair.SAMPLE, full_only=True)
        retained = decode(inputs['fallback'])
        require(retained.get('request_sha256') == sha(canonical(full_request))
            and len(retained.get('records', [])) == 576, 'pair_independent_retained_request')
        by_index = {row['index']: row for row in full_request['contexts']}
        expected = []
        witnesses = []
        for index in parallel_pair.SELECTED_INDICES:
            # The hash-pinned historical record independently supplies ID and
            # exact invocation; the reconstructed request supplies original
            # index and immutable dependency obligations. Neither index alone
            # nor a new request independently establishes context identity.
            record, context = retained['records'][index], by_index[index]
            require(type(context['index']) is int and context['index'] == index
                and record['context_id'] == context['context_id']
                and record['invocation'] == context['invocation']
                and record['dropped_arguments'] == context['dropped_arguments'],
                'pair_independent_heavy_context_binding')
            require(type(context.get('analysis_file')) is str
                and (context['analysis_file'].startswith('/work/analysis/generated-baseline/') if index == 114
                     else context['analysis_file'].startswith('/work/source/')), 'pair_heavy_origin_binding')
            identity = parallel_pair.selected_identity(context)
            identity.update(context_id=record['context_id'], invocation_sha256=sha(canonical(record['invocation'])))
            expected.append(identity)
            witnesses.append({'original_index': index, 'context_id': record['context_id'],
                'invocation_sha256': identity['invocation_sha256'], 'analysis_file': context['analysis_file'],
                'retained_record_sha256': sha(canonical(record)),
                'reconstructed_context_sha256': sha(canonical(context))})
        profile = BASELINE_QUALIFICATION_PROFILE
        resources = resources_for(profile)
        execution_identity = dict(parallel_pair.EXECUTION_IDENTITY)
        require(execution_identity['image_digest'] == FIXED_IMAGE
            and execution_identity['isolation'] == profile
            and execution_identity['cpu'] == int(resources['cpus'])
            and execution_identity['memory_bytes'] == resources['memory_bytes']
            and STAGE_EXECUTION_SECONDS == 1020 and STAGE_WALL_SECONDS == 1030,
                'pair_fixed_actual_resource_profile')
        envelopes, binding = parallel_pair.preflight_pair(full_request, inputs['fallback'],
            expected_fallback_sha256=SAMPLE_INPUTS['fallback']['sha256'],
            prepared_summary=prepared['summary'], expected_selected=expected,
            execution_identity=execution_identity)
        program, program_binding = parallel_pair.build_worker_program(PROGRAM, sample_source_buffers(args),
            expected_sample_sha256=args.expected_sample_sha256, expected_pair_sha256=args.expected_pair_sha256)
        require(len(envelopes) == 2 and envelopes[0]['request'] == envelopes[1]['request']
            and envelopes[0]['binding'] == envelopes[1]['binding'], 'pair_complete_preflight_equivalence')
        # Each arm owns its unchanged 1020-second stage. Do not reinterpret
        # that limit as the complete pair allocation or restart outer time.
        cleanup_reserve_seconds = 20
        require(args.pair_outer_deadline_monotonic - time.monotonic() >=
            2 * STAGE_EXECUTION_SECONDS + cleanup_reserve_seconds, 'pair_complete_outer_fit')
        preflight = {'schema': 'nico.private.parallel_pair_complete_preflight.v1',
            'input_artifacts': refs, 'request_binding': request_binding, 'selection': binding,
            'identity_witnesses': witnesses, 'envelopes': envelopes, 'program_binding': program_binding,
            'same_worker_program_sha256': sha(program.encode()), 'stage_seconds_per_arm': 1020,
            'pair_stage_seconds': 2040, 'cleanup_reserve_seconds': cleanup_reserve_seconds,
            'outer_seconds_remaining_at_preflight': args.pair_outer_deadline_monotonic - time.monotonic(),
            'analyzer_allocation_ms_each_arm': 480000, 'full_native_qualified': False,
            'production_qualified': False}
        preflight_ref = write_private(output / 'pair-complete-preflight.json', preflight)
        result.update(phase='pair_arms', preflight=preflight_ref,
            program_binding=program_binding, sample_binding=binding, request_binding=request_binding)
        write_private(path, result)
        for envelope in envelopes:
            parallel = envelope['diagnostic_parallel']
            remaining_arms = 2 - len(result['arms'])
            require(args.pair_outer_deadline_monotonic - time.monotonic() >=
                remaining_arms * STAGE_EXECUTION_SECONDS + cleanup_reserve_seconds,
                'pair_remaining_outer_fit')
            arm_output = output / ('parallel-' + str(parallel))
            arm = {'primary_request': primary_request, 'request_binding': request_binding,
                'envelope': envelope, 'program': program, 'program_binding': program_binding,
                'input_artifacts': refs, 'preflight_sha256': preflight_ref['sha256']}
            diagnostic = invoke_capacity_sample(args, prepared, target, arm_output, parallel_pair, pair_arm=arm)
            result['arms'].append({'diagnostic_parallel': parallel,
                'directory': arm_output.relative_to(output).as_posix(),
                'result': diagnostic})
            write_private(path, result)
            require(diagnostic['status'] == 'FOUR_CONTEXT_DIAGNOSTIC_CAPTURED'
                and diagnostic['cleanup_verified'] is True
                and diagnostic['fallback_allocation_ms'] == 480000, 'pair_arm_capture_or_cleanup_failed')
        raw_outputs = []
        for arm in result['arms']:
            ref = arm['result']['fallback_evidence']
            raw_outputs.append(regular(output / arm['directory'] / ref['path'], 32 * 1024 * 1024,
                ref['sha256'], ref['bytes']))
        result['comparison'] = parallel_pair.compare_pair_outputs(*raw_outputs, envelopes)
        result.update(status='PARALLEL_PAIR_DIAGNOSTIC_CAPTURED', phase='pair_returned')
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        result['status'] = 'UNPROVEN'
    finally:
        write_private(path, result)
    return result


def sample_worker(settings_path, settings_raw, settings):
    require(settings.get('variant') == 'candidate' and settings.get('parent_pid') == os.getppid(),
            'connected_sample_worker')
    args = normalize(argparse.Namespace(**settings['arguments']))
    require(args.fallback_capacity_sample is True or getattr(args, 'fallback_parallel_pair', None) is True,
            'sample_worker_mode')
    args.variant = 'candidate'
    context = args.output / 'context'
    require(context.is_dir() and context.stat().st_mode & 0o077 == 0
            and Path(__file__).parent == context, 'private_sample_worker_context')
    output = context / 'runs/capacity-sample'
    intervals = []
    process_receipt = {'schema': 'nico.private.fallback_capacity_sample_process_receipt.v1',
        'status': 'UNPROVEN', 'variant': 'candidate', 'source_rows': None, 'intervals': intervals,
        'fresh_process_pid': os.getpid(), 'parent_pid': os.getppid(), 'sample_invocation_attempted': False,
        'actual_python': {'version': sys.version, 'isolated': sys.flags.isolated == 1,
                         'no_bytecode': sys.dont_write_bytecode is True},
        'mock_injection_used': False, 'primary_native_execution': False, 'compiled': False,
        'tests_executed': False, 'full_native_qualified': False, 'production_qualified': False,
        'assessment_completed': False, 'error': None}
    early = context / 'capacity-sample-process-receipt.json'
    write_private(early, process_receipt)
    try:
        helper = module_buffer(args.operation_source / SOURCE_PATHS['image_helper'],
            regular(args.operation_source / SOURCE_PATHS['image_helper'], digest=HELPER_SHA), 'exact_sample_image_helper')
        authority(args, helper)
        operation, rows, buffers = span(intervals, 'actual_source_binding', lambda: source_bindings(args, helper))
        require(rows == settings['source_rows'] and operation == settings['operation'], 'sample_worker_source_binding')
        require(regular(context / 'cpp_static_runner_scope.py') == buffers['scope'], 'sample_private_scope_binding')
        process_receipt['source_rows'] = rows
        scope = module_buffer(context / 'cpp_static_runner_scope.py', buffers['scope'], 'exact_sample_scope')
        prepare = module_buffer(args.operation_source / SOURCE_PATHS['prepare'], buffers['prepare'], 'exact_sample_prepare')
        verifier = module_buffer(args.operation_source / SOURCE_PATHS['verifier'], buffers['verifier'], 'exact_sample_verifier')
        sample = module_buffer(args.operation_source / 'scripts/cpp_fallback_capacity_sample.py', buffers['sample'], 'exact_capacity_sample')
        process_receipt['dependency_before_preparation'] = span(intervals, 'dependency_before_sample_preparation',
            lambda: dependencies(args, verifier))
        prepared = span(intervals, 'candidate_full_static_preparation', lambda: prepare.prepare(args, scope))
        target = context / 'target'
        process_receipt['target_verification'] = span(intervals, 'full3031_target_before_sample', lambda:
            scope.verify_target_source(target, prepared['targets'], prepared['target_inventory'], FROZEN_TREE))
        process_receipt['dependency_before_sample'] = span(intervals, 'dependency_before_sample_invocation',
            lambda: dependencies(args, verifier))
        process_receipt['sample_invocation_attempted'] = True
        write_private(early, process_receipt)
        if getattr(args, 'fallback_parallel_pair', None) is True:
            parallel_pair = module_buffer(args.operation_source / 'scripts/cpp_fallback_parallel_pair.py',
                buffers['parallel_pair'], 'exact_parallel_pair')
            diagnostic = span(intervals, 'actual_preflighted_parallel_pair_and_retention', lambda:
                invoke_capacity_pair(args, prepared, target, output, parallel_pair))
        else:
            diagnostic = span(intervals, 'actual_four_context_sample_and_retention', lambda:
                invoke_capacity_sample(args, prepared, target, output, sample))
        process_receipt['dependency_after_sample'] = span(intervals, 'dependency_after_sample_invocation',
            lambda: dependencies(args, verifier))
        process_receipt['target_verification_after_sample'] = span(intervals, 'full3031_target_after_sample', lambda:
            scope.verify_target_source(target, prepared['targets'], prepared['target_inventory'], FROZEN_TREE))
        require(diagnostic['full_native_qualified'] is False and diagnostic['production_qualified'] is False
                and diagnostic['primary_native_execution'] is False and diagnostic['static_collection_complete'] is False,
                'sample_no_full_acceptance_credit')
        process_receipt.update(status='FRESH_SAMPLE_PROCESS_CAPTURED', sample_status=diagnostic['status'])
    except BaseException as error:
        process_receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if not output.exists():
            output.mkdir(mode=0o700, parents=True)
        write_private(output / 'process-receipt.json', process_receipt)


def sample_parent(args):
    args = normalize(args)
    pair_mode = getattr(args, 'fallback_parallel_pair', None) is True
    require((args.fallback_capacity_sample is True or pair_mode) and not args.output.exists(), 'new_sample_parent_output')
    args.output.mkdir(mode=0o700)
    intervals = []
    receipt = {'schema': 'nico.private.fallback_capacity_sample_caller.v1', 'status': 'UNPROVEN',
        'intervals': intervals, 'source_binding': None, 'image_binding': None, 'target_binding': None,
        'sample': None, 'input_operation': dict(SAMPLE_INPUT_RUN), 'selected_context_indices': list(SAMPLE_INDICES),
        'full_required_fallback_contexts': 576, 'cache_state': 'UNKNOWN', 'single_sample_only': True,
        'job_outer_budget_minutes': 155, 'declared_api_wall_seconds': 1030, 'shared_execution_seconds': 1020,
        'independent1030_hardwall_supervisor_present': False, 'primary_native_execution': False,
        'parent_cpu_is_analyzer_cpu': False, 'overlapping_intervals_additive': False,
        'full_native_qualified': False, 'production_qualified': False, 'assessment_completed': False,
        'static_collection_complete': False, 'historical_image_recovered': False, 'error': None}
    if pair_mode:
        receipt.update(diagnostic_parallel_pair=True, selected_context_indices=[58, 114, 153, 154],
            single_sample_only=False, pair_analyzer_parallelism=[2, 4], stage_execution_seconds_per_arm=1020,
            pair_outer_deadline_monotonic=args.pair_outer_deadline_monotonic)
    write_private(args.output / 'sample-caller-receipt.json', receipt)
    try:
        helper_path = args.operation_source / SOURCE_PATHS['image_helper']
        helper = module_buffer(helper_path, regular(helper_path, digest=HELPER_SHA), 'exact_sample_parent_helper')
        operation = authority(args, helper)
        receipt['operation'] = operation
        operation, rows, buffers = span(intervals, 'actual_source_binding', lambda: source_bindings(args, helper))
        receipt['source_binding'] = {'current_git_head': args.expected_operation, 'actual_operation': operation,
            'effective_fallback_baseline': RECIPE_HEAD, 'effective_recipe_tree': RECIPE_TREE,
            'compiler_overlay': {'path': 'nico/assessment_cpp_project_compiler.py', 'sha256': CANDIDATE_COMPILER_SHA},
            'effective_overlay_is_whole_candidate': False, 'caller_sha256': rows['caller']['sha256'],
            'scope_sha256': rows['scope']['sha256'], 'sample_sha256': rows['sample']['sha256'],
            'prepare_sha256': rows['prepare']['sha256'], 'preparer_sha256': rows['preparer']['sha256'],
            'exporter_sha256': rows['exporter']['sha256'], 'all_selected_files_actual_git_blob_bound': True}
        if pair_mode:
            receipt['source_binding']['parallel_pair_sha256'] = rows['parallel_pair']['sha256']
        context = args.output / 'context'
        context.mkdir(mode=0o700)
        for key, name in (('caller', 'cpp_same_image_full_static_diagnostic.py'), ('scope', 'cpp_static_runner_scope.py')):
            path = context / name
            with path.open('xb') as stream:
                stream.write(buffers[key])
            path.chmod(0o400)
            require(regular(path) == buffers[key], 'sample_private_source_copy_binding')
        scope = module_buffer(context / 'cpp_static_runner_scope.py', buffers['scope'], 'exact_sample_parent_scope')
        prepare = module_buffer(args.operation_source / SOURCE_PATHS['prepare'], buffers['prepare'], 'exact_sample_parent_prepare')
        verifier = module_buffer(args.operation_source / SOURCE_PATHS['verifier'], buffers['verifier'], 'exact_sample_parent_verifier')
        receipt['input_artifacts'] = span(intervals, 'sample_inputs_before_image_load', lambda: sample_inputs(args))[1]
        receipt['dependency_before_setup'] = span(intervals, 'dependency_before_sample_setup', lambda: dependencies(args, verifier))
        receipt['image_binding'] = image_binding(args, helper, prepare, intervals)
        # Reused helper returns pair-specific metadata. A one-sample route must
        # not suggest that two new variants ran or that cache equivalence holds.
        receipt['image_binding'].pop('same_selected_image_for_both_variants', None)
        receipt['image_binding']['single_verified_selected_image_for_sample'] = True
        if pair_mode:
            receipt['image_binding']['same_selected_image_for_both_diagnostic_arms'] = True
        receipt['target_binding'] = span(intervals, 'full3031_git_checkout_verification_and_data_only_copy', lambda:
            copy_target(args, helper, scope))
        receipt['dependency_before_process'] = span(intervals, 'dependency_before_fresh_sample_process', lambda: dependencies(args, verifier))
        arguments = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
                     if key != 'worker_settings'}
        settings_path = context / 'capacity-sample-settings.json'
        settings = write_private(settings_path, {'schema': 'nico.private.fallback_capacity_sample_worker_settings.v1',
            'variant': 'candidate', 'parent_pid': os.getpid(), 'arguments': arguments,
            'source_rows': rows, 'operation': operation})
        write_private(args.output / 'sample-caller-receipt.json', receipt)
        argv = [sys.executable, '-I', '-B', str(context / 'cpp_same_image_full_static_diagnostic.py'),
                '--worker-settings', str(settings_path)]
        child_timeout = None
        if pair_mode:
            child_timeout = args.pair_outer_deadline_monotonic - time.monotonic() - 60
            require(child_timeout > 0, 'pair_parent_remaining_outer_budget')
        process = span(intervals, 'fresh_candidate_sample_process', lambda:
            subprocess.run(argv, capture_output=True, check=False, env=child_environment(), timeout=child_timeout))
        directory = context / 'runs/capacity-sample'
        row = {'id': 'capacity-sample', 'directory': str(directory), 'process_exit_code': process.returncode,
            'settings': settings, 'diagnostic_result': None, 'process_receipt': None,
            'fresh_cp311_isolated_process_requested': True}
        for key, name in (('diagnostic_result', 'sample-diagnostic-result.json'), ('process_receipt', 'process-receipt.json')):
            if (directory / name).exists():
                raw = regular(directory / name, MAX_META)
                row[key] = {'bytes': len(raw), 'sha256': sha(raw)}
        for name, raw in (('stdout', process.stdout), ('stderr', process.stderr)):
            require(len(raw) <= MAX_META, 'sample_process_output_bound')
            with (context / ('capacity-sample-' + name + '.log')).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(raw)
            row[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        receipt['sample'] = row
        write_private(args.output / 'sample-caller-receipt.json', receipt)
        require(process.returncode == 0 and row['diagnostic_result'] is not None and row['process_receipt'] is not None,
                'fresh_sample_process_not_captured')
        detail = decode(regular(directory / 'sample-diagnostic-result.json', MAX_META,
            row['diagnostic_result']['sha256'], row['diagnostic_result']['bytes']))
        require(detail['schema'] == 'nico.private.fallback_capacity_sample_diagnostic.v1'
                and detail['primary_native_execution'] is False and detail['full_native_qualified'] is False
                and detail['production_qualified'] is False and detail['static_collection_complete'] is False,
                'sample_diagnostic_closed_scope')
        receipt['sample_status'] = detail['status']
        receipt['dependency_after_sample'] = span(intervals, 'dependency_after_fresh_sample_process', lambda: dependencies(args, verifier))
        image_after = span(intervals, 'loaded_image_config_rootfs_verification_after_sample', lambda: helper.inspection(FIXED_IMAGE))
        require(sha(canonical({'Config': image_after['Config'], 'RootFS': image_after['RootFS']})) ==
                receipt['image_binding']['config_and_rootfs_sha256'], 'loaded_image_changed_after_sample')
        receipt['image_binding']['config_and_rootfs_verified_after_sample'] = True
        receipt['status'] = 'SAMPLE_PROCESS_AND_RETAINED_RESULT_CAPTURED'
    except BaseException as error:
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        write_private(args.output / 'sample-caller-receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'sample_status': receipt['sample_status'],
        'selected_context_indices': receipt['selected_context_indices'], 'full_native_qualified': False, 'production_qualified': False}))


def main():
    os.umask(0o077)
    for name in CREDENTIAL_NAMES:
        os.environ.pop(name, None)
    args = entry_arguments()
    if args.worker_settings is not None:
        require(all(value is None for key, value in vars(args).items() if key != 'worker_settings'),
                'worker_cli_is_exclusive')
        worker(path_value(args.worker_settings))
    elif args.fallback_capacity_sample is True or args.fallback_parallel_pair is True:
        sample_parent(args)
    else:
        pair(args)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"status":"UNPROVEN","full_native_qualified":false,"production_qualified":false}')
        sys.exit(1)
