"""Verify every original Qt translation blob without executing assessed source."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from nico.node_scanner_applicability_v1 import (
    inspect_node_inputs, justified_inapplicability, valid_input_inventory,
)

COMMIT = 'e7aef7e86da79000aa42f5ba6d13b0d123d9da7c'
TREE = '0c25bcc9297fae81907ba39d2aa29ff1e99013eb'
FILE_COUNT = 101
BLOB_COUNT = 3043


def git(source: Path, *args: str) -> bytes:
    return subprocess.run(['git', '-C', str(source), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=30).stdout


def verify(source: Path, manifest_path: Path) -> dict:
    source = source.resolve()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    if (manifest.get('schema') != 'nico.qt-corpus-manifest.v1'
            or manifest.get('repository') != 'bitcoin/bitcoin'
            or manifest.get('commit_sha') != COMMIT
            or manifest.get('tree_sha') != TREE
            or manifest.get('expected_translation_files') != FILE_COUNT
            or not isinstance(manifest.get('files'), list)
            or len(manifest['files']) != FILE_COUNT):
        raise ValueError('qt_corpus_manifest_identity_invalid')
    if (git(source, 'rev-parse', 'HEAD').decode().strip() != COMMIT
            or git(source, 'rev-parse', 'HEAD^{tree}').decode().strip() != TREE):
        raise ValueError('qt_corpus_checkout_identity_mismatch')
    expected = {}
    for item in manifest['files']:
        path = item.get('path')
        if (not isinstance(path, str) or not path.endswith('.ts')
                or path.startswith('/') or '..' in path.split('/') or path in expected
                or type(item.get('size_bytes')) is not int or item['size_bytes'] <= 0
                or re.fullmatch(r'[0-9a-f]{40}', str(item.get('git_blob_sha1') or '')) is None):
            raise ValueError('qt_corpus_manifest_member_invalid')
        expected[path] = item

    tracked = {}
    original_blobs = []
    for row in git(source, 'ls-tree', '-r', '-l', '-z', 'HEAD').split(b'\0'):
        if not row:
            continue
        metadata, path_raw = row.split(b'\t', 1)
        mode, kind, digest, size = metadata.split()
        path = path_raw.decode('utf-8')
        if kind != b'blob' or mode not in {b'100644', b'100755'}:
            raise ValueError('qt_corpus_unsupported_source_member')
        file = source / path
        if file.is_symlink() or not file.is_file():
            raise ValueError('qt_corpus_complete_checkout_member_missing:' + path)
        raw = file.read_bytes()
        original = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw,
                                usedforsecurity=False).hexdigest()
        if original != digest.decode() or len(raw) != int(size):
            raise ValueError('qt_corpus_complete_checkout_blob_mismatch:' + path)
        original_blobs.append({'path': path, 'mode': mode.decode(),
                               'git_blob_sha1': original, 'size_bytes': len(raw)})
        if path.lower().endswith(('.ts', '.tsx', '.mts', '.cts')):
            if kind != b'blob' or mode not in {b'100644', b'100755'}:
                raise ValueError('qt_corpus_non_regular_typescript_input')
            tracked[path] = {'git_blob_sha1': digest.decode(), 'size_bytes': int(size)}
    if len(original_blobs) != BLOB_COUNT:
        raise ValueError('qt_corpus_complete_blob_population_mismatch')
    if git(source, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('qt_corpus_checkout_dirty_or_extra_inputs')
    if set(tracked) != set(expected):
        raise ValueError('qt_corpus_complete_membership_mismatch')

    verified = {}
    for path, item in expected.items():
        file = source / path
        if file.is_symlink() or not file.is_file():
            raise ValueError('qt_corpus_checkout_member_invalid')
        raw = file.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw,
                            usedforsecurity=False).hexdigest()
        if (tracked[path] != {'git_blob_sha1': item['git_blob_sha1'],
                             'size_bytes': item['size_bytes']}
                or blob != item['git_blob_sha1'] or len(raw) != item['size_bytes']):
            raise ValueError('qt_corpus_original_blob_mismatch:' + path)
        verified[path] = {'path': path, 'format': 'qt-ts-xml-v1',
                          'sha256': hashlib.sha256(raw).hexdigest(),
                          'size_bytes': len(raw)}

    producer = Path.cwd().resolve()
    producer_sha = git(producer, 'rev-parse', 'HEAD').decode().strip()
    from nico import node_scanner_applicability_v1, scanner_applicability_v1
    module_identities = []
    for module in (node_scanner_applicability_v1, scanner_applicability_v1):
        file = Path(module.__file__).resolve()
        relative = file.relative_to(producer).as_posix()
        raw = file.read_bytes()
        if raw != git(producer, 'show', 'HEAD:' + relative):
            raise ValueError('qt_corpus_producer_module_not_exact_source')
        module_identities.append({'path': relative, 'sha256': hashlib.sha256(raw).hexdigest()})
    inventory = inspect_node_inputs(source, COMMIT)
    observed = {item['path']: item for item in inventory['qt_translation_files']}
    if (not valid_input_inventory(inventory, COMMIT)
            or not justified_inapplicability(inventory, 'typescript', COMMIT)
            or inventory['typescript_input_paths'] != [] or observed != verified):
        raise ValueError('qt_corpus_classification_or_absence_unproven')
    return {
        'schema': 'nico.qt-corpus-verification.v1', 'status': 'passed',
        'evidence_scope': 'source_only_translation_classification',
        'assessed_source_executed': False, 'native_execution_credit': False,
        'repository': 'bitcoin/bitcoin', 'commit_sha': COMMIT, 'tree_sha': TREE,
        'producer_source_sha': producer_sha, 'producer_modules': module_identities,
        'verified_original_blobs': len(original_blobs),
        'complete_blob_inventory_sha256': hashlib.sha256(json.dumps(
            original_blobs, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'expected_files': FILE_COUNT, 'verified_files': len(observed),
        'total_original_bytes': sum(item['size_bytes'] for item in observed.values()),
        'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'inventory_sha256': inventory['inventory_sha256'],
        'typescript_input_paths': [], 'qt_translation_files': [
            observed[path] for path in sorted(observed)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    proof = verify(args.source, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, sort_keys=True, indent=2) + '\n',
                           encoding='utf-8')
    print(json.dumps({key: value for key, value in proof.items()
                      if key != 'qt_translation_files'}, sort_keys=True))


if __name__ == '__main__':
    main()
