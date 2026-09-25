"""Provision release-owned runtime fixture archives; never execute their bytes.

Only this repository's reviewed lock is used by CI. Assessed source, public
intake and worker responses cannot choose downloads or installation paths.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time
from urllib.parse import urlsplit

LOCK = Path(__file__).resolve().parents[1]/'docker/assessment-runtime-dependencies.lock.json'
MAX_DOWNLOAD = 64*1024*1024
MAX_EXPANDED = 128*1024*1024
MAX_MEMBER = 64*1024*1024


def _path(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./-]{1,240}', value) is not None
        and not value.startswith('/') and PurePosixPath(value).as_posix() == value
        and all(part not in {'', '.', '..'} for part in value.split('/')))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_lock(value):
    if (not isinstance(value, dict) or set(value) != {'schema', 'packages'}
            or value['schema'] != 'nico.cpp-runtime-dependencies.v1'
            or not isinstance(value['packages'], list) or not 1 <= len(value['packages']) <= 4):
        raise ValueError('cpp_runtime_dependency_lock_invalid')
    ids, destinations, total = set(), set(), 0
    for row in value['packages']:
        fields = {'id', 'url', 'sha256', 'bytes', 'members', 'license_file', 'license_sha256'}
        if (not isinstance(row, dict) or set(row) != fields
                or not isinstance(row['id'], str) or re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,79}', row['id']) is None
                or row['id'] in ids or not isinstance(row['url'], str)
                or type(row['bytes']) is not int or not 1 <= row['bytes'] <= MAX_DOWNLOAD
                or any(not isinstance(row[k], str) or re.fullmatch(r'[0-9a-f]{64}', row[k]) is None
                       for k in ('sha256', 'license_sha256'))
                or not _path(row['license_file']) or not isinstance(row['members'], dict)
                or not 1 <= len(row['members']) <= 16):
            raise ValueError('cpp_runtime_dependency_lock_invalid')
        url = urlsplit(row['url'])
        if (url.scheme != 'https' or url.netloc != 'bitcoincore.org'
                or not url.path.startswith('/bin/') or not url.path.endswith('.tar.gz')
                or not _path(url.path[1:]) or url.query or url.fragment):
            raise ValueError('cpp_runtime_dependency_url_invalid')
        for source, destination in row['members'].items():
            if (not _path(source) or not _path(destination) or not destination.startswith('previous-releases/')
                    or destination in destinations
                    or any(destination.startswith(p+'/') or p.startswith(destination+'/') for p in destinations)):
                raise ValueError('cpp_runtime_dependency_member_invalid')
            destinations.add(destination)
        ids.add(row['id']); total += row['bytes']
    if total > MAX_DOWNLOAD:
        raise ValueError('cpp_runtime_dependency_budget_invalid')
    return value['packages']


def provision(destination, *, lock_path=None, run=subprocess.run):
    lock_path = Path(lock_path or LOCK)
    with lock_path.open('rb') as handle:
        lock_raw = handle.read(65537)
    if len(lock_raw) > 65536:
        raise ValueError('cpp_runtime_dependency_lock_invalid')
    rows = validate_lock(json.loads(lock_raw))
    licenses = {}
    for row in rows:
        path = lock_path.parent/row['license_file']
        if any(p.is_symlink() for p in [path, *path.parents]):
            raise ValueError('cpp_runtime_dependency_license_invalid')
        with path.open('rb') as handle:
            raw = handle.read(65537)
        if not 0 < len(raw) <= 65536 or _sha(raw) != row['license_sha256']:
            raise ValueError('cpp_runtime_dependency_license_invalid')
        licenses[row['id']] = raw
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    payload = destination/'payload'; payload.mkdir(mode=0o755)
    (destination/'lock.json').write_bytes(lock_raw)
    result = {'schema': 'nico.cpp-runtime-dependency-provisioning.v1', 'status': 'UNPROVEN',
        'lock_sha256': _sha(lock_raw), 'target_executed': False, 'packages': [], 'error': None}
    deadline = time.monotonic()+40
    def check():
        if time.monotonic() >= deadline:
            raise ValueError('cpp_runtime_dependency_deadline')
    def save():
        (destination/'receipt.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    save()
    checksums = []
    try:
        for row in rows:
            check()
            archive = destination/(row['id']+'.tar.gz')
            left = max(1, int(deadline-time.monotonic()))
            run(['curl', '--disable', '--fail', '--silent', '--show-error', '--proto', '=https', '--tlsv1.2',
                 '--connect-timeout', '3', '--max-time', str(left), '--max-filesize', str(row['bytes']),
                 '--output', str(archive), row['url']], check=True, timeout=left+1,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')})
            check()
            if archive.is_symlink() or not archive.is_file() or archive.stat().st_size != row['bytes']:
                raise ValueError('cpp_runtime_dependency_archive_size')
            raw = archive.read_bytes()
            if _sha(raw) != row['sha256']:
                raise ValueError('cpp_runtime_dependency_archive_hash')
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                expanded = stream.read(MAX_EXPANDED+1)
            if len(expanded) > MAX_EXPANDED:
                raise ValueError('cpp_runtime_dependency_expanded_limit')
            check()
            retained, seen = [], set()
            with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as bundle:
                for index, member in enumerate(bundle):
                    check()
                    name = member.name.rstrip('/') if member.isdir() else member.name
                    if index >= 1024 or not _path(name) or name in seen:
                        raise ValueError('cpp_runtime_dependency_archive_members')
                    seen.add(name)
                    if name not in row['members']:
                        continue  # No unselected member is extracted, followed or executed.
                    if not member.isfile() or member.sparse or not 1 <= member.size <= MAX_MEMBER:
                        raise ValueError('cpp_runtime_dependency_member_type')
                    with bundle.extractfile(member) as source:
                        data = source.read(MAX_MEMBER+1)
                    if len(data) != member.size or not data.startswith(b'\x7fELF'):
                        raise ValueError('cpp_runtime_dependency_member_bytes')
                    relative = row['members'][name]
                    output = payload/relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with output.open('xb') as target:
                        target.write(data)
                    output.chmod(0o555); os.utime(output, (0, 0))
                    retained.append({'archive_member': name, 'path': relative,
                                     'sha256': _sha(data), 'bytes': len(data)})
                    checksums.append(_sha(data)+'  '+relative+'\n')
            if {item['archive_member'] for item in retained} != set(row['members']):
                raise ValueError('cpp_runtime_dependency_member_missing')
            license_name = 'licenses/'+row['id']+'.txt'
            license_output = payload/license_name
            license_output.parent.mkdir(exist_ok=True)
            license_output.write_bytes(licenses[row['id']]); license_output.chmod(0o444)
            os.utime(license_output, (0, 0))
            checksums.append(row['license_sha256']+'  '+license_name+'\n')
            result['packages'].append({'id': row['id'], 'url': row['url'],
                'archive_sha256': row['sha256'], 'archive_bytes': len(raw), 'members': retained,
                'unselected_member_count': len(seen)-len(retained), 'license_sha256': row['license_sha256']})
            archive.unlink(); save()
        check()
        (destination/'SHA256SUMS').write_text(''.join(sorted(checksums)))
        result['status'] = 'VERIFIED_RUNTIME_DEPENDENCIES'
    except Exception as exc:
        text = str(exc)
        result['error'] = text if re.fullmatch(r'cpp_runtime_dependency_[a-z_]+', text) else 'cpp_runtime_dependency_failed'
        raise
    finally:
        save()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps({'status': provision(args.destination)['status']}))
