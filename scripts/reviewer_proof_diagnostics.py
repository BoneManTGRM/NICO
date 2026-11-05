"""Allowlisted diagnostics only; never evidence of visual qualification."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

DIAGNOSTIC_BYTES = 2048
RESERVED_BYTES = 2 * DIAGNOSTIC_BYTES
UPLOAD_BYTES = 20 * 1024 * 1024
STAGES = frozenset({'build-setup', 'environment', 'npm-install', 'frontend-build',
                    'proof-setup', 'playwright-import', 'server-start', 'browser-proof'})
_stage = 'unknown'


def set_stage(stage):
    global _stage
    _stage = stage if isinstance(stage, str) and stage in STAGES else 'unknown'


def record(kind, error):
    # Never serialize messages, args, commands, paths, URLs or environment values.
    category = 'other'
    for cls, label in ((subprocess.TimeoutExpired, 'timeout'),
                       (subprocess.CalledProcessError, 'process-exit'),
                       (ImportError, 'import'), (OSError, 'os'),
                       (AssertionError, 'assertion'), (ValueError, 'value'),
                       (RuntimeError, 'runtime'), (SystemExit, 'system-exit'),
                       (KeyboardInterrupt, 'interrupted')):
        if isinstance(error, cls):
            category = label
            break
    code = error.returncode if isinstance(error, subprocess.CalledProcessError) else None
    if isinstance(error, SystemExit):
        code = error.code
    bounded_code = code if type(code) is int and -255 <= code <= 255 else None
    return {'schema': 'nico.reviewer-proof-diagnostic.v1', 'kind': kind,
            'stage': _stage, 'outcome': 'returned' if error is None else 'failed',
            'error_category': None if error is None else category,
            'exit_code': bounded_code, 'exit_code_omitted': code is not None and bounded_code is None,
            'visual_qualification': False}


def write_record(root, kind, error):
    if kind not in {'build', 'proof'}:
        raise ValueError('unknown diagnostic kind')
    data = json.dumps(record(kind, error), sort_keys=True).encode('ascii')
    if len(data) > DIAGNOSTIC_BYTES:
        raise RuntimeError('diagnostic budget exceeded')
    # Exclusive creation refuses symlinks and stale records from earlier attempts.
    path = Path(root) / f'reviewer-binding-{kind}-diagnostic.json'
    with path.open('xb') as stream:
        stream.write(data)


def run_with_diagnostics(root, kind, action):
    set_stage('build-setup' if kind == 'build' else 'proof-setup')
    try:
        result = action()
    except BaseException as original:
        try:
            write_record(root, kind, original)
        except BaseException:
            # Fixed text only; diagnostic failure must not replace the original.
            try:
                print('Reviewer diagnostic unavailable; original failure preserved.')
            except BaseException:
                pass
        raise
    write_record(root, kind, None)  # Failure here cannot silently qualify success.
    return result


def validate_record(data, kind):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate diagnostic field')
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    expected = {'schema', 'kind', 'stage', 'outcome', 'error_category',
                'exit_code', 'exit_code_omitted', 'visual_qualification'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('invalid diagnostic fields')
    if value['schema'] != 'nico.reviewer-proof-diagnostic.v1' or value['kind'] != kind:
        raise ValueError('invalid diagnostic identity')
    stages = {'unknown', 'build-setup', 'environment', 'npm-install', 'frontend-build'} if kind == 'build' else {
        'unknown', 'proof-setup', 'playwright-import', 'server-start', 'browser-proof'}
    if not isinstance(value['stage'], str) or value['stage'] not in stages:
        raise ValueError('invalid diagnostic stage')
    if value['outcome'] not in ('returned', 'failed') or value['visual_qualification'] is not False:
        raise ValueError('invalid diagnostic outcome')
    if type(value['exit_code_omitted']) is not bool:
        raise ValueError('invalid omission flag')
    code = value['exit_code']
    if code is not None and (type(code) is not int or not -255 <= code <= 255):
        raise ValueError('invalid exit code')
    category = value['error_category']
    if value['outcome'] == 'returned':
        if category is not None or code is not None or value['exit_code_omitted']:
            raise ValueError('inconsistent successful diagnostic')
    elif not isinstance(category, str) or category not in {
        'other', 'timeout', 'process-exit', 'import', 'os', 'assertion',
        'value', 'runtime', 'system-exit', 'interrupted'}:
        raise ValueError('invalid diagnostic category')
    if value['exit_code_omitted'] and code is not None:
        raise ValueError('inconsistent omitted exit code')
    return json.dumps(value, sort_keys=True).encode('ascii')


def _read_regular(directory, name, limit):
    # Bound the read itself, and never follow a path substituted with a symlink.
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError('unsafe or oversized artifact')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) > limit or len(data) != before.st_size or (
            before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('oversized or changing artifact')
        return data


def stage_upload(root):
    """Copy validated bytes into a fresh private directory; expose no raw paths."""
    root = Path(root).absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    files = {}
    total = 0
    try:
        for kind in ('build', 'proof'):
            name = f'reviewer-binding-{kind}-diagnostic.json'
            try:
                data = _read_regular(root_fd, name, DIAGNOSTIC_BYTES)
            except FileNotFoundError:
                continue
            data = validate_record(data, kind)
            if len(data) > DIAGNOSTIC_BYTES:
                raise ValueError('diagnostic budget exceeded')
            files[name] = data
            total += len(data)
        try:
            proof_fd = os.open('reviewer-binding-webkit-proof', flags, dir_fd=root_fd)
        except FileNotFoundError:
            proof_fd = None
        if proof_fd is not None:
            try:
                try:
                    publish_fd = os.open('publish', flags, dir_fd=proof_fd)
                except FileNotFoundError:
                    publish_fd = None
                if publish_fd is not None:
                    try:
                        for name in sorted(os.listdir(publish_fd)):
                            if name not in {'server.log', 'manifest.json'} and not re.fullmatch(
                                r'(en|es-MX)-(desktop|mobile)-(qualified|unqualified|duplicate|stale|dependency)\.png', name
                            ) and name not in {'en-desktop-navigation.png', 'es-MX-desktop-navigation.png'}:
                                raise ValueError('unexpected proof artifact')
                            data = _read_regular(publish_fd, name, UPLOAD_BYTES - total)
                            total += len(data)
                            files[name] = data
                    finally:
                        os.close(publish_fd)
            finally:
                os.close(proof_fd)
    finally:
        os.close(root_fd)
    if not files or total > UPLOAD_BYTES:
        raise ValueError('missing or over-budget upload')
    destination = Path(tempfile.mkdtemp(prefix='reviewer-binding-validated-', dir=root))
    try:
        for name, data in files.items():
            with (destination / name).open('xb') as stream:
                stream.write(data)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


if __name__ == '__main__':
    # Called only by the always-run validation step; emit an output on success only.
    print('upload_path=' + str(stage_upload(Path(__file__).resolve().parents[1])))
