"""Keep only exact, supported TypeScript build inputs for the owned assessment."""
from __future__ import annotations

import argparse
from hashlib import sha256
import gzip
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from nico import nico_ci_typescript_typegen_inputs_v1 as sealer

SCHEMA = 'nico.owned-typescript-install.v1'
BASELINE_SHA = 'aec46d5ca31e19f6d7e62b65d98f8e116396782f0e164a1a7d289e5f484878f4'
REFERENCE_ARTIFACT = '4f51458ba63b7f37f85f58f0361ef62a5d6c62cd40571e3db662ae539ece9e6e'
MAX_MEMBER = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
DRIVER = 'nico_typecheck_confined_driver_v1.cjs'
HOST = 'nico_typecheck_virtual_host_v1.cjs'
WEB = 'apps/web/'
DEPS = WEB + 'node_modules/'
TS_LIB = '@compiler/lib/'
READ_COUNT = 785
SRC_COUNT = 210
DEP_COUNT = 517
LIB_COUNT = 89
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def digest(raw):
    return sha256(raw).hexdigest()


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _parts(relative):
    path = relative.split('/')
    _require(len(relative) < 1024 and relative.isascii() and not re.search(r'[\x00-\x1f\\]', relative)
             and all(s not in {'', '.', '..'} for s in path), 'invalid input path')
    return path


def _read(root, relative, expected=None, limit=MAX_MEMBER):
    parts = _parts(relative)
    dirs = [os.open(root, DIR)]
    try:
        for segment in parts[:-1]:
            dirs.append(os.open(segment, DIR, dir_fd=dirs[-1]))
        with os.fdopen(os.open(parts[-1], FILE, dir_fd=dirs[-1]), 'rb') as fd:
            before = os.fstat(fd.fileno())
            _require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'invalid input member')
            contents = fd.read(before.st_size + 1)
            after = os.fstat(fd.fileno())
        _require(len(contents) == before.st_size and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                 == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'input changed')
    finally:
        for fd in reversed(dirs):
            os.close(fd)
    _require(expected is None or digest(contents) == expected, 'input digest mismatch')
    return contents


def _baseline(path):
    compressed = _read(path.parent, path.name, limit=256*1024)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(256*1024+1)
    _require(len(raw) <= 256*1024 and digest(raw) == BASELINE_SHA, 'baseline digest mismatch')
    data = json.loads(raw)
    _require(data['source_sha'] == sealer.HISTORICAL_COMMIT and len(data['read_inputs']) == READ_COUNT,
             'historical reference identity mismatch')
    return compressed, data


def _mount_digest_bytes(mount):
    return digest(json.dumps([[p, digest(b)] for p,b in sorted(mount.items())], ensure_ascii=False,
                             separators=(',', ':')).encode())


def _mount_digest_expected(manifest):
    return digest(json.dumps([[p, h] for p,h in sorted(manifest.items())], ensure_ascii=False,
                             separators=(',', ':')).encode())


def _node_install(src, dst, expected):
    # No shell or Node module execution here. Keep no unpinned executable copy.
    with os.fdopen(os.open(src, FILE), 'rb') as input_, dst.open('xb') as output:
        start = os.fstat(input_.fileno())
        _require(stat.S_ISREG(start.st_mode) and 0 < start.st_size <= 192*1024*1024, 'Node binary boundary')
        hashed, count = sha256(), 0
        for chunk in iter(lambda: input_.read(65536), b''):
            count += len(chunk)
            _require(count <= start.st_size, 'Node binary grew')
            hashed.update(chunk)
            output.write(chunk)
        end = os.fstat(input_.fileno())
    _require(count == start.st_size and (start.st_size, start.st_mtime_ns, start.st_ctime_ns) ==
             (end.st_size, end.st_mtime_ns, end.st_ctime_ns) and hashed.hexdigest() == expected,
             'Node binary digest mismatch')
    dst.chmod(0o555)


