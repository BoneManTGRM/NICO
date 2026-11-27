"""Private, not wired: bridge exact source and build inputs to a confined TS process."""
from __future__ import annotations

from dataclasses import dataclass
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from types import MappingProxyType

from nico.nico_ci_typescript_typegen_inputs_v1 import REPO, TrustedTypegenPin, admit_private_build_inputs

PROTOCOL = 'nico.typescript.bridge.v1'
COMPILER_VERSION = '6.0.3'
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_INPUT_WIRE = 48 * 1024 * 1024
MAX_NATIVE_STDOUT = 4 * 1024 * 1024
MAX_NATIVE_STDERR = 32768
MAX_INPUT_MEMBERS = 12000
MAX_INPUT_MEMBER_BYTES = 8 * 1024 * 1024
TIMEOUT = 120.0
MOUNTS = ('source', 'generated', 'dependencies', 'compilerLibs')


class BoundaryUnavailable(ValueError):
    """Only relay stable reason codes from the trusted bridge."""


def _require(condition, reason):
    if not condition:
        raise BoundaryUnavailable(reason)


@dataclass(frozen=True)
class AssessedIdentity:
    repository: str
    commit: str
    tree: str


@dataclass(frozen=True)
class OwnedTypeScriptPolicy:
    """Independently reviewed, immutable, backend-only trust configuration."""
    producer_commit: str
    typegen_pin: TrustedTypegenPin
    mount_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class TrustedCompiler:
    # Exact paths are configured by the trusted parent, never a target or request.
    node: Path
    node_sha256: str
    node_version: str
    driver: Path
    driver_sha256: str
    host: Path
    host_sha256: str
    compiler_entry: Path
    compiler_entry_sha256: str
    package_json_sha256: str
    compiler_version: str


def _hex(value, count):
    return isinstance(value, str) and re.fullmatch(f'[0-9a-f]{{{count}}}', value) is not None


def _source_mount_matches_inventory(source_mount, verified_source_inventory):
    _require(len(source_mount) <= MAX_INPUT_MEMBERS and len(verified_source_inventory) <= MAX_INPUT_MEMBERS,
             'mount_member_budget')
    expected_web = {name: digest for name, digest in verified_source_inventory.items()
                    if name.startswith('apps/web/')}
    actual, total = {}, 0
    for name, raw in source_mount.items():
        _require(isinstance(name, str) and isinstance(raw, bytes), 'mount_member_invalid')
        total += len(raw)
        _require(len(raw) <= MAX_INPUT_MEMBER_BYTES and total <= MAX_INPUT_BYTES, 'mount_byte_budget')
        actual['apps/web/'+name] = sha256(raw).hexdigest()
    return bool(expected_web) and expected_web == actual


