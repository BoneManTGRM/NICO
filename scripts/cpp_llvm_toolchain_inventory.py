"""Authenticate an upstream LLVM package inventory; never install or execute it.

The result is preparation for a pinned tool-image change, not qualification.
The fixed signing key and repository are independent of assessed projects.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests

ORIGIN = 'https://apt.llvm.org/'
KEY_URL = ORIGIN + 'llvm-snapshot.gpg.key'
RELEASE_URL = ORIGIN + 'bookworm/dists/llvm-toolchain-bookworm-17/InRelease'
INDEX_PATH = 'main/binary-amd64/Packages.gz'
INDEX_URL = ORIGIN + 'bookworm/dists/llvm-toolchain-bookworm-17/' + INDEX_PATH
FINGERPRINT = '6084F3CF814B57C1CF12EFD515CF4D18AF4F7421'
PACKAGES = ('clang-17', 'libclang-cpp17', 'libllvm17', 'libclang-common-17-dev',
            'libclang1-17', 'libclang-rt-17-dev', 'llvm-17-linker-tools')


def release_index(release: bytes, compressed: bytes) -> None:
    in_hashes = False
    rows = []
    for line in release.decode('utf-8').splitlines():
        if not line.startswith(' '):
            in_hashes = line == 'SHA256:'
            continue
        if in_hashes:
            parts = line.split()
            if len(parts) == 3 and parts[2] == INDEX_PATH:
                rows.append(parts)
    if (len(rows) != 1 or rows[0][0] != hashlib.sha256(compressed).hexdigest()
            or rows[0][1] != str(len(compressed))):
        raise ValueError('llvm_index_signature_binding_invalid')


def select_packages(compressed: bytes) -> list[dict]:
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
        raw = archive.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('llvm_index_size_invalid')
    selected = {}
    for stanza in raw.decode('utf-8').split('\n\n'):
        fields = {}
        for line in stanza.splitlines():
            if not line or line.startswith((' ', '\t')):
                continue
            key, sep, value = line.partition(': ')
            if not sep or key in fields:
                raise ValueError('llvm_index_member_invalid')
            fields[key] = value
        name = fields.get('Package')
        if name not in PACKAGES:
            continue
        version = fields.get('Version', '')
        size = fields.get('Size', '')
        path = fields.get('Filename', '')
        digest = fields.get('SHA256', '')
        if (name in selected or fields.get('Architecture') not in {'amd64', 'all'}
                or re.fullmatch(r'(?:1:)?17\.0\.6(?:[~+\w.:-]+)', version) is None
                or not size.isdigit() or not 0 < int(size) <= 80 * 1024 * 1024
                or re.fullmatch(r'pool/main/[A-Za-z0-9_./+~%:-]+\.deb', path) is None
                or any(part in {'', '.', '..'} for part in path.split('/'))
                or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
            raise ValueError('llvm_package_identity_invalid')
        selected[name] = {'package': name, 'version': version, 'architecture': fields['Architecture'],
            'bytes': int(size), 'sha256': digest, 'url': ORIGIN + 'bookworm/' + path,
            'depends': fields.get('Depends', ''), 'pre_depends': fields.get('Pre-Depends', '')}
    if set(selected) != set(PACKAGES) or len({r['version'] for r in selected.values()}) != 1:
        raise ValueError('llvm_package_population_incomplete')
    if sum(r['bytes'] for r in selected.values()) > 200 * 1024 * 1024:
        raise ValueError('llvm_package_budget_exceeded')
    return [selected[name] for name in PACKAGES]


def fetch(url: str, destination: Path, *, limit: int, deadline: float) -> bytes:
    if url not in {KEY_URL, RELEASE_URL, INDEX_URL}:
        raise ValueError('llvm_inventory_destination_invalid')
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, stream=True, allow_redirects=False, timeout=(3, 5),
                         headers={'Accept-Encoding': 'identity'}) as response:
            if response.status_code != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity':
                raise ValueError('llvm_inventory_download_rejected')
            data = bytearray()
            for chunk in response.iter_content(65536):
                if time.monotonic() >= deadline or len(data) + len(chunk) > limit:
                    raise ValueError('llvm_inventory_download_limit')
                data.extend(chunk)
    if time.monotonic() >= deadline:
        raise ValueError('llvm_inventory_download_limit')
    destination.write_bytes(data)
    return bytes(data)


def inventory(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'nico.llvm-toolchain-inventory.v1', 'status': 'UNPROVEN',
              'installed': False, 'tools_executed': False, 'target_executed': False,
              'production_qualified': False}
    try:
        deadline = time.monotonic() + 60
        key = fetch(KEY_URL, output / 'upstream-key.asc', limit=65536, deadline=deadline)
        signed = fetch(RELEASE_URL, output / 'InRelease', limit=524288, deadline=deadline)
        index = fetch(INDEX_URL, output / 'Packages.gz', limit=4 * 1024 * 1024, deadline=deadline)
        with tempfile.TemporaryDirectory(prefix='nico-llvm-key-') as directory:
            home = Path(directory)
            base = ['gpg', '--batch', '--no-options', '--homedir', str(home), '--no-auto-key-retrieve']
            displayed = subprocess.run([*base, '--with-colons', '--show-keys', str(output / 'upstream-key.asc')],
                capture_output=True, check=True, timeout=5)
            fingerprints = [line.split(':')[9] for line in displayed.stdout.decode().splitlines() if line.startswith('fpr:')]
            if not fingerprints or fingerprints[0] != FINGERPRINT:
                raise ValueError('llvm_signing_key_mismatch')
            subprocess.run([*base, '--dearmor', '--output', str(home / 'keyring.gpg'), str(output / 'upstream-key.asc')],
                capture_output=True, check=True, timeout=5)
            verified = subprocess.run(['gpgv', '--homedir', str(home), '--keyring', str(home / 'keyring.gpg'),
                '--status-fd=1', '--output', str(output / 'Release'), str(output / 'InRelease')],
                capture_output=True, check=True, timeout=5)
            signatures = [line.split() for line in verified.stdout.decode().splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
            if len(signatures) != 1 or FINGERPRINT not in (signatures[0][2], signatures[0][-1]):
                raise ValueError('llvm_signer_not_authorized')
        release = (output / 'Release').read_bytes()
        release_index(release, index)
        packages = select_packages(index)
        result.update(status='AUTHENTICATED_INVENTORY', signing_key_fingerprint=FINGERPRINT,
            signing_key_sha256=hashlib.sha256(key).hexdigest(), inrelease_sha256=hashlib.sha256(signed).hexdigest(),
            index_sha256=hashlib.sha256(index).hexdigest(), packages=packages,
            dependency_closure_qualified=False, expected_package_hashes_recorded=True)
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error_code=str(exc) if
            isinstance(exc, ValueError) and re.fullmatch(r'llvm_[a-z_]+', str(exc)) else 'llvm_inventory_unavailable')
        raise
    finally:
        (output / 'receipt.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('llvm-toolchain-inventory'))
    result = inventory(parser.parse_args().output.resolve())
    print(json.dumps({'status': result['status'], 'installed': False, 'production_qualified': False}))
