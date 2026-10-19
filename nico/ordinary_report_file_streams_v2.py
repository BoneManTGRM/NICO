"""Dormant path-backed v2 ZIP transport; no installer, storage or approval authority.

Stack dependency: PR1784 head 1d798c6d. Existing logical limits are unchanged.
Only ZIP/member I/O is streamed. Canonical JSON and bounded PDF validation still
materialize objects; callers must qualify worker memory/time before installation.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import hashlib
import os
from pathlib import Path
import secrets
import stat
import time
from typing import Mapping
import zipfile

from nico import ordinary_report_files_v2 as transport
from nico import ordinary_review_bundle_v2 as core

CHUNK_BYTES = 64 * 1024


def _absolute(path):
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('report_files_parent_path')
    return Path(os.path.abspath(path))


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _directory(path):
    """Pin an absolute directory through no-follow opens of every component."""
    path = _absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _same_directory(path, fd):
    with _directory(path) as current:
        a, b = os.fstat(current), os.fstat(fd)
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
            raise ValueError('report_files_directory_changed')


@contextmanager
def _source(path, maximum):
    path = _absolute(path)
    with _directory(path.parent) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or not 0 < initial.st_size <= maximum:
                raise ValueError('report_files_source_limit_or_type')
            def unchanged():
                _same_directory(path.parent, directory)
                current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                if _signature(initial) != _signature(current) or _signature(initial) != _signature(os.fstat(stream.fileno())):
                    raise ValueError('report_files_source_changed')
            yield stream, initial.st_size, unchanged
            unchanged()


def _read(stream, maximum, started, *, sink=None, retain=False):
    digest = hashlib.sha256()
    count = 0
    data = bytearray() if retain else None
    while True:
        core._tick(started)
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        count += len(chunk)
        if count > maximum:
            raise ValueError('report_files_byte_limit')
        digest.update(chunk)
        if sink is not None:
            sink.write(chunk)
        if data is not None:
            data.extend(chunk)
    return count, digest.hexdigest(), bytes(data) if data is not None else None


def _receipt(path, size, digest, manifest, manifest_digest, started, canonical_seconds):
    return {'archive_path': str(path), 'archive_size_bytes': size, 'archive_sha256': digest,
            'manifest': manifest, 'manifest_sha256': manifest_digest,
            'approval_status': 'pending_human_approval', 'client_delivery_allowed': False,
            'transport_seconds': time.monotonic() - started,
            'canonical_validation_seconds': canonical_seconds,
            'canonical_validation_materializes_json': True}


def _validate_open(stream, size, *, expected_identity, expected_manifest_sha256, started):
    """Validate full logical content with existing v2 truth/PDF validators."""
    identity = core._identity(expected_identity)
    stream.seek(0)
    actual_size, archive_digest, _ = _read(stream, transport.MAX_FAMILY_BYTES, started)
    if actual_size != size:
        raise ValueError('report_files_source_changed')
    stream.seek(0)
    with zipfile.ZipFile(stream) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or not 11 <= len(names) <= core.MAX_VOLUMES + 10:
            raise ValueError('report_files_zip_population')
        if any(item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16) for item in infos):
            raise ValueError('report_files_zip_member_type')
        if sum(item.file_size for item in infos) > transport.MAX_FAMILY_BYTES:
            raise ValueError('report_files_zip_limit')
        if transport.MANIFEST_NAME not in names:
            raise ValueError('report_files_manifest_missing')
        with archive.open(transport.MANIFEST_NAME) as member:
            _, digest, raw = _read(member, transport.MAX_FAMILY_BYTES, started, retain=True)
        if digest != expected_manifest_sha256:
            raise ValueError('report_files_manifest_digest')
        manifest = transport._json_object(raw)
        if set(manifest) != {'artifact_schema', 'identity', 'bundle_manifest_sha256', 'approval_status', 'client_delivery_allowed', 'artifacts'}:
            raise ValueError('report_files_manifest_fields')
        if core._sha(core._json(manifest)) != expected_manifest_sha256:
            raise ValueError('report_files_manifest_digest')
        if manifest['artifact_schema'] != transport.SCHEMA or manifest['identity'] != identity:
            raise ValueError('report_files_identity')
        if manifest['approval_status'] != 'pending_human_approval' or manifest['client_delivery_allowed'] is not False:
            raise ValueError('report_files_review_only')
        entries = manifest['artifacts']
        if not isinstance(entries, list) or not 10 <= len(entries) <= core.MAX_VOLUMES + 9:
            raise ValueError('report_files_population')
        volume_count = len(entries) - 9
        pdf_names = [f"volume-{n:03d}-{identity['report_language']}.pdf" for n in range(1, volume_count + 1)]
        expected_names = pdf_names + list(transport.EXPORT_NAMES.values()) + ['bundle-manifest.json', 'artifact-identity.json']
        kinds = ['pdf_volume'] * volume_count + list(transport.EXPORT_NAMES) + ['bundle_manifest', 'artifact_identity']
        if names != sorted(expected_names + [transport.MANIFEST_NAME]):
            raise ValueError('report_files_zip_members')
        total, text_total, pdf_total = len(raw), 0, 0
        retained, pdfs = {}, []
        for entry, name, kind in zip(entries, expected_names, kinds, strict=True):
            if set(entry) != {'artifact_type', 'filename', 'sha256', 'size_bytes'} or entry['filename'] != name or entry['artifact_type'] != kind:
                raise ValueError('report_files_member_order')
            if type(entry['size_bytes']) is not int or entry['size_bytes'] <= 0 or archive.getinfo(name).file_size != entry['size_bytes']:
                raise ValueError('report_files_member_size')
            limit = transport.MAX_TEXT_BYTES if kind in transport.EXPORT_NAMES else core.MAX_BYTES if kind == 'pdf_volume' else transport.MAX_FAMILY_BYTES
            declared = entry['size_bytes']
            if (declared > limit or total + declared > transport.MAX_FAMILY_BYTES
                    or (kind in transport.EXPORT_NAMES and text_total + declared > transport.MAX_TEXT_BYTES)
                    or (kind == 'pdf_volume' and pdf_total + declared > core.MAX_BYTES)):
                raise ValueError('report_files_byte_limit')
            keep = kind in {'pdf_volume', 'canonical_json', 'bundle_manifest', 'artifact_identity'}
            with archive.open(name) as member:
                count, digest, data = _read(member, limit, started, retain=keep)
            if count != entry['size_bytes'] or digest != entry['sha256']:
                raise ValueError('report_files_member_digest')
            total += count
            text_total += count if kind in transport.EXPORT_NAMES else 0
            pdf_total += count if kind == 'pdf_volume' else 0
            if total > transport.MAX_FAMILY_BYTES or text_total > transport.MAX_TEXT_BYTES or pdf_total > core.MAX_BYTES:
                raise ValueError('report_files_byte_limit')
            if kind == 'pdf_volume':
                pdfs.append({'filename': name, 'pdf_base64': base64.b64encode(data).decode('ascii')})
            elif keep:
                retained[name] = data
        canonical_started = time.monotonic()
        transport._canonical_identity(retained['canonical.json'], identity)
        canonical_seconds = time.monotonic() - canonical_started
        raw_bundle = retained['bundle-manifest.json']
        if core._sha(raw_bundle) != manifest['bundle_manifest_sha256']:
            raise ValueError('report_files_bundle_manifest_digest')
        bundle = {'manifest': transport._json_object(raw_bundle), 'manifest_sha256': manifest['bundle_manifest_sha256'], 'files': pdfs}
        core.validate_review_bundle(bundle, expected_identity=identity, expected_manifest_sha256=manifest['bundle_manifest_sha256'])
        metadata = {'artifact_schema': transport.SCHEMA, 'identity': identity,
                    'bundle_manifest_sha256': manifest['bundle_manifest_sha256'],
                    'approval_status': 'pending_human_approval', 'client_delivery_allowed': False}
        if retained['artifact-identity.json'] != core._json(metadata):
            raise ValueError('report_files_identity_metadata')
        core._tick(started)
        return _receipt('', size, archive_digest, manifest, expected_manifest_sha256, started, canonical_seconds)


def validate_report_files_zip_path(archive: Path, *, expected_identity, expected_manifest_sha256):
    """Expected digest must come from protected retained evidence, not the ZIP."""
    started = time.monotonic()
    try:
        with _source(archive, transport.MAX_FAMILY_BYTES) as (stream, size, unchanged):
            receipt = _validate_open(stream, size, expected_identity=expected_identity,
                                     expected_manifest_sha256=expected_manifest_sha256, started=started)
            unchanged()
            receipt['archive_path'] = str(_absolute(archive))
            return receipt
    except (KeyError, TypeError, AttributeError, UnicodeError, zipfile.BadZipFile) as exc:
        raise ValueError('report_files_invalid_structure') from exc


def write_report_files_zip_from_paths(bundle, export_paths: Mapping[str, Path], destination: Path, *,
                                     expected_identity, expected_bundle_manifest_sha256):
    """Publish one fully verified archive with atomic no-overwrite link semantics.

    Parent directories must be caller-owned trusted staging directories. No path
    component may be a symlink. Crash-before-publication can leave a private temp
    file, but never a partially written final archive or a returned ready receipt.
    """
    started = time.monotonic()
    core.validate_review_bundle(bundle, expected_identity=expected_identity,
                                expected_manifest_sha256=expected_bundle_manifest_sha256)
    identity = core._identity(expected_identity)
    if set(export_paths) != set(transport.EXPORT_NAMES):
        raise ValueError('report_files_export_population')
    destination = _absolute(destination)
    with ExitStack() as stack:
        directory = stack.enter_context(_directory(destination.parent))
        try:
            os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(destination)
        members, artifacts = {}, []
        def add(kind, name, size, digest, data):
            members[name] = data
            artifacts.append({'artifact_type': kind, 'filename': name, 'sha256': digest, 'size_bytes': size})
        for pdf in bundle['files']:
            data = base64.b64decode(pdf['pdf_base64'], validate=True)
            add('pdf_volume', pdf['filename'], len(data), core._sha(data), data)
        source_stack = stack.enter_context(ExitStack())
        sources = {}
        text_size = 0
        for kind, name in transport.EXPORT_NAMES.items():
            stream, size, unchanged = source_stack.enter_context(_source(export_paths[kind], transport.MAX_TEXT_BYTES))
            count, digest, _ = _read(stream, transport.MAX_TEXT_BYTES, started)
            unchanged()
            if count != size:
                raise ValueError('report_files_source_changed')
            text_size += size
            if text_size > transport.MAX_TEXT_BYTES:
                raise ValueError('report_files_byte_limit')
            sources[name] = (stream, unchanged)
            add(kind, name, size, digest, None)
        metadata = {'artifact_schema': transport.SCHEMA, 'identity': identity,
                    'bundle_manifest_sha256': expected_bundle_manifest_sha256,
                    'approval_status': 'pending_human_approval', 'client_delivery_allowed': False}
        for kind, name, data in [('bundle_manifest', 'bundle-manifest.json', core._json(bundle['manifest'])),
                                 ('artifact_identity', 'artifact-identity.json', core._json(metadata))]:
            add(kind, name, len(data), core._sha(data), data)
        manifest = {**metadata, 'artifacts': artifacts}
        raw_manifest = core._json(manifest)
        manifest_digest = core._sha(raw_manifest)
        members[transport.MANIFEST_NAME] = raw_manifest
        if sum(item['size_bytes'] for item in artifacts) + len(raw_manifest) > transport.MAX_FAMILY_BYTES:
            raise ValueError('report_files_byte_limit')
        expected = {item['filename']: item for item in artifacts}
        temporary = '.nico-family-' + secrets.token_hex(16) + '.tmp'
        fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'w+b') as output:
                with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
                    for name in sorted(members):
                        core._tick(started)
                        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = 0o600 << 16
                        info.create_system = 3
                        info.file_size = expected[name]['size_bytes'] if name in expected else len(raw_manifest)
                        with zipped.open(info, 'w') as target:
                            if name in sources:
                                stream, unchanged = sources[name]
                                unchanged()
                                stream.seek(0)
                                count, digest, _ = _read(stream, transport.MAX_TEXT_BYTES, started, sink=target)
                                unchanged()
                                if count != expected[name]['size_bytes'] or digest != expected[name]['sha256']:
                                    raise ValueError('report_files_source_changed')
                            else:
                                data = members[name]
                                for offset in range(0, len(data), CHUNK_BYTES):
                                    core._tick(started)
                                    target.write(data[offset:offset + CHUNK_BYTES])
                                    if output.tell() > transport.MAX_FAMILY_BYTES:
                                        raise ValueError('report_files_byte_limit')
                        if output.tell() > transport.MAX_FAMILY_BYTES:
                            raise ValueError('report_files_byte_limit')
                size = output.tell()
                if size > transport.MAX_FAMILY_BYTES:
                    raise ValueError('report_files_byte_limit')
                output.flush()
                os.fsync(output.fileno())
                receipt = _validate_open(output, size, expected_identity=identity,
                                         expected_manifest_sha256=manifest_digest, started=started)
                for _, unchanged in sources.values():
                    unchanged()
                source_stack.close()
                _same_directory(destination.parent, directory)
                core._tick(started)
                os.link(temporary, destination.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                receipt['archive_path'] = str(destination)
                return receipt
        finally:
            os.unlink(temporary, dir_fd=directory)