def publish(reference, baseline, scripts, node, producer, out):
    _require(re.fullmatch('[0-9a-f]{40}', producer) is not None and producer != '0'*40,
             'missing or invalid Railway build producer')
    _require(out.is_absolute() and not out.exists(), 'output exists or is not absolute')
    compressed, known = _baseline(baseline)
    reads, inventory, compiler = known['read_inputs'], known['source_inventory'], known['compiler']
    compiler_root = reference / (DEPS + 'typescript')
    _require(compiler['version'] == '6.0.3' and compiler['node_version'] == 'v24.22.3',
             'wrong compiler pins')
    _require(compiler['entry_sha256'] == reads[TS_LIB+'typescript.js']
             and compiler['package_sha256'] == reads['@compiler/package.json'], 'compiler hash mismatch')
    sources = {p.removeprefix(WEB): h for p,h in inventory.items() if p.startswith(WEB)}
    _require(len(sources) == SRC_COUNT, 'web source inventory is incomplete')
    for name, expected in sources.items():
        _read(reference, WEB+name, expected, 4*1024*1024)
    dependencies, libraries, total = {}, {}, 0
    generated_hashes = known['generated_inputs']
    _require(all(reads.get(p) == h for p,h in generated_hashes.items()),
             'generated read inventory mismatch')
    accounted = set(generated_hashes) | {TS_LIB+'typescript.js', '@compiler/package.json', WEB+'package-lock.json'}
    for name, expectation in reads.items():
        if name in inventory:
            _require(inventory[name] == expectation, 'source read inventory mismatch')
            accounted.add(name)
    for name, expected in reads.items():
        if name.startswith(DEPS):
            target, path, fdroot = dependencies, name.removeprefix(DEPS), reference
        elif name.startswith(TS_LIB) and name.endswith('.d.ts'):
            target, path, fdroot = libraries, name.removeprefix(TS_LIB), compiler_root
        else:
            continue
        contents = _read(fdroot, name if fdroot == reference else 'lib/'+path, expected)
        total += len(contents)
        _require(total <= MAX_TOTAL, 'installed dependency byte budget')
        target[path] = contents
        accounted.add(name)
    _require(set(reads) == accounted, 'read inventory not fully accounted')
    _require(len(dependencies) == DEP_COUNT and len(libraries) == LIB_COUNT, 'read closure incomplete')
    # Verify the exact lock as part of both source and protected-read inventories.
    _read(reference, WEB+'package-lock.json', reads[WEB+'package-lock.json'])
    compiler_bytes = _read(compiler_root, 'lib/typescript.js', compiler['entry_sha256'],32*1024*1024)
    compiler_metadata = _read(compiler_root, 'package.json', compiler['package_sha256'],256*1024)
    _require(json.loads(compiler_metadata)['version'] == '6.0.3', 'compiler metadata version mismatch')
    driver, host = _read(scripts, DRIVER, limit=256*1024), _read(scripts, HOST, limit=256*1024)
    source_inventory_sha = sealer.inventory_digest(inventory)
    generated_pin = sealer.TrustedTypegenPin(
        producer, sealer.HISTORICAL_COMMIT, sealer.HISTORICAL_TREE, source_inventory_sha, REFERENCE_ARTIFACT,
        tuple(sorted((Path(p).name,h) for p,h in known['generated_inputs'].items())))
    reference_fd = os.open(reference, DIR)
    try:
        sealed = sealer.seal_private_build_inputs(reference_fd, generated_pin)
    finally:
        os.close(reference_fd)
    generated = sealer.admit_private_build_inputs(sealed, generated_pin,
        assessed_commit=sealer.HISTORICAL_COMMIT, assessed_tree=sealer.HISTORICAL_TREE,
        verified_source_inventory=inventory)
    manifest = {
        'schema': SCHEMA, 'producer_commit': producer,
        'target_commit': sealer.HISTORICAL_COMMIT, 'target_tree': sealer.HISTORICAL_TREE,
        'baseline_sha256': BASELINE_SHA, 'generated_bundle_sha256': digest(sealed),
        'driver_sha256': digest(driver), 'host_sha256': digest(host),
        'node_version': compiler['node_version'], 'node_sha256': compiler['node_sha256'],
        'compiler_version': compiler['version'], 'compiler_entry_sha256': compiler['entry_sha256'],
        'compiler_package_sha256': compiler['package_sha256'], 'source_inventory_sha256': source_inventory_sha,
        'mount_digests': {
            'source': _mount_digest_expected(sources), 'generated': _mount_digest_bytes(generated),
            'dependencies': _mount_digest_bytes(dependencies), 'compilerLibs': _mount_digest_bytes(libraries),
        }
    }
    # Atomic publication. An incomplete generation/build is not an installed runtime.
    with tempfile.TemporaryDirectory(prefix='.owned-typecheck-', dir=out.parent) as scratch:
        payload = Path(scratch)/'ready'
        payload.mkdir(mode=0o755)
        members = {
            'manifest.json': json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode(),
            'historical_typescript_inputs.json.gz': compressed,
            'generated.zip': sealed, 'scripts/'+DRIVER: driver, 'scripts/'+HOST: host,
            'typescript/package.json': compiler_metadata, 'typescript/lib/typescript.js': compiler_bytes,
        }
        members.update({'dependencies/'+name: serialized for name,serialized in dependencies.items()})
        members.update({'typescript/lib/'+name: serialized for name,serialized in libraries.items()})
        for name, serialized in members.items():
            _parts(name)
            file = payload/name
            file.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with file.open('xb') as fd:
                fd.write(serialized)
            file.chmod(0o444)
        _node_install(node,payload/'node',compiler['node_sha256'])
        payload.rename(out)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('reference','baseline','scripts','node','out'):
        parser.add_argument('--'+field, type=Path, required=True)
    parser.add_argument('--producer', required=True)
    options=parser.parse_args()
    publish(**vars(options))
    print(json.dumps({'owned_typescript_inputs':'packaged', 'producer_commit':options.producer,
                      'target_commit':sealer.HISTORICAL_COMMIT, 'compiler_observed':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
