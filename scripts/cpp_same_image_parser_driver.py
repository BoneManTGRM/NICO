"""Root-owned host orchestration for one retrieved-image AST parser diagnostic."""
import argparse
import hashlib
import json
import os

import importlib.machinery, importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import types

MAX_RECEIPT = 8 * 1024 * 1024
BUILDER_SHA = '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344'
WORKER_SHA = '9a12d14dd5ab388bc1f007b54acb343f755870c2ffc338ca2f617a0d8422e3b8'
REPO = 'BoneManTGRM/NICO'
BRANCH = 'refs/heads/diagnostic/v17-pinned-image-20261007'
WORKFLOW = '.github/workflows/cpp-same-image-parser-diagnostic.yml'
OPERATIONS = []



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

def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def command(argv, timeout=30, check=True, maximum=1024 * 1024):
    start = time.perf_counter_ns()
    try:
        value = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        OPERATIONS.append({'argv': argv, 'wall_ms': (time.perf_counter_ns() - start) / 1e6,
                           'timeout_seconds': timeout, 'timed_out': True})
        raise
    require(len(value.stdout) + len(value.stderr) <= maximum, 'bounded_operation_output')
    OPERATIONS.append({'argv': argv, 'wall_ms': (time.perf_counter_ns() - start) / 1e6,
                       'timeout_seconds': timeout, 'timed_out': False, 'exit_code': value.returncode,
                       'stdout_sha256': sha(value.stdout), 'stderr_sha256': sha(value.stderr),
                       'stderr_tail': value.stderr[-8192:].decode('utf-8', 'backslashreplace'),
                       'stderr_tail_truncated': len(value.stderr) > 8192})
    require(not check or value.returncode == 0, 'operation_failed:' + argv[0])
    return value


