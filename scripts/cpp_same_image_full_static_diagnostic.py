"""Private connected baseline-first full-static pair on one verified loaded image.

The normal job prepares retained inputs and produces the dependency proof before
this caller. This caller has no provider client, dependency installer, image
builder, cache reset, target compiler/runtime entrypoint, or qualification gate.
Every stage call is an unchanged selected-scope invoke in a fresh CP311 process.
"""
from __future__ import annotations

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
VERIFIER_SHA = 'f225feeff1da8928d8d9e936a01e56c43cabad63193e2502551976bb0c657e04'
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
    module = types.ModuleType(label)
    module.__file__ = str(path)
    source = raw.decode('utf-8')
    linecache.cache[str(path)] = (len(raw), None, source.splitlines(True), str(path))
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


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
    expected = {'caller': args.expected_caller_sha256, 'scope': args.expected_scope_sha256,
                'prepare': args.expected_prepare_sha256, 'preparer': args.expected_preparer_sha256,
                'exporter': args.expected_exporter_sha256, 'verifier': VERIFIER_SHA,
                'wheel_manifest': WHEEL_MANIFEST_SHA, 'image_helper': HELPER_SHA}
    rows, buffers = {}, {}
    for key, name in SOURCE_PATHS.items():
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
    checkout = helper.checked_git_source(args.target_checkout, FROZEN_HEAD, FROZEN_TREE, 3031)
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
    return parser.parse_args()


def normalize(args):
    for name in ('operation_source', 'recipe_source', 'prepared_inputs', 'target_checkout',
                 'output', 'dependency_proof'):
        require(getattr(args, name, None) is not None, 'required_cli_argument')
        setattr(args, name, path_value(getattr(args, name)))
    for name in ('expected_caller_sha256', 'expected_scope_sha256', 'expected_prepare_sha256',
                 'expected_preparer_sha256', 'expected_exporter_sha256', 'expected_proof_sha256'):
        hexadecimal(getattr(args, name, None), 64, 'expected_digest_argument')
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


def main():
    os.umask(0o077)
    for name in CREDENTIAL_NAMES:
        os.environ.pop(name, None)
    args = entry_arguments()
    if args.worker_settings is not None:
        require(all(value is None for key, value in vars(args).items() if key != 'worker_settings'),
                'worker_cli_is_exclusive')
        worker(path_value(args.worker_settings))
    else:
        pair(args)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('{"status":"UNPROVEN","full_native_qualified":false,"production_qualified":false}')
        sys.exit(1)
