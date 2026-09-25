"""Bounded project-wide snapshots built on the existing generated-byte boundary.

This module captures bytes only. Compiler visitation, static analysis and
production qualification remain separate, evidence-bound capabilities.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from nico.assessment_cpp_generated_context import (
    _PRELUDE, _strict_json, _stable_bytes, build_directory, snapshot_directory,
    run_generated_program,
)

# Project-wide snapshots are opt-in. The earlier header-only contract and all
# four earlier embedded programs above retain their exact bytes and limits.
PROJECT_GENERATED_MAX_FILES = 2048
# Byte-table headers can expand well beyond their raw asset size. This
# per-file bound shares, rather than raises, the existing aggregate allowance.
PROJECT_GENERATED_MAX_FILE_BYTES = 32 * 1024 * 1024
PROJECT_GENERATED_MAX_BYTES = 32 * 1024 * 1024
PROJECT_GENERATED_SCAN_LIMIT = 40000
PROJECT_GENERATED_STREAM_LIMIT = 48 * 1024 * 1024
PROJECT_HEADER_SUFFIXES = ('.h', '.hh', '.hpp', '.hxx', '.inc', '.inl', '.ipp', '.tpp', '.txx')


def _project_paths(paths):
    if (not isinstance(paths, list) or len(paths) > PROJECT_GENERATED_MAX_FILES
            or any(not isinstance(p, str) or len(p) > 1000
                or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+-]*', p) is None
                or any(part in {'', '.', '..', '.git'} for part in p.split('/')) for p in paths)
            or paths != sorted(set(paths))):
        raise ValueError('worker_generated_project_paths_invalid')
    members = set(paths)
    if any('/'.join(p.split('/')[:i]) in members
           for p in paths for i in range(1, len(p.split('/')))):
        raise ValueError('worker_generated_project_paths_invalid')
    return list(paths)


def project_snapshot_request(contexts):
    """Bind a byte capture to the shared context inventory; grant no execution."""
    if (not isinstance(contexts, dict)
            or contexts.get('schema') != 'nico.cpp-compilation-contexts.v1'
            or contexts.get('build_directory') not in ('/work/build', '/work/address', '/work/undefined')):
        raise ValueError('worker_generated_project_context_invalid')
    keys = ('database_sha256', 'source_population_sha256', 'context_membership_sha256')
    if any(not isinstance(contexts.get(k), str) or re.fullmatch(r'[0-9a-f]{64}', contexts[k]) is None for k in keys):
        raise ValueError('worker_generated_project_context_invalid')
    rows = contexts.get('contexts')
    if (not isinstance(rows, list) or not 1 <= len(rows) <= 20000
            or type(contexts.get('context_count')) is not int or contexts['context_count'] != len(rows)
            or any(not isinstance(r, dict) or r.get('index') != i
                or r.get('origin') not in {'original', 'generated'}
                or not isinstance(r.get('path'), str)
                or not isinstance(r.get('context_id'), str)
                or re.fullmatch(r'[0-9a-f]{64}', r['context_id']) is None for i, r in enumerate(rows))):
        raise ValueError('worker_generated_project_context_invalid')
    identities = sorted(r['context_id'] for r in rows)
    if (len(set(identities)) != len(identities)
            or hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
               != contexts['context_membership_sha256']
            or sorted({r['path'] for r in rows if r['origin'] == 'generated'}) != contexts.get('generated_units')
            or sorted({r['path'] for r in rows if r['origin'] == 'original'}) != contexts.get('original_units')):
        raise ValueError('worker_generated_project_context_invalid')
    group = {'/work/build': 'baseline', '/work/address': 'address', '/work/undefined': 'undefined'}[contexts['build_directory']]
    return {'schema': 'nico.cpp-generated-project-request.v1', 'configuration': group,
        **{k: contexts[k] for k in keys}, 'generated_units': _project_paths(contexts.get('generated_units'))}


def _project_request(request):
    keys = {'schema', 'configuration', 'database_sha256', 'source_population_sha256',
            'context_membership_sha256', 'generated_units'}
    if (not isinstance(request, dict) or set(request) != keys
            or request['schema'] != 'nico.cpp-generated-project-request.v1'):
        raise ValueError('worker_generated_project_request_invalid')
    build_directory(request['configuration'])
    _project_paths(request['generated_units'])
    if any(not isinstance(request[k], str) or re.fullmatch(r'[0-9a-f]{64}', request[k]) is None
           for k in ('database_sha256', 'source_population_sha256', 'context_membership_sha256')):
        raise ValueError('worker_generated_project_request_invalid')
    return request


def _project_header_inventory(root):
    """Bounded descriptor traversal. Links and special files are never read.

    Non-header links are retained as explicit exclusions, not followed. Any
    required generated unit behind one still fails the separate exact read.
    This inventories header candidates; it never claims compiler visitation.
    """
    root = Path(root)
    if not root.is_absolute():
        raise ValueError('worker_generated_root_invalid')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    headers, links, seen = [], [], [0]
    def walk(directory, prefix, depth):
        if depth > 64:
            raise ValueError('worker_generated_project_inventory_limit')
        with os.scandir(directory) as entries:
            for entry in entries:
                seen[0] += 1
                if seen[0] > PROJECT_GENERATED_SCAN_LIMIT:
                    raise ValueError('worker_generated_project_inventory_limit')
                relative = prefix + entry.name
                info = entry.stat(follow_symlinks=False)
                candidate = entry.name.lower().endswith(PROJECT_HEADER_SUFFIXES)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        walk(child, relative + '/', depth + 1)
                    finally:
                        os.close(child)
                elif candidate:
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError('worker_generated_project_header_type_invalid')
                    headers.append(relative)
                    if len(headers) > PROJECT_GENERATED_MAX_FILES:
                        raise ValueError('worker_generated_project_inventory_limit')
                elif stat.S_ISLNK(info.st_mode):
                    links.append(relative)
                    if len(links) > PROJECT_GENERATED_MAX_FILES:
                        raise ValueError('worker_generated_project_inventory_limit')
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        walk(fd, '', 0)
    finally:
        os.close(fd)
    return _project_paths(sorted(headers)), _project_paths(sorted(links))


def _project_file_population(files):
    raw = json.dumps({p: {'bytes': v['bytes'], 'sha256': v['sha256']} for p, v in sorted(files.items())},
                     sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


class ProjectSnapshotFailure(ValueError):
    """A rejected member and its bounds, never its contents or host error text."""
    def __init__(self, code, failed_input):
        super().__init__(code)
        self.failed_input = failed_input


def _input_metadata(root, relative):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in (*Path(root).parts[1:], *relative.split('/')[:-1]):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        info = os.stat(relative.split('/')[-1], dir_fd=fd, follow_symlinks=False)
        kind = ('regular' if stat.S_ISREG(info.st_mode) else 'symlink' if stat.S_ISLNK(info.st_mode)
                else 'directory' if stat.S_ISDIR(info.st_mode) else 'other')
        return {'type': kind, 'bytes': info.st_size, 'links': info.st_nlink}
    except OSError:
        return {'type': 'unavailable', 'bytes': None, 'links': None}
    finally:
        os.close(fd)


def _project_read(root, relative, maximum, total, phase):
    try:
        return _stable_bytes(root, relative, maximum)
    except (ValueError, OSError) as error:
        code = str(error)
        if re.fullmatch(r'worker_generated_[a-z_]+', code) is None:
            code = 'worker_generated_capture_unavailable'
        raise ProjectSnapshotFailure(code, {'path': relative, 'phase': phase,
            'effective_max_bytes': maximum, 'captured_bytes_before': total,
            'observed': _input_metadata(root, relative)}) from error


def capture_project_snapshot(build_root, destination, request):
    """Capture exact generated units plus bounded regular header candidates.

    The new snapshot is private and read-only. Repeated reads and inventories
    detect observed changes; only these copied bytes may feed later analysis.
    No build output is executed and the producer's files are never modified.
    """
    request = _project_request(request)
    build_root, destination = Path(build_root), Path(destination)
    parent = destination.parent
    info = parent.lstat()
    if (parent.absolute() != parent.resolve(strict=True) or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700
            or destination.exists() or destination.is_symlink()):
        raise ValueError('worker_generated_destination_invalid')
    headers, links = _project_header_inventory(build_root)
    paths = _project_paths(sorted(set(request['generated_units']) | set(headers)))
    staging = Path(tempfile.mkdtemp(prefix='.project-generated-', dir=parent))
    files, total = {}, 0
    try:
        for relative in paths:
            raw = _project_read(build_root, relative,
                min(PROJECT_GENERATED_MAX_FILE_BYTES, PROJECT_GENERATED_MAX_BYTES - total), total, 'initial_read')
            total += len(raw)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('xb') as handle:
                handle.write(raw)
            target.chmod(0o444)
            files[relative] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                               'base64': base64.b64encode(raw).decode('ascii')}
        for relative in paths:
            raw = _project_read(build_root, relative, PROJECT_GENERATED_MAX_FILE_BYTES, total, 'verification_read')
            if raw != base64.b64decode(files[relative]['base64'], validate=True):
                raise ValueError('worker_generated_input_changed')
        if _project_header_inventory(build_root) != (headers, links):
            raise ValueError('worker_generated_input_changed')
        value = {**request, 'schema': 'nico.cpp-generated-project.v1',
            'header_candidates': headers, 'unfollowed_links': links, 'files': files,
            'captured_bytes': total, 'file_population_sha256': _project_file_population(files),
            'analysis_executed': False, 'header_dependencies_verified': False}
        if len(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()) > PROJECT_GENERATED_STREAM_LIMIT:
            raise ValueError('worker_generated_project_output_limit')
        for directory in sorted((p for p in staging.rglob('*') if p.is_dir()), reverse=True):
            directory.chmod(0o555)
        staging.chmod(0o555)
        os.rename(staging, destination)
        return value
    finally:
        if staging.exists():
            staging.chmod(0o700)
            for directory in staging.rglob('*'):
                if directory.is_dir(): directory.chmod(0o700)
            shutil.rmtree(staging)


def validate_project_snapshot(value, contexts):
    """Reconstruct identities and every captured-byte digest on the controller."""
    request = project_snapshot_request(contexts)
    fields = set(request) | {'header_candidates', 'unfollowed_links', 'files', 'captured_bytes',
                            'file_population_sha256', 'analysis_executed', 'header_dependencies_verified'}
    if (not isinstance(value, dict) or set(value) != fields
            or value['schema'] != 'nico.cpp-generated-project.v1'
            or any(value[k] != request[k] for k in request if k != 'schema')
            or value['analysis_executed'] is not False or value['header_dependencies_verified'] is not False
            or not isinstance(value['files'], dict) or type(value['captured_bytes']) is not int):
        raise ValueError('worker_generated_project_snapshot_invalid')
    headers, links = _project_paths(value['header_candidates']), _project_paths(value['unfollowed_links'])
    if (any(not p.lower().endswith(PROJECT_HEADER_SUFFIXES) for p in headers)
            or (set(headers) | set(request['generated_units'])) & set(links)
            or sorted(value['files']) != _project_paths(sorted(set(headers) | set(request['generated_units'])))):
        raise ValueError('worker_generated_project_population_invalid')
    total = 0
    for item in value['files'].values():
        if (not isinstance(item, dict) or set(item) != {'sha256', 'bytes', 'base64'}
                or type(item['bytes']) is not int or not 0 <= item['bytes'] <= PROJECT_GENERATED_MAX_FILE_BYTES
                or not isinstance(item['base64'], str)
                or len(item['base64']) > 4 * ((PROJECT_GENERATED_MAX_FILE_BYTES + 2) // 3)
                or not isinstance(item['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None):
            raise ValueError('worker_generated_project_snapshot_invalid')
        raw = base64.b64decode(item['base64'], validate=True)
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('worker_generated_project_digest_mismatch')
        total += len(raw)
        if total > PROJECT_GENERATED_MAX_BYTES:
            raise ValueError('worker_generated_project_size_invalid')
    if total != value['captured_bytes'] or value['file_population_sha256'] != _project_file_population(value['files']):
        raise ValueError('worker_generated_project_size_invalid')
    return value


def collect_project_snapshot(request):
    if os.getuid() != 1001 or os.getgid() != 1001:
        raise ValueError('worker_generated_analyst_identity')
    request = _project_request(request)
    group = request['configuration']
    return capture_project_snapshot(Path(build_directory(group)),
        Path(snapshot_directory(group)), request)


def run_project_snapshot():
    """Retain bounded diagnostics in the new project path; legacy paths unchanged."""
    import sys
    request = None
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('worker_generated_request_size_invalid')
        request = _strict_json(raw)
        result = collect_project_snapshot(request)
    except Exception as error:
        group = request.get('configuration') if isinstance(request, dict) else None
        code = str(error)
        if re.fullmatch(r'worker_(?:compiler|generated)_[a-z_]+', code) is None:
            code = 'worker_generated_capture_unavailable'
        result = {'schema': 'nico.cpp-generated-failure.v1', 'configuration': group,
                  'phase': 'project_snapshot', 'error': code}
        if isinstance(error, ProjectSnapshotFailure):
            result['failed_input'] = error.failed_input
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        sys.exit(1)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


PROJECT_SNAPSHOT_PROGRAM = (_PRELUDE +
    f'PROJECT_GENERATED_MAX_FILES={PROJECT_GENERATED_MAX_FILES}\n'
    f'PROJECT_GENERATED_MAX_FILE_BYTES={PROJECT_GENERATED_MAX_FILE_BYTES}\n'
    f'PROJECT_GENERATED_MAX_BYTES={PROJECT_GENERATED_MAX_BYTES}\n'
    f'PROJECT_GENERATED_SCAN_LIMIT={PROJECT_GENERATED_SCAN_LIMIT}\n'
    f'PROJECT_GENERATED_STREAM_LIMIT={PROJECT_GENERATED_STREAM_LIMIT}\n'
    f'PROJECT_HEADER_SUFFIXES={PROJECT_HEADER_SUFFIXES!r}\n' +
    '\n'.join(inspect.getsource(f) for f in (_strict_json, build_directory, snapshot_directory,
        _stable_bytes, _project_paths, _project_request, _project_header_inventory,
        _project_file_population, ProjectSnapshotFailure, _input_metadata, _project_read,
        capture_project_snapshot, collect_project_snapshot, run_project_snapshot)) +
    "\nrun_project_snapshot()\n")


def restore_project_files(request, destination):
    """Restore a controller-validated snapshot into a fresh private analyst tree.

    Context and compiler bindings are checked before this call by the controller.
    The isolated receiver independently checks paths, byte limits and all hashes;
    it never reads a build tree, follows a link or executes a captured member.
    """
    if (not isinstance(request, dict)
            or set(request) != {'schema', 'files', 'file_population_sha256'}
            or request['schema'] != 'nico.cpp-project-restore.v1'
            or not isinstance(request['files'], dict)
            or not isinstance(request['file_population_sha256'], str)
            or re.fullmatch(r'[0-9a-f]{64}', request['file_population_sha256']) is None):
        raise ValueError('worker_project_restore_request_invalid')
    paths = _project_paths(sorted(request['files']))
    total = 0
    for item in request['files'].values():
        if (not isinstance(item, dict) or set(item) != {'sha256', 'bytes', 'base64'}
                or type(item['bytes']) is not int or not 0 <= item['bytes'] <= PROJECT_GENERATED_MAX_FILE_BYTES
                or not isinstance(item['base64'], str)
                or len(item['base64']) > 4 * ((item['bytes'] + 2) // 3)
                or not isinstance(item['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', item['sha256']) is None):
            raise ValueError('worker_project_restore_member_invalid')
        total += item['bytes']
        if total > PROJECT_GENERATED_MAX_BYTES:
            raise ValueError('worker_project_restore_size_invalid')
    if _project_file_population(request['files']) != request['file_population_sha256']:
        raise ValueError('worker_project_restore_population_invalid')
    destination = Path(destination)
    parent = destination.parent
    info = parent.lstat()
    if (not parent.is_absolute() or parent != parent.resolve(strict=True)
            or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or destination.exists() or destination.is_symlink()):
        raise ValueError('worker_project_restore_destination_invalid')
    staging = Path(tempfile.mkdtemp(prefix='.project-restore-', dir=parent))
    try:
        for path in paths:
            item = request['files'][path]
            raw = base64.b64decode(item['base64'], validate=True)
            if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('worker_project_restore_digest_invalid')
            leaf = staging / path
            leaf.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with leaf.open('xb') as handle:
                handle.write(raw)
            leaf.chmod(0o444)
            if _stable_bytes(staging, path, PROJECT_GENERATED_MAX_FILE_BYTES) != raw:
                raise ValueError('worker_project_restore_written_bytes_invalid')
        for directory in sorted((p for p in staging.rglob('*') if p.is_dir()), reverse=True):
            directory.chmod(0o555)
        staging.chmod(0o555)
        os.rename(staging, destination)
        return {'file_population_sha256': request['file_population_sha256'],
                'files': {p: {'sha256': v['sha256'], 'bytes': v['bytes']}
                          for p, v in sorted(request['files'].items())}}
    finally:
        if staging.exists():
            staging.chmod(0o700)
            for directory in staging.rglob('*'):
                if directory.is_dir():
                    directory.chmod(0o700)
            shutil.rmtree(staging)


def run_project_restore():
    import sys
    try:
        if os.getuid() != 1001 or os.getgid() != 1001:
            raise ValueError('worker_project_restore_identity_invalid')
        raw = sys.stdin.buffer.read(PROJECT_GENERATED_STREAM_LIMIT + 1)
        if len(raw) > PROJECT_GENERATED_STREAM_LIMIT:
            raise ValueError('worker_project_restore_input_limit')
        result = restore_project_files(_strict_json(raw), Path('/work/analysis/generated-baseline'))
    except Exception as exc:
        code = str(exc)
        if re.fullmatch(r'worker_project_restore_[a-z_]+', code) is None:
            code = 'worker_project_restore_failed'
        print(json.dumps({'schema': 'nico.cpp-project-restore-failure.v1', 'error': code}))
        sys.exit(1)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


PROJECT_RESTORE_PROGRAM = (_PRELUDE
    + f'PROJECT_GENERATED_MAX_FILES={PROJECT_GENERATED_MAX_FILES}\n'
    + f'PROJECT_GENERATED_MAX_FILE_BYTES={PROJECT_GENERATED_MAX_FILE_BYTES}\n'
    + f'PROJECT_GENERATED_MAX_BYTES={PROJECT_GENERATED_MAX_BYTES}\n'
    + f'PROJECT_GENERATED_STREAM_LIMIT={PROJECT_GENERATED_STREAM_LIMIT}\n'
    + '\n'.join(inspect.getsource(f) for f in (_strict_json, _project_paths,
        _project_file_population, _stable_bytes, restore_project_files, run_project_restore))
    + '\nrun_project_restore()\n')
