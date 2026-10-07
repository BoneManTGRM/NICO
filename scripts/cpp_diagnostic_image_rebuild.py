"""Build/retain/retrieve trusted diagnostic tools. Never qualify or run a target."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import signal
import stat
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
MAX_ARCHIVE = 3 * 1024 * 1024 * 1024
MAX_META = 1024 * 1024
MAX_LOG = 8 * 1024 * 1024
MAX_MEMBERS = 4096
SAVE_SECONDS = 45
LOAD_SECONDS = 90
REPO = 'BoneManTGRM/NICO'
BRANCH = 'refs/heads/diagnostic/v17-pinned-image-20261007'
WORKFLOW = '.github/workflows/cpp-diagnostic-image-rebuild.yml'
HISTORICAL = 'sha256:9c915795728a59ee5269d9ac3ddcd15a2103ceacad87a80cebc0aa9bd4d4fdaf'
HEX = re.compile(r'[0-9a-f]{64}')


def require(ok, code):
    if not ok:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def regular(path, maximum=MAX_META):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and not path.is_symlink(), 'regular_path_required')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'file_size_or_type')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) and len(raw) == before.st_size, 'file_changed')
    return raw


def file_digest(path, maximum=MAX_ARCHIVE):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and not path.is_symlink(), 'archive_path')
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, 'archive_size')
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            require(total <= maximum, 'archive_size')
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) and total == before.st_size, 'archive_changed')
    return {'name': path.name, 'bytes': total, 'sha256': digest.hexdigest()}


def safe_name(name):
    require(isinstance(name, str) and 0 < len(name) <= 240 and not name.startswith('/')
            and PurePosixPath(name).as_posix() == name
            and all(part not in {'', '.', '..'} for part in name.split('/'))
            and re.fullmatch(r'[A-Za-z0-9._/-]+', name) is not None, 'unsafe_archive_path')
    return name


def source_name(name):
    # Pinned Git trees contain Next.js route brackets and C++ '+' filenames.
    # This is a source-checkout path contract, separate from Docker archives.
    require(isinstance(name, str) and 0 < len(name) <= 240 and not name.startswith('/')
            and PurePosixPath(name).as_posix() == name
            and all(part not in {'', '.', '..'} for part in name.split('/'))
            and re.fullmatch(r'[A-Za-z0-9._/+\[\]-]+', name) is not None, 'unsafe_source_path')
    return name


def archive_proof(path, expected_config, expected_diffids=None):
    """Inert bounded metadata and every-layer verification; no extraction/load."""
    fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    before = Path(path).stat()
    archive = file_digest(path)
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', expected_config) is not None, 'config_id')
    members = {}
    with tarfile.open(path, 'r:') as bundle:
        for count, member in enumerate(bundle, 1):
            require(count <= MAX_MEMBERS, 'archive_member_count')
            name = safe_name(member.name.rstrip('/') if member.isdir() else member.name)
            require(name not in members and not member.sparse and (member.isfile() or member.isdir()),
                    'archive_duplicate_or_special_member')
            require(0 <= member.size <= MAX_ARCHIVE, 'archive_member_size')
            members[name] = member
        require('manifest.json' in members and members['manifest.json'].isfile(), 'manifest_missing')
        def small(name):
            name = safe_name(name)
            require(name in members and members[name].isfile()
                    and 0 < members[name].size <= MAX_META, 'archive_metadata_size')
            with bundle.extractfile(members[name]) as stream:
                body = stream.read(MAX_META + 1)
            require(len(body) == members[name].size, 'archive_metadata_short_read')
            return body
        manifest = decode(small('manifest.json'))
        require(isinstance(manifest, list) and len(manifest) == 1 and isinstance(manifest[0], dict),
                'archive_manifest_population')
        record = manifest[0]
        require(set(record) <= {'Config', 'RepoTags', 'Layers', 'LayerSources'}
                and {'Config', 'Layers'} <= set(record), 'archive_manifest_fields')
        config_path = safe_name(record['Config'])
        config_raw = small(config_path)
        require('sha256:' + sha(config_raw) == expected_config, 'archive_config_digest')
        config = decode(config_raw)
        require(config.get('architecture') == 'amd64' and config.get('os') == 'linux'
                and isinstance(config.get('rootfs'), dict)
                and config['rootfs'].get('type') == 'layers', 'archive_config_platform_rootfs')
        diffids = config['rootfs'].get('diff_ids')
        paths = record['Layers']
        require(isinstance(diffids, list) and 1 <= len(diffids) <= 256
                and all(isinstance(item, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', item) for item in diffids)
                and isinstance(paths, list) and len(paths) == len(diffids), 'archive_layer_population')
        if expected_diffids is not None:
            require(diffids == expected_diffids, 'archive_inspected_diffids')
        layers, verified, total_expanded = [], {}, 0
        for index, (name, wanted) in enumerate(zip(paths, diffids)):
            name = safe_name(name)
            require(name in members and members[name].isfile() and members[name].size > 0,
                    'archive_layer_missing')
            if name not in verified:
                digest = hashlib.sha256()
                byte_count = 0
                stored_digest = hashlib.sha256()
                class HashedReader:
                    def __init__(self, stream):
                        self.stream = stream
                    def read(self, count=-1):
                        raw = self.stream.read(count)
                        stored_digest.update(raw)
                        return raw
                with bundle.extractfile(members[name]) as layer:
                    prefix = layer.read(2)
                    layer.seek(0)
                    reader = HashedReader(layer)
                    stream = gzip.GzipFile(fileobj=reader) if prefix == b'\x1f\x8b' else reader
                    try:
                        while chunk := stream.read(1024 * 1024):
                            byte_count += len(chunk)
                            require(byte_count <= MAX_ARCHIVE, 'layer_expanded_size')
                            digest.update(chunk)
                    finally:
                        if isinstance(stream, gzip.GzipFile):
                            stream.close()
                    while reader.read(1024 * 1024):
                        pass
                total_expanded += byte_count
                require(total_expanded <= MAX_ARCHIVE, 'layers_total_expanded_size')
                # gzip is read to EOF: trailer/CRC are checked by stdlib.
                verified[name] = {'diff_id': 'sha256:' + digest.hexdigest(),
                                  'expanded_bytes': byte_count, 'stored_bytes': members[name].size,
                                  'stored_sha256': stored_digest.hexdigest(), 'gzip': prefix == b'\x1f\x8b'}
                if name.startswith('blobs/sha256/'):
                    require(HEX.fullmatch(name[len('blobs/sha256/'):])
                            and name[len('blobs/sha256/'):] == stored_digest.hexdigest(), 'layer_blob_locator_digest')
            actual = verified[name]
            require(actual['diff_id'] == wanted, 'layer_diffid_mismatch')
            layers.append({'index': index, 'path': name, **actual})
    require(fingerprint(before) == fingerprint(Path(path).stat()), 'archive_changed_during_layer_verification')
    return {'archive': archive, 'config_id': expected_config, 'config_path': config_path,
            'config_sha256': sha(config_raw), 'manifest_sha256': sha(canonical(manifest)),
            'layer_reference_count': len(layers), 'unique_layer_members': len(verified),
            'total_unique_expanded_layer_bytes': total_expanded, 'members': len(members),
            'all_layer_diffids_verified': True, 'safe_unique_outer_regular_or_directory_members': True,
            'layer_rows': layers, 'extraction': False, 'target_execution': False}


def command(argv, *, cwd=None, timeout=30, maximum=MAX_META):
    result = subprocess.run(argv, cwd=cwd, check=True, capture_output=True, timeout=timeout)
    require(len(result.stdout) + len(result.stderr) <= maximum, 'command_output_limit')
    return result.stdout


def git_value(source, argument):
    return command(['git', '-C', str(source), 'rev-parse', argument], maximum=65536).decode().strip()


def checked_git_source(source, commit, tree=None, population=None, allowed_eol_paths=()):
    require(git_value(source, 'HEAD') == commit, 'source_commit')
    actual_tree = git_value(source, 'HEAD^{tree}')
    if tree is not None:
        require(actual_tree == tree, 'source_tree')
    subprocess.run(['git', '-C', str(source), 'diff-index', '--quiet', 'HEAD', '--'],
                   check=True, timeout=30)
    listing = command(['git', '-C', str(source), 'ls-tree', '-rz', '--full-tree', 'HEAD'],
                      maximum=2 * 1024 * 1024)
    rows = []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        header, name = entry.split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        name = name.decode()
        source_name(name)
        require(kind == 'blob' and mode in {'100644', '100755'}, 'trusted_source_type')
        body = regular(source / name, 64 * 1024 * 1024)
        actual_blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
        normalization = None
        if actual_blob != blob and name in allowed_eol_paths:
            # Git attributes may write CRLF in an otherwise clean checkout.
            # Accept only if normalization matches the immutable original blob;
            # record actual worktree bytes and never edit a source file.
            canonical_body = body.replace(b'\r\n', b'\n')
            actual_blob = hashlib.sha1(b'blob ' + str(len(canonical_body)).encode()
                                       + b'\0' + canonical_body).hexdigest()
            normalization = 'CRLF_to_LF_for_Git_identity_check_only_no_source_edit'
        require(actual_blob == blob, 'trusted_source_blob')
        actual_mode = '100755' if (source / name).stat().st_mode & 0o111 else '100644'
        require(mode == actual_mode, 'trusted_source_mode')
        rows.append({'path': name, 'git_blob': blob, 'git_mode': mode,
                     'bytes': len(body), 'sha256': sha(body), 'git_normalization': normalization})
    if population is not None:
        require(len(rows) == population, 'trusted_source_population')
    return {'commit': commit, 'tree': actual_tree, 'tracked_files': len(rows),
            'tracked_byte_blob_mode_inventory_sha256': sha(canonical(rows)),
            'checkout_eol_differences': [row for row in rows if row['git_normalization'] is not None]}


def inspection(image):
    observed = decode(command(['docker', 'image', 'inspect', image]))
    require(isinstance(observed, list) and len(observed) == 1, 'image_population')
    observed = observed[0]
    require(observed.get('Id') == image and observed.get('Os') == 'linux'
            and observed.get('Architecture') == 'amd64'
            and type(observed.get('Size')) is int and 0 < observed['Size'] <= MAX_ARCHIVE,
            'image_identity_platform_size')
    require(observed.get('RootFS', {}).get('Type') == 'layers'
            and isinstance(observed['RootFS'].get('Layers'), list), 'image_layers')
    return observed


def identity(operation_source, expected_job):
    require(os.environ.get('GITHUB_REPOSITORY') == REPO
            and os.environ.get('GITHUB_REPOSITORY_ID') == '1282576027'
            and os.environ.get('GITHUB_REF') == BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_JOB') == expected_job, 'operation_authority_identity')
    head = os.environ.get('GITHUB_SHA', '')
    require(re.fullmatch(r'[0-9a-f]{40}', head) is not None
            and git_value(operation_source, 'HEAD') == head
            and os.environ.get('GITHUB_WORKFLOW_SHA') == head
            and os.environ.get('GITHUB_WORKFLOW_REF') == REPO + '/' + WORKFLOW + '@' + BRANCH,
            'operation_workflow_source_identity')
    require(sys.version_info[:2] == (3, 11), 'host_python_version')
    subprocess.run(['git', '-C', str(operation_source), 'diff-index', '--quiet', 'HEAD', '--'],
                   check=True, timeout=30)
    return {'workflow_head': head, 'workflow_tree': git_value(operation_source, 'HEAD^{tree}'),
            'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': 1,
            'runner_name': os.environ.get('RUNNER_NAME'), 'runner_os': os.environ.get('RUNNER_OS'),
            'runner_arch': os.environ.get('RUNNER_ARCH'), 'python': sys.version,
            'python_executable': sys.executable, 'kernel': list(os.uname()),
            'helper_sha256': sha(regular(Path(__file__), MAX_META))}


def write(path, value):
    payload = canonical(value) + b'\n'
    require(len(payload) <= MAX_LOG, 'compact_receipt_limit')
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        os.chmod(temporary, 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def provision_block(source):
    workflow = regular(source / '.github/workflows/cpp-full-project-integration.yml').decode()
    baseline = workflow.split('\n  project-baseline-qualification:\n', 1)[1].split('\n  llvm-toolchain-inventory:\n', 1)[0]
    segment = baseline.split('      - name: Provision exact tools without assessed source or runtime network\n', 1)[1]
    segment = segment.split('        run: |\n', 1)[1]
    lines = []
    for line in segment.splitlines():
        if line and not line.startswith('          '):
            break
        lines.append(line[10:] if line else '')
    script = '\n'.join(lines) + '\n'
    require('timeout 210s docker build --network=none' in script
            and 'docker image inspect' in script and 'docker cp' in script
            and 'docker push' not in script and 'qualification-input' not in script, 'provision_block_scope')
    return script.encode()


def run_logged_script(script, source, log):
    """Unchanged pinned provision commands; bounded log, no secret values logged."""
    with log.open('xb') as output:
        os.chmod(log, 0o600)
        proc = subprocess.Popen(['bash', '--noprofile', '--norc'], cwd=source,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        count = 0
        try:
            proc.stdin.write(script)
            proc.stdin.close()
            while chunk := proc.stdout.read1(65536):
                count += len(chunk)
                require(count <= MAX_LOG, 'build_log_retention_limit')
                output.write(chunk)
            require(proc.wait() == 0, 'pinned_provision_or_build_failed')
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            raise
        finally:
            proc.stdout.close()
    return file_digest(log, MAX_LOG)


def build(args, result):
    recipe = args.recipe_source.absolute()
    source_identity = checked_git_source(recipe, 'f0919654edd719059ea03319981b13f46ba70a88',
                                        'b9e200f62b9b2db9c6488326826ad8ae393418d0', 3305)
    pins_raw = regular(args.operation_source / 'scripts/cpp_diagnostic_image_inputs.json')
    pins = decode(pins_raw)
    require(pins['recipe_source_sha'] == source_identity['commit']
            and pins['recipe_source_tree'] == source_identity['tree'], 'pins_source_identity')
    for row in pins['trusted_recipe_files']:
        body = regular(recipe / safe_name(row['path']))
        require(len(body) == row['bytes'] and sha(body) == row['sha256']
                and hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() == row['git_blob'],
                'trusted_recipe_pin')
    cppcheck_path = recipe / 'toolchain/full-project/cppcheck'
    require(command(['git', '-C', str(cppcheck_path), 'ls-files', '--others', '-z'], maximum=MAX_META) == b'',
            'untracked_cppcheck_build_input')
    cppcheck = checked_git_source(cppcheck_path, pins['cppcheck_commit'], pins['cppcheck_tree'],
                                 1052, pins['cppcheck_checkout_eol_paths'])
    script = provision_block(recipe)
    result.update(recipe_source=source_identity, cppcheck_source=cppcheck,
                  input_pins_sha256=sha(pins_raw), provision_block_sha256=sha(script), phase='provision_build')
    write(args.output / 'receipt.json', result)
    result['build_log'] = run_logged_script(script, recipe, args.output / 'build.log')
    image = regular(recipe / 'full-project-image-id.txt', 1024).decode().strip()
    observed = inspection(image)
    require(observed['Config'].get('User') == '1000:1000'
            and observed['Config'].get('Entrypoint') == ['sleep'], 'diagnostic_image_configuration')
    base = decode(command(['docker', 'image', 'inspect', pins['base_image']]))
    require(isinstance(base, list) and len(base) == 1 and base[0].get('Architecture') == 'amd64'
            and base[0].get('Os') == 'linux'
            and any(ref.endswith('@' + pins['base_image'].split('@', 1)[1]) for ref in base[0].get('RepoDigests', [])),
            'pinned_base_image_identity')
    require(observed['RootFS']['Layers'][:len(base[0]['RootFS']['Layers'])] == base[0]['RootFS']['Layers'],
            'pinned_base_layer_prefix')
    receipts = {}
    for name in ['cpp-runtime-toolchain.json', 'cppcheck-header-observer.json', 'clang-header-observer.json']:
        body = regular(recipe / name)
        receipts[name] = {'bytes': len(body), 'sha256': sha(body), 'value': decode(body)}
    context = recipe / 'toolchain/full-project'
    provision_receipts = {}
    for family, lock_name in pins['lock_families'].items():
        expected_lock = regular(recipe / 'docker' / lock_name)
        require(regular(context / family / 'lock.json') == expected_lock, 'provision_lock_changed')
        acquired = decode(regular(context / family / 'receipt.json'))
        require(acquired.get('lock_sha256') == sha(expected_lock)
                and acquired.get('status') in {'VERIFIED_TOOL_INPUTS', 'VERIFIED_RUNTIME_DEPENDENCIES'},
                'provision_receipt_invalid')
        provision_receipts[family] = acquired
    require(sha(regular(context / 'cmake.whl', 64 * 1024 * 1024)) == pins['cmake_sha256']
            and sha(regular(context / 'pycapnp.whl', 8 * 1024 * 1024)) == pins['pycapnp_sha256'], 'wheel_identity')
    result.update(image_config_id=image, image_inspection=observed, base_inspection=base[0],
                  trusted_tool_receipts=receipts, provision_receipts=provision_receipts, phase='save_image')
    write(args.output / 'receipt.json', result)
    archive = args.output / 'image.tar'
    def save_limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARCHIVE, MAX_ARCHIVE))
    subprocess.run(['docker', 'image', 'save', '--output', str(archive), image],
                   check=True, timeout=SAVE_SECONDS, preexec_fn=save_limits)
    result['archive_proof'] = archive_proof(archive, image, observed['RootFS']['Layers'])
    result.update(phase='retained_local_image', status='DIAGNOSTIC_IMAGE_SAVED_UNRETRIEVED',
                  complete_image_archive_verified=True, supported_storage_retrieval_verified=False,
                  historical_image_recovered=False, new_config_matches_historical=(image == HISTORICAL),
                  environment_differences={'new_image_created': observed.get('Created'),
                    'historical_image_created': '2026-10-06T20:18:13.098263332Z',
                    'same_source_recipe_not_same_historical_execution': True,
                    'original_build_resource_scope': 'Original210s Docker build has no explicit4CPU/12GiB/256pid build flags. Those constrain assessed runtime; this workflow starts no assessed runtime.',
                    'recipe_commands_changed': False,
                    'host_requirements_install_omitted': 'Provision/build helper is stdlib-only; no native controller or qualification executes.',
                    'bytecode_cache_disabled_on_new_host': True})
    write(args.output / 'receipt.json', result)
    anchor = sha(regular(args.output / 'receipt.json', MAX_LOG))
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('receipt_sha256=' + anchor + '\nimage_config_id=' + image + '\n')
    print(json.dumps({'status': result['status'], 'image_config_id': image,
                      'archive': result['archive_proof']['archive'], 'production_qualified': False}))


def retrieve(args, result):
    root = args.input.absolute()
    require(root.resolve(strict=True) == root, 'retrieved_root_path')
    before_raw = regular(root / 'receipt.json', MAX_LOG)
    require(HEX.fullmatch(os.environ.get('NICO_DIAGNOSTIC_RECEIPT_SHA256', ''))
            and sha(before_raw) == os.environ['NICO_DIAGNOSTIC_RECEIPT_SHA256'], 'cross_job_receipt_anchor')
    before = decode(before_raw)
    require(before.get('schema') == 'nico.private.diagnostic_image_rebuild.v1'
            and before.get('status') == 'DIAGNOSTIC_IMAGE_SAVED_UNRETRIEVED'
            and before.get('production_qualified') is False
            and before.get('target_execution') is False
            and before['operation']['workflow_head'] == result['operation']['workflow_head']
            and before['operation']['run_id'] == result['operation']['run_id']
            and before['operation']['run_attempt'] == 1
            and before['operation']['runner_name'] != result['operation']['runner_name'], 'retrieved_receipt_binding')
    image = before['image_config_id']
    require(image == os.environ.get('NICO_DIAGNOSTIC_IMAGE_CONFIG_ID'), 'cross_job_image_anchor')
    expected_layers = before['image_inspection']['RootFS']['Layers']
    result.update(phase='archive_verification', build_receipt_sha256=sha(before_raw), image_config_id=image,
                  recipe_source=before['recipe_source'])
    write(args.output / 'receipt.json', result)
    proof = archive_proof(root / 'image.tar', image, expected_layers)
    require(proof == before['archive_proof'], 'retrieved_archive_changed')
    missing = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, timeout=30)
    require(missing.returncode != 0 and b'No such image' in missing.stderr
            and len(missing.stdout) + len(missing.stderr) <= MAX_META, 'fresh_runner_image_preexisting_or_daemon_unavailable')
    result.update(phase='load_image', archive_proof=proof, new_runner_image_absent_before_load=True)
    write(args.output / 'receipt.json', result)
    loaded = command(['docker', 'image', 'load', '--input', str(root / 'image.tar')], timeout=LOAD_SECONDS)
    observed = inspection(image)
    require(observed['RootFS']['Layers'] == expected_layers
            and observed['Config'] == before['image_inspection']['Config'], 'loaded_complete_image_identity')
    result.update(phase='retrieved_and_verified', status='DIAGNOSTIC_IMAGE_RETRIEVED_COMPLETE_IDENTITY_VERIFIED',
                  archive_proof=proof, image_inspection=observed, load_output_sha256=sha(loaded),
                  complete_image_archive_verified=True, supported_storage_retrieval_verified=True,
                  original_build_scope=before['environment_differences'], historical_image_recovered=False)
    write(args.output / 'receipt.json', result)
    print(json.dumps({'status': result['status'], 'image_config_id': image,
                      'retrieval_verified': True, 'production_qualified': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'retrieve'])
    parser.add_argument('--operation-source', type=Path, required=True)
    parser.add_argument('--recipe-source', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.operation_source = args.operation_source.absolute()
    args.output = args.output.absolute()
    require(args.output == args.output.resolve() and not args.output.exists(), 'new_output_required')
    args.output.mkdir(mode=0o700, parents=False)
    result = {'schema': 'nico.private.diagnostic_image_rebuild.v1', 'status': 'UNPROVEN',
              'phase': 'identity', 'mode': args.mode, 'operation': None, 'error': None,
              'archive_limit_bytes': MAX_ARCHIVE, 'save_seconds': SAVE_SECONDS, 'load_seconds': LOAD_SECONDS,
              'full_native_qualified': False, 'production_qualified': False, 'target_execution': False,
              'qualification_executed': False, 'registry_push': False, 'release_or_merge': False,
              'historical001f_timing_evidence': False, 'complete_image_archive_verified': False,
              'supported_storage_retrieval_verified': False}
    write(args.output / 'receipt.json', result)
    try:
        result['operation'] = identity(args.operation_source,
            'build-diagnostic-image' if args.mode == 'build' else 'verify-retained-diagnostic-image')
        write(args.output / 'receipt.json', result)
        if args.mode == 'build':
            require(args.recipe_source is not None and args.input is None, 'build_arguments')
            build(args, result)
        else:
            require(args.input is not None and args.recipe_source is None, 'retrieve_arguments')
            retrieve(args, result)
    except BaseException as error:
        result.update(status='UNPROVEN', error={'type': type(error).__name__,
                       'code': str(error) if isinstance(error, ValueError) else 'operation_failed'})
        write(args.output / 'receipt.json', result)
        raise


if __name__ == '__main__':
    main()