def _mount_digest(mount):
    rows = [[path, sha256(data).hexdigest()] for path, data in sorted(mount.items())]
    return sha256(json.dumps(rows, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _prepare_wire(policy, assessed, node_version, compiler_version, mounts):
    _require(set(mounts) == set(MOUNTS), 'mount_set_invalid')
    expected = dict(policy.mount_digests)
    _require(set(expected) == set(MOUNTS) and len(policy.mount_digests) == len(MOUNTS)
             and all(_hex(hash, 64) for hash in expected.values()), 'mount_policy_invalid')
    total = 0
    count = 0
    encoded = {}
    for name in MOUNTS:
        count += len(mounts[name])
        _require(0 < len(mounts[name]) and count <= MAX_INPUT_MEMBERS, 'mount_member_budget')
        mount = dict(mounts[name])
        rows = []
        for path, contents in mount.items():
            _require(isinstance(path, str) and 0 < len(path) < 1024
                     and path.isascii() and not re.search(r'[\x00-\x1f\\]', path)
                     and all(p and p not in {'.', '..'} for p in path.split('/'))
                     and isinstance(contents, bytes), 'mount_member_invalid')
            total += len(contents)
            _require(len(contents) <= MAX_INPUT_MEMBER_BYTES and total <= MAX_INPUT_BYTES,
                     'mount_byte_budget')
            rows.append((path, base64.b64encode(contents).decode('ascii')))
        _require(_mount_digest(mount) == expected[name], 'mount_digest_mismatch')
        encoded[name] = rows
    nonce = secrets.token_hex(32)
    wire = json.dumps({'protocol': PROTOCOL, 'nonce': nonce, 'node_version': node_version,
                       'assessed': {'repository': assessed.repository, 'commit': assessed.commit,
                                    'tree': assessed.tree},
                       'pin': {'repository': assessed.repository, 'commit': assessed.commit,
                               'tree': assessed.tree, 'compilerVersion': compiler_version,
                               'mountDigests': expected}, 'mounts': encoded},
                      separators=(',', ':'), ensure_ascii=False).encode()
    _require(len(wire) <= MAX_INPUT_WIRE, 'protocol_input_budget')
    return wire, nonce


def _inspect(path, expected, *, max_bytes, immutable):
    # A production call accepts only root-owned inputs in directories the launch
    # user cannot modify; do not use the repo checkout or user-writable folders.
    _require(isinstance(path, Path) and path.is_absolute()
             and path.resolve(strict=True) == path and not any(c in str(path) for c in ',*'), 'runtime_path_untrusted')
    _require(_hex(expected, 64), 'runtime_pin_invalid')
    if immutable:
        for parent in path.parents:
            info = parent.stat()
            _require(info.st_uid == 0 and not (info.st_mode & 0o022) and not os.access(parent, os.W_OK),
                     'runtime_path_not_immutable')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    digest = sha256()
    with os.fdopen(descriptor, 'rb') as reader:
        first = os.fstat(reader.fileno())
        _require(stat.S_ISREG(first.st_mode) and 0 < first.st_size <= max_bytes
                 and (not immutable or (first.st_uid == 0 and not (first.st_mode & 0o022)
                                        and not os.access(path, os.W_OK))), 'runtime_file_untrusted')
        total = 0
        for block in iter(lambda: reader.read(65536), b''):
            total += len(block)
            _require(total <= first.st_size, 'runtime_file_size_changed')
            digest.update(block)
        end = os.fstat(reader.fileno())
        _require(total == first.st_size and (first.st_dev, first.st_ino, first.st_ctime_ns, first.st_mtime_ns)
                 == (end.st_dev, end.st_ino, end.st_ctime_ns, end.st_mtime_ns), 'runtime_file_changed')
    _require(digest.hexdigest() == expected, 'runtime_file_hash_mismatch')


def _verify_runtime(runtime, *, immutable):
    _require(runtime.driver.name == 'nico_typecheck_confined_driver_v1.cjs'
             and runtime.host == runtime.driver.with_name('nico_typecheck_virtual_host_v1.cjs')
             and runtime.compiler_entry.name == 'typescript.js' and runtime.compiler_entry.parent.name == 'lib'
             and re.fullmatch(r'v24\.[0-9]+\.[0-9]+', runtime.node_version) is not None,
             'runtime_shape_invalid')
    for path, hash, limit in (
        (runtime.node, runtime.node_sha256, 256 * 1024 * 1024),
        (runtime.driver, runtime.driver_sha256, 256 * 1024),
        (runtime.host, runtime.host_sha256, 256 * 1024),
        (runtime.compiler_entry, runtime.compiler_entry_sha256, 32 * 1024 * 1024),
        (runtime.compiler_entry.parent.parent / 'package.json', runtime.package_json_sha256, 256 * 1024),
    ):
        _inspect(path, hash, max_bytes=limit, immutable=immutable)


def _capture(runtime, wire, *, timeout):
    _require(0 < timeout <= TIMEOUT, 'native_deadline_invalid')
    # No shell or PATH lookup. Stdin contains approved data, not an argv path.
    # Resolve only the three exact approved code paths, no repository mounts.
    command = [str(runtime.node), '--permission', '--max-old-space-size=640']
    for permitted in (runtime.driver, runtime.host, runtime.compiler_entry):
        command.append(f'--allow-fs-read={permitted}')
    command.extend((str(runtime.driver), str(runtime.compiler_entry)))
    buffers = [bytearray(), bytearray()]
    limit = [MAX_NATIVE_STDOUT, MAX_NATIVE_STDERR]
    end = time.monotonic() + timeout
    with tempfile.TemporaryFile() as data:
        data.write(wire)
        data.seek(0)
        proc = subprocess.Popen(command, cwd='/', stdin=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                shell=False, start_new_session=True, env={'LANG': 'C.UTF-8'})
        try:
            with selectors.DefaultSelector() as selector:
                for index, stream in enumerate((proc.stdout, proc.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, index)
                while selector.get_map() or proc.poll() is None:
                    remaining = end - time.monotonic()
                    _require(remaining > 0, 'native_timeout')
                    for item, _ in selector.select(min(remaining, 0.05)):
                        index = item.data
                        available = limit[index] - len(buffers[index])
                        chunk = os.read(item.fileobj.fileno(), min(65536, available + 1))
                        if not chunk:
                            selector.unregister(item.fileobj)
                            continue
                        _require(len(chunk) <= available, 'native_output_overflow')
                        buffers[index].extend(chunk)
            _require(proc.returncode == 0 and not buffers[1], 'native_incomplete')
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
    return bytes(buffers[0])


def _validated_response(raw, nonce, assessed, runtime):
    native = json.loads(raw)
    _require(native.get('protocol') == PROTOCOL and native.get('nonce') == nonce
             and native.get('node_version') == runtime.node_version and native.get('repository') == assessed.repository
             and native.get('commit') == assessed.commit and native.get('tree') == assessed.tree,
             'native_receipt_identity_mismatch')
    result = native.get('result', {})
    _require(result.get('compiler_version') == runtime.compiler_version
             and isinstance(result.get('diagnostics'), list)
             and isinstance(result.get('roots'), list) and result.get('roots')
             and isinstance(result.get('program_inputs'), list) and result.get('program_inputs')
             and isinstance(result.get('read_inputs'), dict) and result.get('read_inputs'),
             'native_receipt_schema_mismatch')
    return result


def run_owned_native_bridge(*, policy, verified_producer_commit, assessed, verified_source_inventory,
                            source_mount, private_generated_bundle, dependency_mount, compiler_lib_mount,
                            runtime):
    """Only a protected integrator should call; currently not registered with NICO.

    An outcome here is not a completed assessment, approval, score or coverage
    update. Source/producer receipts must already be authenticated independently.
    """
    try:
        pin = policy.typegen_pin
        _require(assessed.repository == REPO and verified_producer_commit == policy.producer_commit == pin.producer_commit
                 and assessed.commit == pin.target_commit and assessed.tree == pin.target_tree,
                 'producer_or_assessed_identity_mismatch')
        _require(private_generated_bundle is not None, 'generated_type_bytes_unavailable')
        _require(dependency_mount and compiler_lib_mount, 'trusted_dependency_closure_unavailable')
        _require(source_mount and verified_source_inventory, 'source_mount_unavailable')
        _require(runtime is not None and runtime.compiler_version == COMPILER_VERSION, 'pinned_runtime_unavailable')
        _require(_source_mount_matches_inventory(source_mount, verified_source_inventory),
                 'source_mount_inventory_mismatch')
        try:
            generated = admit_private_build_inputs(private_generated_bundle, pin, assessed_commit=assessed.commit,
                                                    assessed_tree=assessed.tree,
                                                    verified_source_inventory=verified_source_inventory)
        except (ValueError, OSError, TypeError) as exc:
            raise BoundaryUnavailable('generated_type_bytes_unverified') from exc
        mounts = MappingProxyType({'source': source_mount, 'generated': generated,
                                   'dependencies': dependency_mount, 'compilerLibs': compiler_lib_mount})
        wire, nonce = _prepare_wire(policy, assessed, runtime.node_version, runtime.compiler_version, mounts)
        _verify_runtime(runtime, immutable=True)
        raw = _capture(runtime, wire, timeout=TIMEOUT)
        native = _validated_response(raw, nonce, assessed, runtime)
        return {'outcome': 'compiler_observed', 'native_sha256': sha256(raw).hexdigest(), 'native': native}
    except BoundaryUnavailable as exc:
        return {'outcome': 'unavailable', 'reason': str(exc)}
    except (ValueError, TypeError, OSError, AttributeError, KeyError, subprocess.SubprocessError):
        # Never expose process logs, command paths, provider headers or content.
        return {'outcome': 'unavailable', 'reason': 'native_bridge_unverified'}
