"""Validate retained collection tools without loading or executing their bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path


def verify(directory: Path) -> dict:
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise ValueError('collection_export_directory_invalid')
    files = {}
    total = 0
    for path in sorted(directory.rglob('*')):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError('collection_export_nonregular_file')
        name = path.relative_to(directory).as_posix()
        limit = 32 * 1024 * 1024 if name == 'cppcheck' else (
            4 * 1024 * 1024 if name == 'nico-clang-header-observer.so' else 1024 * 1024)
        size = path.stat().st_size
        total += size
        if size > limit or total > 64 * 1024 * 1024 or len(files) >= 1024:
            raise ValueError('collection_export_size_limit')
        raw = path.read_bytes()
        if len(raw) != size:
            raise ValueError('collection_export_file_changed')
        files[name] = {'size_bytes': size, 'sha256': hashlib.sha256(raw).hexdigest()}
    required = {'cppcheck', 'COPYING', 'repair.json', 'nico-clang-header-observer.so',
                'clang-header-observer.json', 'image-config-digest.txt', 'image.json'}
    if not required <= files.keys() or any(not files[name]['size_bytes'] for name in required):
        raise ValueError('collection_export_required_file_missing')
    if not all(any(name.startswith(prefix + '/') for name in files) for prefix in ('cfg', 'platforms')):
        raise ValueError('collection_export_models_missing')
    image = (directory / 'image-config-digest.txt').read_text().strip()
    metadata = json.loads((directory / 'image.json').read_bytes())
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', image) or not isinstance(metadata, list)
            or len(metadata) != 1 or metadata[0].get('Id') != image):
        raise ValueError('collection_export_image_mismatch')
    receipt = json.loads((directory / 'clang-header-observer.json').read_bytes())
    if (receipt.get('schema') != 'nico.clang-header-tool.v1'
            or receipt.get('plugin_sha256') != files['nico-clang-header-observer.so']['sha256']):
        raise ValueError('collection_export_observer_mismatch')
    return {'schema': 'nico.cpp-collection-tool-export.v1', 'image_config_digest': image,
            'files': files, 'qualification_completed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), sort_keys=True, indent=2))
