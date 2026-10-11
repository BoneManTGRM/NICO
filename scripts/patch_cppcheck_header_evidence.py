"""Apply one hash-pinned observer patch to the trusted Cppcheck dependency."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MANIFEST_SHA256 = 'cbe13e1183c4e44e398943bcbbe2c68e2cebd984f1bbe694d245a3b7a765f5f4'
SOURCES = frozenset({'externals/simplecpp/simplecpp.cpp', 'externals/simplecpp/simplecpp.h',
    'lib/cppcheck.cpp', 'lib/cppcheck.h', 'lib/preprocessor.cpp', 'lib/preprocessor.h'})
LIMIT = 2 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stable(path, limit=LIMIT):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path or path.is_symlink():
        raise ValueError('header_tool_source_path_invalid')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError('header_tool_source_invalid')
        raw = os.read(fd, limit + 1)
        after = os.fstat(fd)
        if len(raw) != before.st_size or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('header_tool_source_changed')
        return raw, stat.S_IMODE(before.st_mode)
    finally:
        os.close(fd)


def patched_sources(patch, originals):
    """Literal unified hunks only; never execute patch scripts or shell code."""
    lines = patch.decode('utf-8', 'strict').splitlines(keepends=True)
    results, position = {}, 0
    while position < len(lines):
        match = re.fullmatch(r'diff --git a/(\S+) b/(\S+)\n', lines[position])
        if not match or match[1] != match[2] or match[1] not in originals or match[1] in results:
            raise ValueError('header_tool_patch_invalid')
        name = match[1]; position += 1
        if position < len(lines) and lines[position].startswith('index '):
            position += 1
        if lines[position:position+2] != ['--- a/' + name + '\n', '+++ b/' + name + '\n']:
            raise ValueError('header_tool_patch_invalid')
        position += 2
        original = originals[name].decode('utf-8', 'strict').splitlines(keepends=True)
        output, consumed = [], 0
        while position < len(lines) and not lines[position].startswith('diff --git '):
            hunk = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[position])
            if not hunk:
                raise ValueError('header_tool_patch_invalid')
            old_start, old_count = int(hunk[1])-1, int(hunk[2] or '1')
            new_start, new_count = int(hunk[3])-1, int(hunk[4] or '1')
            if not consumed <= old_start <= len(original):
                raise ValueError('header_tool_patch_invalid')
            output.extend(original[consumed:old_start]); consumed = old_start
            if len(output) != new_start:
                raise ValueError('header_tool_patch_invalid')
            position += 1; removed = added = 0
            while position < len(lines) and lines[position][:1] in {' ', '+', '-'}:
                prefix, value = lines[position][0], lines[position][1:]
                if prefix in {' ', '-'}:
                    if consumed >= len(original) or original[consumed] != value:
                        raise ValueError('header_tool_patch_context_mismatch')
                    consumed += 1; removed += 1
                if prefix in {' ', '+'}:
                    output.append(value); added += 1
                position += 1
            if removed != old_count or added != new_count:
                raise ValueError('header_tool_patch_invalid')
        output.extend(original[consumed:]); results[name] = ''.join(output).encode()
    if set(results) != set(originals):
        raise ValueError('header_tool_patch_population_mismatch')
    return results


def apply_header_patch(source, bundle):
    source, bundle = Path(source).absolute(), Path(bundle).absolute()
    manifest_raw, unused = stable(bundle / 'manifest.json', 65536)
    if digest(manifest_raw) != MANIFEST_SHA256:
        raise ValueError('header_tool_manifest_mismatch')
    manifest = json.loads(manifest_raw)
    if set(manifest['sources']) != SOURCES or manifest['patch'] != 'header-token-pass-v2.patch':
        raise ValueError('header_tool_manifest_mismatch')
    patch, unused = stable(bundle / manifest['patch'], 256 * 1024)
    if digest(patch) != manifest['patch_sha256']:
        raise ValueError('header_tool_patch_digest_mismatch')
    originals, modes = {}, {}
    for name in sorted(SOURCES):
        originals[name], modes[name] = stable(source / name)
        if digest(originals[name]) != manifest['sources'][name]['before_sha256']:
            raise ValueError('header_tool_upstream_mismatch')
    results = patched_sources(patch, originals)
    for name, raw in results.items():
        if digest(raw) != manifest['sources'][name]['after_sha256'] or len(raw) > LIMIT:
            raise ValueError('header_tool_result_mismatch')
    prepared = {}
    try:
        for name, raw in results.items():
            fd, temporary = tempfile.mkstemp(prefix='.nico-header-', dir=(source / name).parent)
            prepared[name] = temporary
            with os.fdopen(fd, 'wb') as handle:
                handle.write(raw); handle.flush(); os.fchmod(handle.fileno(), modes[name]); os.fsync(handle.fileno())
        if any(stable(source / name)[0] != originals[name] for name in originals):
            raise ValueError('header_tool_upstream_changed')
        for name, temporary in prepared.items():
            os.replace(temporary, source / name)
    finally:
        for temporary in prepared.values():
            if os.path.exists(temporary): os.unlink(temporary)
    return {'schema': 'nico.cppcheck-header-tool.v1', 'manifest_sha256': MANIFEST_SHA256,
        'upstream_commit': manifest['upstream_commit'], 'patch_sha256': manifest['patch_sha256'],
        'sources': manifest['sources'], 'trace_schema': manifest['trace_schema'],
        'application_script_sha256': digest(Path(__file__).read_bytes()),
        'base_tool_version': manifest['base_tool_version'], 'qualification_completed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path); parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    print(json.dumps(apply_header_patch(args.source, args.bundle), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