def write(path, value):
    raw = canonical(value) + b'\n'
    require(len(raw) <= MAX_RECEIPT, 'compact_receipt_limit')
    with path.open('wb') as stream:
        stream.write(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation-source', required=True, type=Path)
    parser.add_argument('--recipe-source', required=True, type=Path)
    parser.add_argument('--prepared-inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    for key in ('operation_source', 'recipe_source', 'prepared_inputs', 'output'):
        path = getattr(args, key).absolute()
        require(path == path.resolve() and ',' not in str(path), 'canonical_driver_path')
        setattr(args, key, path)
    require(args.prepared_inputs.is_dir() and args.prepared_inputs.stat().st_mode & 0o077 == 0,
            'private_prepared_host_directory')
    args.image_artifact = args.prepared_inputs / 'host/image'
    args.baseline_artifact = args.prepared_inputs / 'runtime/inputs'
    runtime_source = args.prepared_inputs / 'runtime/source'
    # Normal job credentials are never inherited by tool subprocesses or copied.
    for key in ('GITHUB_TOKEN', 'GH_TOKEN', 'ACTIONS_RUNTIME_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN',
                'ACTIONS_ID_TOKEN_REQUEST_URL'):
        os.environ.pop(key, None)
    require(not args.output.exists(), 'new_output_required')
    args.output.mkdir(mode=0o700)
    result = {'schema': 'nico.c34.same_image_parser_outer_receipt.v1', 'status': 'UNPROVEN',
              'production_qualified': False, 'historical_image_recovered': False,
              'target_execution': False, 'analyzer_execution': False, 'registry_push': False,
              'release_or_merge': False, 'new_image_build': False, 'operations': OPERATIONS,
              'historical001f_diagnosis_reused': True, 'cleanup_verified': False, 'error': None}
    create_attempted = False
    name = None
    write(args.output / 'outer-receipt.json', result)
    try:
        # Execute the already reviewed helper's verified bytes, not a re-read or replacement checker.
        helper_path = args.operation_source / 'scripts/cpp_diagnostic_image_rebuild.py'
        helper_raw = helper_path.read_bytes()
        require(len(helper_raw) == 30882 and sha(helper_raw) == BUILDER_SHA, 'exact_image_helper_hash')
        helper = _import_verified_buffer(helper_path, helper_raw, 'hash_bound_original_image_helper')
        head = os.environ.get('GITHUB_SHA', '')
        require(os.environ.get('GITHUB_REPOSITORY') == REPO
                and os.environ.get('GITHUB_REPOSITORY_ID') == '1282576027'
                and os.environ.get('GITHUB_REF') == BRANCH and os.environ.get('GITHUB_EVENT_NAME') == 'push'
                and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
                and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
                and os.environ.get('GITHUB_JOB') == 'same-image-parser-diagnostic'
                and re.fullmatch(r'[0-9a-f]{40}', head) is not None
                and helper.git_value(args.operation_source, 'HEAD') == head
                and os.environ.get('GITHUB_WORKFLOW_SHA') == head
                and os.environ.get('GITHUB_WORKFLOW_REF') == REPO + '/' + WORKFLOW + '@' + BRANCH,
                'operation_authority_identity')
        command(['git', '-C', str(args.operation_source), 'diff-index', '--quiet', 'HEAD', '--'])
        result['operation'] = {'head': head, 'tree': helper.git_value(args.operation_source, 'HEAD^{tree}'),
            'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': 1, 'runner': os.environ.get('RUNNER_NAME'),
            'driver_sha256': sha(Path(__file__).read_bytes()), 'archive_helper_sha256': BUILDER_SHA,
            'host_python': sys.version}
        pins_raw = helper.regular(args.prepared_inputs / 'host/pins.json', MAX_RECEIPT)
        pins = helper.decode(pins_raw)
        IMAGE = pins['image']['image_config_id']
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', IMAGE) is not None, 'derived_image_identity')
        result['pins_sha256'] = sha(pins_raw)
        preparation_raw = helper.regular(args.prepared_inputs / 'host/preparation.json', MAX_RECEIPT)
        preparation = helper.decode(preparation_raw)
        adapter_path = args.operation_source / 'scripts/cpp_private_diagnostic_inputs.py'
        require(preparation['status'] == 'PRIVATE_RETAINED_INPUTS_PREPARED'
                and preparation['adapter_sha256'] == sha(helper.regular(adapter_path, 64 * 1024 * 1024))
                and preparation['source']['commit'] == head
                and preparation['source']['tree'] == helper.git_value(args.operation_source, 'HEAD^{tree}')
                and preparation['public_metadata_export'] is False
                and preparation['new_artifact_upload'] is False
                and preparation['target_or_native_execution'] is False
                and preparation['actual_observed_scratch_peak_bytes'] <= 6 * 1024 * 1024 * 1024,
                'actual_private_preparation_binding')
        result['private_preparation_sha256'] = sha(preparation_raw)
        recipe = helper.checked_git_source(args.recipe_source, pins['recipe_source']['commit'],
                                           pins['recipe_source']['tree'], 3305)
        result['unchanged_recipe_source'] = recipe
        for key in ('baseline', 'source_path'):
            row = pins['sources'][key]
            original = helper.regular(args.recipe_source / row['original_recipe_path'], 64 * 1024 * 1024)
            packaged = helper.regular(args.operation_source / row['path'], 64 * 1024 * 1024)
            require(original == packaged and len(original) == row['bytes'] and sha(original) == row['sha256']
                    and hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()
                    == row['git_blob'], 'baseline_source_copy_binding')
        for key in ('candidate', 'fixtures'):
            row = pins['sources'][key]
            raw = helper.regular(args.operation_source / row['path'], 64 * 1024 * 1024)
            require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'diagnostic_source_binding')
        candidate = pins['sources']['candidate']
        actual_blob = command(['git', '-C', str(args.operation_source), 'rev-parse', 'HEAD:' + candidate['path']])
        require(actual_blob.stdout.decode().strip() == candidate['git_blob'], 'actual_candidate_git_blob')
        program = args.operation_source / 'scripts/cpp_same_image_dependency_diagnostic.py'
        require(sha(helper.regular(program, 64 * 1024 * 1024)) == pins['diagnostic_script_sha256'],
                'portable_diagnostic_source_binding')
        runtime_pins_raw = helper.regular(runtime_source / 'scripts/cpp-parser-diagnostic-inputs/runtime-pins.json', MAX_RECEIPT)
        runtime_pins = helper.decode(runtime_pins_raw)
        require(sha(runtime_pins_raw) == preparation['runtime_pin_sha256']
                and runtime_pins['sources'] == pins['sources'] and runtime_pins['functions'] == pins['functions']
                and runtime_pins['frozen_target'] == pins['frozen_target']
                and runtime_pins['diagnostic_script_sha256'] == pins['diagnostic_script_sha256']
                and runtime_pins['image'] == {key: pins['image'][key] for key in ('image_config_id', 'tar_sha256')},
                'minimal_runtime_manifest_binding')
        result['diagnostic_frozen_target'] = {key: pins['frozen_target'][key]
                                             for key in ('repository', 'commit', 'tree', 'target_population_sha256')}
        for row in pins['sources'].values():
            raw = helper.regular(runtime_source / row['path'], 64 * 1024 * 1024)
            require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'mounted_runtime_source_binding')
        require(helper.regular(runtime_source / 'scripts/cpp_same_image_dependency_diagnostic.py',
                               64 * 1024 * 1024) == helper.regular(program, 64 * 1024 * 1024),
                'mounted_unchanged_complete_original_worker')
        wrapper = args.operation_source / 'scripts/cpp_private_parser_worker.py'
        wrapper_raw = helper.regular(wrapper, 64 * 1024 * 1024)
        require(sha(wrapper_raw) == WORKER_SHA and helper.regular(runtime_source /
                'scripts/cpp_private_parser_worker.py', 64 * 1024 * 1024) == wrapper_raw,
                'mounted_reviewed_loading_extension')
        retrieval_raw = helper.regular(args.prepared_inputs / 'host/retrieval/receipt.json', MAX_RECEIPT)
        retrieval = helper.decode(retrieval_raw)
        require(sha(retrieval_raw) == pins['image']['prior_retrieval_receipt_sha256']
                and retrieval['status'] == 'DIAGNOSTIC_IMAGE_RETRIEVED_COMPLETE_IDENTITY_VERIFIED'
                and retrieval['build_receipt_sha256'] == pins['image']['build_receipt_sha256']
                and retrieval['complete_image_archive_verified'] is True
                and retrieval['supported_storage_retrieval_verified'] is True
                and retrieval['operation']['workflow_head'] == pins['image']['build_head']
                and retrieval['operation']['run_id'] == str(pins['image']['run_id'])
                and retrieval['operation']['run_attempt'] == 1, 'actual_independent_prior_retrieval')
        before_raw = helper.regular(args.image_artifact / 'receipt.json', MAX_RECEIPT)
        require(sha(before_raw) == pins['image']['build_receipt_sha256'], 'independent_build_receipt_anchor')
        before = helper.decode(before_raw)
        require(before['status'] == 'DIAGNOSTIC_IMAGE_SAVED_UNRETRIEVED'
                and before['production_qualified'] is False and before['target_execution'] is False
                and before['operation']['workflow_head'] == pins['image']['build_head']
                and before['operation']['run_id'] == str(pins['image']['run_id'])
                and before['operation']['run_attempt'] == 1
                and before['operation']['helper_sha256'] == BUILDER_SHA
                and before['recipe_source']['commit'] == pins['recipe_source']['commit']
                and before['recipe_source']['tree'] == pins['recipe_source']['tree']
                and before['image_config_id'] == pins['image']['image_config_id'] == IMAGE,
                'actual_image_build_receipt_binding')
        require(before['image_inspection']['RootFS']['Layers'] == pins['image']['expected_layers'],
                'independent_ordered_image_layers')
        # Retain the exact raw producer receipt for root's tool/provision inspection.
        (args.output / 'image-build-receipt.json').write_bytes(before_raw)
        result['build_receipt_sha256'] = sha(before_raw)
        result['prior_verified_retrieval_receipt_sha256'] = pins['image']['prior_retrieval_receipt_sha256']
        start = time.perf_counter_ns()
        proof = helper.archive_proof(args.image_artifact / 'image.tar', IMAGE,
                                     before['image_inspection']['RootFS']['Layers'])
        result['full_archive_verification_wall_ms'] = (time.perf_counter_ns() - start) / 1e6
        require(proof == before['archive_proof'] and proof['archive']['sha256'] == pins['image']['tar_sha256']
                and proof['archive']['bytes'] == pins['image']['tar_bytes'], 'actual_full_image_archive_binding')
        result['archive_proof'] = proof
        require(proof == retrieval['archive_proof'] == preparation['complete_archive_proof'],
                'private_preparation_and_independent_archive_binding')
        result['provider_artifact_zip_reverified_by_private_transport'] = all(
            row['provider_raw_zip_verified'] is True for row in preparation['downloads'].values())
        require(result['provider_artifact_zip_reverified_by_private_transport'], 'private_raw_zip_verification')
        write(args.output / 'outer-receipt.json', result)
        reserve = preparation['preflights'][-1]['separately_supplied_load_store_reserve_bytes']
        require(type(reserve) is int and reserve > 0 and shutil.disk_usage(args.prepared_inputs).free >= reserve,
                'current_host_load_store_reserve_guard')
        result['image_load_disk_preflight'] = {'host_free_disk_bytes': shutil.disk_usage(args.prepared_inputs).free,
            'separately_supplied_reserve_bytes': reserve, 'actual_load_store_bytes_known': False,
            'container_tmpfs_used_as_host_allowance': False}
        absent = command(['docker', 'image', 'inspect', IMAGE], check=False)
        require(absent.returncode != 0 and b'No such image' in absent.stderr,
                'fresh_runner_image_preexisting_or_daemon_unavailable')
        loaded = command(['docker', 'image', 'load', '--input', str(args.image_artifact / 'image.tar')], timeout=90)
        observed = helper.inspection(IMAGE)
        require(observed['RootFS']['Layers'] == before['image_inspection']['RootFS']['Layers']
                and observed['Config'] == before['image_inspection']['Config'], 'loaded_complete_image_identity')
        result['loaded_image_inspection'] = observed
        result['host_free_disk_after_load_bytes'] = shutil.disk_usage(args.prepared_inputs).free
        result['load_stdout_sha256'] = sha(loaded.stdout)
        identity = {'image_config_id': IMAGE, 'image_archive_sha256': proof['archive']['sha256'],
                    'complete_archive_verified': True, 'network': 'none', 'read_only': True,
                    'user': '1000:1000'}
        identity_dir = args.output / 'identity'
        identity_dir.mkdir(mode=0o755)
        os.chmod(identity_dir, 0o755)
        write(identity_dir / 'container-identity.json', identity)
        os.chmod(identity_dir / 'container-identity.json', 0o644)
        name = 'nico-parser-' + os.environ['GITHUB_RUN_ID'] + '-1'
        argv = ['docker', 'create', '--name=' + name, '--network=none', '--read-only', '--user=1000:1000',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--cpus=4', '--memory=12g',
                '--memory-swap=12g', '--pids-limit=256',
                '--tmpfs=/work:rw,nosuid,nodev,noexec,size=9663676416,mode=1777', '--log-driver=none',
                '--env=HOME=/work', '--env=TMPDIR=/work',
                '--mount=type=bind,src=' + str(runtime_source) + ',dst=/diag,readonly',
                '--mount=type=bind,src=' + str(args.baseline_artifact) + ',dst=/evidence,readonly',
                '--mount=type=bind,src=' + str(identity_dir) + ',dst=/identity,readonly',
                '--entrypoint=python3', IMAGE, '-I', '-S', '-B',
                '/diag/scripts/cpp_private_parser_worker.py', '--inputs', '/evidence',
                '--pins', '/diag/scripts/cpp-parser-diagnostic-inputs/runtime-pins.json']
        result['container_create_argv'] = argv
        create_attempted = True
        result['container_create_attempted'] = True
        result['container_create_completed'] = False
        command(argv)
        result['container_create_completed'] = True
        metadata = helper.decode(command(['docker', 'container', 'inspect', name]).stdout)
        require(isinstance(metadata, list) and len(metadata) == 1, 'container_inspection_population')
        meta = metadata[0]; host = meta['HostConfig']
        require(meta['Image'] == IMAGE and meta['Config']['User'] == '1000:1000'
                and meta['Config']['Entrypoint'] == ['python3'] and host['NetworkMode'] == 'none'
                and host['ReadonlyRootfs'] is True and host['NanoCpus'] == 4000000000
                and host['Memory'] == host['MemorySwap'] == 12884901888 and host['PidsLimit'] == 256
                and host['Tmpfs'] == {'/work': 'rw,nosuid,nodev,noexec,size=9663676416,mode=1777'}
                and host['CapDrop'] == ['ALL'] and 'no-new-privileges' in host['SecurityOpt']
                and {mount['Destination']: (mount['Source'], mount['RW']) for mount in meta['Mounts']
                     if mount['Type'] == 'bind'} == {
                         '/diag': (str(runtime_source), False),
                         '/evidence': (str(args.baseline_artifact), False),
                         '/identity': (str(identity_dir), False)}, 'actual_fixed_container_binding')
        result['container_before'] = meta
        write(args.output / 'outer-receipt.json', result)
        measured = command(['docker', 'start', '--attach', name], timeout=480,
                           maximum=MAX_RECEIPT, check=False)
        (args.output / 'container-diagnostic.json').write_bytes(measured.stdout)
        (args.output / 'container-stderr.txt').write_bytes(measured.stderr)
        require(len(measured.stdout) <= MAX_RECEIPT and not measured.stderr, 'bounded_container_receipt')
        compact = helper.decode(measured.stdout)
        require(measured.returncode == 0 and compact['status'] == 'SAME_IMAGE_AST_HELPERS_VERIFIED'
                and compact['production_qualified'] is False and compact['target_execution'] is False
                and compact['native_execution'] is False and compact['pins_sha256'] == sha(runtime_pins_raw)
                and compact['diagnostic_container_executed'] is True
                and compact['input_provenance']['nonempty_dependency_lists'] == 576
                and compact['fixture_pairs'] == 41 and compact['forbidden_events'] == [],
                'actual_container_diagnostic_receipt')
        state = helper.decode(command(['docker', 'container', 'inspect', name]).stdout)[0]['State']
        require(state['Running'] is False and state['ExitCode'] == 0 and state['OOMKilled'] is False,
                'container_terminal_state')
        result.update(status='RETRIEVED_IMAGE_AST_PARSER_DIAGNOSTIC_VERIFIED', container_terminal=state,
                      container_receipt_sha256=sha(measured.stdout), full_native_qualified=False,
                      setup_or_analyzer_throughput_improvement_proved=False)
    except BaseException as error:
        result.update(status='UNPROVEN', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if create_attempted:
            try:
                cleanup = command(['docker', 'rm', '--force', name], timeout=5, check=False)
                result['cleanup_verified'] = cleanup.returncode == 0
            except BaseException as error:
                result['cleanup_error'] = {'type': type(error).__name__, 'message': str(error)}
            if result['cleanup_verified'] is not True:
                result['status'] = 'UNPROVEN'
        write(args.output / 'outer-receipt.json', result)
    require(result['cleanup_verified'], 'diagnostic_cleanup_failed')
    # Only aggregate findings leave private host scratch through the normal log.
    print(json.dumps({'status': result['status'], 'production_qualified': False, 'target_execution': False,
                      'retained_dependency_lists': 576, 'fixture_pairs': 41,
                      'timings': compact['timings'], 'full_native_qualified': False,
                      'setup_or_analyzer_throughput_improvement_proved': False}))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        # Raw failure details remain in the private host receipt, never in logs.
        print('{"status":"UNPROVEN","production_qualified":false,"target_execution":false}')
        sys.exit(1)
