"""Dormant offline TypeScript bundle verification; no acquisition or execution.

The policy/key and measured compiler identity come from an independent controller,
never from the target bundle. A valid self-declared build is not a trust anchor.
This format is not a GitHub/Sigstore attestation verifier or OS qualification.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import gzip
import hashlib
import hmac
import io
import json
from pathlib import PurePosixPath
import re
import tarfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = 'nico.typescript.offline-provenance.v1'
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_UNPACKED = 32 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 20_000
MAX_PACKAGES = 256
HEX = re.compile(r'[a-f0-9]{64}')


def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _wire(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def _digest(value): return _sha(_wire(value))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid_utf8_json') from exc


def _path(value):
    if (not isinstance(value, str) or not 0 < len(value) <= 1024
            or not all(re.fullmatch(r'[A-Za-z0-9_.@+~-]+', p) and p not in {'.', '..', '.git'} for p in value.split('/'))):
        raise ValueError('bundle_path_boundary')
    return value


def _inventory(files):
    if not isinstance(files, dict) or len(files) > MAX_FILES: raise ValueError('bundle_file_budget')
    total = 0
    output = {}
    for name, raw in files.items():
        _path(name)
        if not isinstance(raw, bytes): raise ValueError('bundle_regular_bytes_required')
        total += len(raw)
        if total > MAX_TOTAL: raise ValueError('bundle_byte_budget')
        output[name] = _sha(raw)
    return output


def _archive_inventory(raw):
    """Inspect bounded archive bytes; never extract paths or execute contents."""
    if not isinstance(raw, bytes) or len(raw) > MAX_ARCHIVE: raise ValueError('archive_byte_budget')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
            unpacked = zipped.read(MAX_UNPACKED + 1)
        if len(unpacked) > MAX_UNPACKED: raise ValueError('archive_unpacked_budget')
        files = {}; seen = set(); directories = set()
        with tarfile.open(fileobj=io.BytesIO(unpacked), mode='r:') as archive:
            for entry in archive:
                if (entry.pax_headers or archive.pax_headers
                        or unpacked[entry.offset+156:entry.offset+157] not in {b'0', b'\x00', b'5'}):
                    raise ValueError('unsupported_archive_metadata')
                name = entry.name.rstrip('/') if entry.isdir() else entry.name
                _path(name)
                if name in seen: raise ValueError('duplicate_archive_path')
                seen.add(name)
                if len(seen) > MAX_FILES: raise ValueError('archive_entry_budget')
                if name == 'package' and entry.isdir(): continue
                if not name.startswith('package/'): raise ValueError('archive_package_root')
                relative = _path(name[len('package/'):])
                if entry.isdir(): directories.add(relative); continue
                if not entry.isfile() or entry.size < 0 or entry.size > MAX_UNPACKED:
                    raise ValueError('archive_nonregular_or_oversize')
                stream = archive.extractfile(entry)
                if stream is None: raise ValueError('archive_missing_payload')
                payload = stream.read(entry.size + 1)
                if len(payload) != entry.size: raise ValueError('archive_payload_size')
                files[relative] = payload
        for name in set(files) | directories:
            if any(str(p) in files for p in PurePosixPath(name).parents if str(p) != '.'):
                raise ValueError('archive_file_directory_conflict')
        if 'package.json' not in files: raise ValueError('archive_package_metadata_missing')
        return files
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise ValueError('archive_format_invalid') from exc


@dataclass(frozen=True)
class BundlePolicy:
    source: dict
    compiler: dict
    build: dict
    generator: dict
    source_inventory: dict[str, str]
    required_generated_paths: frozenset[str]
    key_id: str
    public_key: bytes


def verify_offline_bundle(*, source_files, packages, generated_files, envelope, policy: BundlePolicy, compiler_identity):
    """Return content/provenance verification only, never analysis or execution credit."""
    if not isinstance(envelope, dict) or set(envelope) != {'key_id', 'statement', 'signature'}:
        raise ValueError('provenance_envelope_schema')
    if envelope['key_id'] != policy.key_id or not policy.key_id: raise ValueError('untrusted_provenance_key')
    statement = envelope['statement']
    fields = {'schema','source','compiler','build','generator','lockfile','source_inventory_sha256',
              'package_inventory_sha256','generated_inventory_sha256','package_inventory_complete','generated_inventory_complete'}
    if not isinstance(statement, dict) or set(statement) != fields or statement['schema'] != SCHEMA:
        raise ValueError('provenance_statement_schema')
    signed = _wire(statement)
    if len(signed) > 64*1024: raise ValueError('provenance_statement_budget')
    try:
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(policy.public_key).verify(signature, signed)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValueError('provenance_signature_invalid') from exc
    for field in ('source','compiler','build','generator'):
        if statement[field] != getattr(policy, field): raise ValueError('provenance_'+field+'_mismatch')
    if compiler_identity != policy.compiler: raise ValueError('measured_compiler_mismatch')
    source = statement['source']; compiler = statement['compiler']; build = statement['build']; generator = statement['generator']
    if (set(source) != {'repository','commit_sha','tree_sha','run_id','snapshot_id'}
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source['repository'])
            or any(not re.fullmatch(r'[a-f0-9]{40}', source[k]) for k in ('commit_sha','tree_sha'))
            or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', source[k]) for k in ('run_id','snapshot_id'))):
        raise ValueError('source_identity_schema')
    if (set(compiler) != {'version','package_sha256','compiler_sha256','libraries_sha256','node_sha256'}
            or compiler['version'] != '6.0.3' or any(not HEX.fullmatch(compiler[k]) for k in compiler if k != 'version')):
        raise ValueError('compiler_identity_schema')
    if (set(build) != {'provider','repository','workflow_path','workflow_sha','run_id','attempt','conclusion'}
            or build['provider'] != 'github-actions' or build['repository'] != source['repository']
            or build['conclusion'] != 'success' or not re.fullmatch(r'[a-f0-9]{40}', build['workflow_sha'])
            or not re.fullmatch(r'[1-9][0-9]{0,19}', build['run_id']) or type(build['attempt']) is not int or build['attempt'] < 1
            or not _path(build['workflow_path']).startswith('.github/workflows/')):
        raise ValueError('authorized_build_identity_schema')
    if statement['package_inventory_complete'] is not True or statement['generated_inventory_complete'] is not True:
        raise ValueError('incomplete_offline_inventory')
    source_inventory = _inventory(source_files)
    if any('node_modules' in name.split('/') for name in source_inventory):
        raise ValueError('source_dependency_namespace_conflict')
    if source_inventory != policy.source_inventory or _digest(source_inventory) != statement['source_inventory_sha256']:
        raise ValueError('source_inventory_mismatch')
    lock_binding = statement['lockfile']
    if not isinstance(lock_binding, dict) or set(lock_binding) != {'path','sha256'}:
        raise ValueError('lockfile_binding_schema')
    lock_path = _path(lock_binding['path'])
    if PurePosixPath(lock_path).name != 'package-lock.json' or source_inventory.get(lock_path) != lock_binding['sha256']:
        raise ValueError('lockfile_identity_mismatch')
    lock = _json(source_files[lock_path])
    if (not isinstance(lock, dict) or type(lock.get('lockfileVersion')) is not int
            or lock['lockfileVersion'] != 3 or not isinstance(lock.get('packages'), dict)):
        raise ValueError('unsupported_lockfile')
    locked = {p: item for p, item in lock['packages'].items() if p}
    if '' not in lock['packages'] or not isinstance(packages, dict) or set(packages) != set(locked) or len(packages) > MAX_PACKAGES:
        raise ValueError('package_closure_mismatch')
    inventories = {}; contents = {}; compressed_total = 0; extracted_total = 0; entry_total = 0
    for location, entry in sorted(locked.items()):
        _path(location)
        if not location.startswith('node_modules/') or not isinstance(entry, dict) or entry.get('link'):
            raise ValueError('unsupported_package_location')
        expected_name = location.rsplit('node_modules/', 1)[-1]
        if (not re.fullmatch(r'(?:@[A-Za-z0-9_.~-]+/)?[A-Za-z0-9_.~-]+', expected_name)
                or not isinstance(entry.get('version'), str) or not entry['version']
                or not isinstance(entry.get('resolved'), str) or not entry['resolved'].startswith('https://registry.npmjs.org/')
                or not isinstance(entry.get('integrity'), str) or not entry['integrity'].startswith('sha512-')):
            raise ValueError('unsupported_package_identity')
        packed = packages[location]
        if not isinstance(packed, bytes): raise ValueError('package_bytes_required')
        compressed_total += len(packed)
        if compressed_total > MAX_TOTAL: raise ValueError('package_aggregate_budget')
        try: expected = base64.b64decode(entry['integrity'][7:], validate=True)
        except ValueError as exc: raise ValueError('package_integrity_format') from exc
        if len(expected) != 64 or not hmac.compare_digest(hashlib.sha512(packed).digest(), expected):
            raise ValueError('package_integrity_mismatch')
        files = _archive_inventory(packed)
        extracted_total += sum(len(raw) for raw in files.values()); entry_total += len(files)
        if extracted_total > MAX_TOTAL or entry_total > MAX_FILES: raise ValueError('package_extracted_aggregate_budget')
        metadata = _json(files['package.json'])
        if not isinstance(metadata, dict) or metadata.get('name') != expected_name or metadata.get('version') != entry['version']:
            raise ValueError('package_metadata_mismatch')
        if any('node_modules' in name.split('/') for name in files):
            raise ValueError('bundled_dependency_unsupported')
        inventories[location] = {'archive_sha256':_sha(packed),'integrity':entry['integrity'],'files':_inventory(files)}
        contents[location] = files
    if _digest(inventories) != statement['package_inventory_sha256']: raise ValueError('package_inventory_mismatch')
    # First supported subset: ordinary exact-version dependency graphs only.
    # npm workspace/link/peer/optional/platform/range semantics are not inferred.
    root_manifest = str(PurePosixPath(lock_path).parent / 'package.json')
    if root_manifest not in source_files: raise ValueError('root_manifest_missing')
    metadata_by_path = {'': _json(source_files[root_manifest]), **{p:_json(v['package.json']) for p,v in contents.items()}}
    for location, entry in lock['packages'].items():
        metadata = metadata_by_path[location]
        if not isinstance(entry, dict) or not isinstance(metadata, dict): raise ValueError('package_graph_schema')
        unsupported = ('peerDependencies','peerDependenciesMeta','optionalDependencies','workspaces','bundledDependencies','bundleDependencies','os','cpu','libc')
        if any(entry.get(k) or metadata.get(k) for k in unsupported) or any(entry.get(k) for k in ('link','optional','inBundle')):
            raise ValueError('unsupported_lockfile_install_semantics')
        sections = ('dependencies','devDependencies') if location == '' else ('dependencies',)
        for section in sections:
            deps = metadata.get(section, {})
            if not isinstance(deps, dict) or deps != entry.get(section, {}): raise ValueError('package_dependency_declaration_conflict')
            for name, version in deps.items():
                if (not re.fullmatch(r'(?:@[A-Za-z0-9_.~-]+/)?[A-Za-z0-9_.~-]+', name)
                        or not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',version)):
                    raise ValueError('unsupported_dependency_range_or_alias')
                parts = location.split('/') if location else []
                candidates = []
                while parts:
                    if parts[-1] != 'node_modules': candidates.append('/'.join(parts)+'/node_modules/'+name)
                    parts.pop()
                candidates.append('node_modules/'+name)
                resolved = next((p for p in candidates if p in locked), None)
                if resolved is None or locked[resolved]['version'] != version:
                    raise ValueError('dependency_graph_incomplete_or_conflicting')
    if (set(generator) != {'package_path','version','entry_path','entry_sha256','config_path','config_sha256'}
            or generator['package_path'] not in contents
            or locked[generator['package_path']]['version'] != generator['version']
            or inventories[generator['package_path']]['files'].get(_path(generator['entry_path'])) != generator['entry_sha256']
            or source_inventory.get(_path(generator['config_path'])) != generator['config_sha256']):
        raise ValueError('generator_binding_mismatch')
    generated_inventory = _inventory(generated_files)
    if not policy.required_generated_paths or not policy.required_generated_paths <= generated_inventory.keys():
        raise ValueError('required_generated_inputs_missing')
    generated_prefix = str(PurePosixPath(generator['config_path']).parent / '.next/types') + '/'
    for name in generated_inventory:
        if (not name.endswith('.d.ts') or not name.startswith(generated_prefix) or 'node_modules' in name.split('/') or name in source_inventory):
            raise ValueError('generated_input_boundary_or_conflict')
        try: generated_files[name].decode('utf-8')
        except UnicodeError as exc: raise ValueError('generated_declaration_encoding') from exc
    if _digest(generated_inventory) != statement['generated_inventory_sha256']: raise ValueError('generated_inventory_mismatch')
    result = {'schema':SCHEMA,'verified':True,'verification_scope':'controller_signature_and_frozen_bytes',
              'source':dict(source),'compiler':dict(compiler),'build':dict(build),'lockfile':dict(lock_binding),
              'statement_sha256':_sha(signed),'source_inventory_sha256':_digest(source_inventory),
              'package_inventory_sha256':_digest(inventories),'generated_inventory_sha256':_digest(generated_inventory),
              'package_count':len(inventories),'generated_count':len(generated_inventory),
              'os_isolation_verified':False,'qualified_for_production':False}
    result['receipt_sha256'] = _digest(result)
    return result
