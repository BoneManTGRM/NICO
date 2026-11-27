"""Seal protected-build type inputs for exact owned assessments; never run code.

The pin must come from an independently verified protected-build receipt, or a
reviewed immutable build pin. Neither archive metadata nor a target checkout is
an authority. Successful admission is not an assessment/compiler result.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from io import BytesIO
import json
import os
from re import fullmatch
import stat
from types import MappingProxyType
import zipfile

REPO = 'BoneManTGRM/NICO'
SCHEMA = 'nico.private-typegen-inputs.v1'
NAMES = frozenset({'cache-life.d.ts', 'root-params.d.ts', 'routes.d.ts', 'validator.ts'})
HISTORICAL_COMMIT = '5eb768b5776f88bae86e972c76267915cc874c85'
HISTORICAL_TREE = 'fd4170b422a9f623c286e9e1f3c08e01b0ec821c'
HISTORICAL_PACKAGE = '091a04fa67c7907b98e106fcff8b964e13129754fce72d24f3025b97c4887fa3'
MAX_FILE = 1024 * 1024
MAX_SUM = 2 * 1024 * 1024
MAX_MANIFEST = 4096
MAX_ARCHIVE = MAX_SUM + 8192
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')


def _hex(value, count):
    return isinstance(value, str) and fullmatch(f'[0-9a-f]{{{count}}}', value) is not None


@dataclass(frozen=True)
class TrustedTypegenPin:
    """Expected metadata and expected bytes, provided independently of the archive."""
    producer_commit: str
    target_commit: str
    target_tree: str
    source_inventory_sha256: str
    target_receipt_sha256: str
    # Sorted tuple is immutable; no implicit last-write-wins if an entry repeats.
    generated_hashes: tuple[tuple[str, str], ...]

    def manifest(self):
        entries = dict(self.generated_hashes)
        historical = self.target_commit == HISTORICAL_COMMIT
        names = NAMES | {'package.json'} if historical else NAMES
        if historical and (self.target_tree != HISTORICAL_TREE
                           or entries.get('package.json') != HISTORICAL_PACKAGE):
            raise ValueError('typegen_build_metadata_pin_invalid')
        if (not all(_hex(v, 40) for v in (self.producer_commit, self.target_commit, self.target_tree))
                or not _hex(self.source_inventory_sha256, 64) or not _hex(self.target_receipt_sha256, 64)
                or set(entries) != names or tuple(sorted(entries.items())) != self.generated_hashes
                or not all(_hex(value, 64) for value in entries.values())):
            raise ValueError('typegen_pin_invalid')
        return _json({'schema': SCHEMA, 'repository': REPO, 'producer_commit': self.producer_commit,
                      'target_commit': self.target_commit, 'target_tree': self.target_tree,
                      'source_inventory_sha256': self.source_inventory_sha256,
                      'target_receipt_sha256': self.target_receipt_sha256,
                      'generated_inputs': entries})


def inventory_digest(verified_source_inventory):
    """Hash a caller-verified complete Git source inventory, without altering it."""
    if (not 0 < len(verified_source_inventory) <= 10000
            or any(not isinstance(name, str) or not name or not _hex(value, 64)
                   for name, value in verified_source_inventory.items())):
        raise ValueError('typegen_source_inventory_invalid')
    return sha256(_json(verified_source_inventory)).hexdigest()


def _stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_inputs(root_fd, expected):
    # The build controller supplies the trusted repository root descriptor.
    # Open every subdirectory and leaf relative to the preceding descriptor.
    dirs = []
    try:
        directory = root_fd
        for segment in ('apps', 'web', '.next', 'types'):
            directory = os.open(segment, _DIRECTORY, dir_fd=directory)
            dirs.append(directory)
        directory_before = os.fstat(directory)
        build_directory_before = os.fstat(dirs[-2])
        if set(os.listdir(directory)) != NAMES:
            raise ValueError('typegen_generated_set_mismatch')
        output, total = {}, 0
        for name in sorted(expected):
            parent = dirs[-2] if name == 'package.json' else directory
            fd = os.open(name, _FILE, dir_fd=parent)
            try:
                start = os.fstat(fd)
                if (not stat.S_ISREG(start.st_mode) or start.st_nlink != 1
                        or not 0 < start.st_size <= MAX_FILE or total + start.st_size > MAX_SUM):
                    raise ValueError('typegen_file_boundary')
                payload = bytearray()
                while len(payload) <= start.st_size:
                    chunk = os.read(fd, min(65536, start.st_size + 1 - len(payload)))
                    if not chunk:
                        break
                    payload.extend(chunk)
                if len(payload) != start.st_size or _stamp(os.fstat(fd)) != _stamp(start):
                    raise ValueError('typegen_file_changed')
            finally:
                os.close(fd)
            if not compare_digest(sha256(payload).hexdigest(), expected[name]):
                raise ValueError('typegen_file_digest_mismatch')
            output[name] = bytes(payload)
            total += len(payload)
        if (_stamp(os.fstat(directory)) != _stamp(directory_before)
                or _stamp(os.fstat(dirs[-2])) != _stamp(build_directory_before)):
            raise ValueError('typegen_directory_changed')
        return output
    finally:
        for fd in reversed(dirs):
            os.close(fd)


def _pack(manifest, inputs):
    sink = BytesIO()
    with zipfile.ZipFile(sink, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in (('manifest.json', manifest), *sorted(inputs.items())):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, data)
    raw = sink.getvalue()
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('typegen_archive_budget')
    return raw


def seal_private_build_inputs(trusted_root_fd: int, pin: TrustedTypegenPin) -> bytes:
    """Build-only: seal exact generated bytes into a deterministic private bundle."""
    manifest = pin.manifest()
    inputs = _read_inputs(trusted_root_fd, dict(pin.generated_hashes))
    return _pack(manifest, inputs)


def admit_private_build_inputs(raw: bytes, pin: TrustedTypegenPin, *,
                               assessed_commit: str, assessed_tree: str,
                               verified_source_inventory):
    """Read-only rehearsal/consumer: fail closed before exposing any verified bytes."""
    expected_manifest = pin.manifest()
    if (assessed_commit != pin.target_commit or assessed_tree != pin.target_tree
            or not compare_digest(inventory_digest(verified_source_inventory), pin.source_inventory_sha256)):
        raise ValueError('typegen_assessment_identity_mismatch')
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE:
        raise ValueError('typegen_archive_budget')
    expected = dict(pin.generated_hashes)
    payload, total = {}, 0
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != len(expected) + 1 or {a.filename for a in entries} != set(expected) | {'manifest.json'}:
                raise ValueError('typegen_archive_member_set')
            for info in entries:
                name = info.filename
                limit = MAX_MANIFEST if name == 'manifest.json' else MAX_FILE
                if (not 0 < info.file_size <= limit or info.flag_bits != 0
                        or not stat.S_ISREG(info.external_attr >> 16)
                        or info.compress_type != zipfile.ZIP_STORED or info.compress_size != info.file_size):
                    raise ValueError('typegen_archive_member_boundary')
                with archive.open(info) as stream:
                    content = stream.read(limit + 1)
                if len(content) != info.file_size:
                    raise ValueError('typegen_archive_member_size')
                if name == 'manifest.json':
                    if not compare_digest(content, expected_manifest):
                        raise ValueError('typegen_archive_manifest_mismatch')
                    continue
                total += len(content)
                if total > MAX_SUM or not compare_digest(sha256(content).hexdigest(), expected[name]):
                    raise ValueError('typegen_archive_member_digest')
                payload[name] = content
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError('typegen_archive_invalid') from exc
    if not compare_digest(raw, _pack(expected_manifest, payload)):
        raise ValueError('typegen_archive_encoding_mismatch')
    return MappingProxyType(payload)
