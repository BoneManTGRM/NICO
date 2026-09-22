"""Trusted Cppcheck controller; target bytes enter a disposable container only.

This consumes the existing standalone profile. It does not qualify a build,
compilation database, header context or runtime checks, and never pulls images.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time
from uuid import uuid4

from nico.assessment_worker_capacity_v1 import docker_resource_args


def _native_result(xml, stdout, stderr, *, exit_code, timed_out, output_truncated, duration_ms, invocation):
    """Preserve original bounded bytes even when canonical text cannot be parsed."""
    streams = {'xml': xml, 'stdout': stdout, 'stderr': stderr}
    result = {'native': None, 'native_decoding_failed': False,
        'execution': {'exit_code': exit_code, 'timed_out': timed_out, 'output_truncated': output_truncated,
                      'duration_ms': duration_ms, 'invocation': invocation},
        'raw_streams': {name: base64.b64encode(value).decode('ascii') for name, value in streams.items()},
        'streams': {name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)}
                    for name, value in streams.items()}}
    try:
        result['native'] = {'xml': xml.decode('utf-8'), 'progress': (stdout+stderr).decode('utf-8'),
                            **result['execution']}
    except UnicodeDecodeError:
        result['native_decoding_failed'] = True
    return result


# Only this trusted program, never repository commands, is the entry point.
# One serializer is used locally and in the disposable image; target files
# cannot supply or replace controller functions.
SETUP_PROGRAM = r'''
request = json.loads(sys.stdin.buffer.read(24 * 1024 * 1024 + 1))
status = dict(line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid() == os.getgid() == 1000
assert status['NoNewPrivs'].strip() == '1' and int(status['CapEff'].strip(), 16) == 0
assert not pathlib.Path('/var/run/docker.sock').exists()
assert not any(k.startswith(('GITHUB_', 'ACTIONS_', 'NICO_', 'RAILWAY_')) for k in os.environ)
limits = {k: pathlib.Path('/sys/fs/cgroup', k).read_text().strip() for k in ('cpu.max', 'memory.max', 'pids.max')}
quota, period = map(int, limits['cpu.max'].split())
assert 0 < quota / period <= 0.5 and 0 < int(limits['memory.max']) <= 268435456
assert 0 < int(limits['pids.max']) <= 32
probe = socket.socket(); probe.settimeout(1)
try:
    probe.connect(('192.0.2.1', 443))
    raise RuntimeError('network_isolation_missing')
except OSError as error:
    import errno
    assert error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
finally:
    probe.close()
root = pathlib.Path('/work/source'); root.mkdir()
for name, item in request['inputs'].items():
    path = pathlib.PurePosixPath(name)
    assert not path.is_absolute() and all(p not in ('.', '..', '.git') for p in name.split('/'))
    data = base64.b64decode(item['base64'], validate=True)
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    output = root / path; output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
'''

PROGRAM = ('import base64, hashlib, json, os, pathlib, resource, signal, socket, subprocess, sys, time\n'
           + inspect.getsource(_native_result) + SETUP_PROGRAM + r'''
os.chdir(root)
tool_env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LD_LIBRARY_PATH': '/usr/local/lib64:/usr/local/lib'}
version = subprocess.run(['cppcheck', '--version'], capture_output=True, check=True, timeout=5, env=tool_env)
assert version.stdout.decode().strip() == 'Cppcheck ' + request['tool_version']
pathlib.Path('/work/cppcheck-inputs.txt').write_text(''.join('./' + p + '\n' for p in sorted(request['inputs'])))
output_limit = request['output_limit']
resource.setrlimit(resource.RLIMIT_FSIZE, (output_limit, output_limit))
start = time.monotonic(); timed_out = False
with open('/work/stdout', 'wb') as stdout, open('/work/stderr', 'wb') as stderr:
    process = subprocess.Popen(request['invocation'], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                               start_new_session=True, env=tool_env)
    try:
        process.wait(timeout=request['timeout_seconds'])
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=5)
duration = int((time.monotonic() - start) * 1000)
def read(name):
    path = pathlib.Path('/work', name)
    return path.read_bytes() if path.exists() else b''
xml, stdout, stderr = read('cppcheck.xml'), read('stdout'), read('stderr')
truncated = any(len(value) >= output_limit for value in (xml, stdout, stderr))
# The prepared profile has one retained progress field. Preserve both streams;
# native stream hashes/sizes and kernel observations accompany the controller result.
result = _native_result(xml, stdout, stderr, exit_code=124 if timed_out else process.returncode,
    timed_out=timed_out, output_truncated=truncated, duration_ms=duration, invocation=request['invocation'])
result.update(tool_version=request['tool_version'], isolation=limits)
print(json.dumps(result, sort_keys=True))
''')


def invocation():
    return ["cppcheck", "--xml", "--enable=warning,style,performance,portability,information",
        "--check-level=normal", "--max-configs=12", "--std=c++20", "--std=c11", "--platform=unix64",
        "-j2", "--file-list=/work/cppcheck-inputs.txt", "--output-file=/work/cppcheck.xml"]


def _command(args, *, checkpoint, timeout=15, input_bytes=None, limit=131072, native_exit=False):
    """Bound Docker CLI output while it is emitted, and always reap the CLI."""
    checkpoint()
    process = subprocess.Popen(args, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={"PATH": os.environ.get("PATH", "")},
        start_new_session=True, bufsize=0, shell=False)
    output = bytearray()
    pending = memoryview(input_bytes or b'')
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as ready:
            os.set_blocking(process.stdout.fileno(), False)
            ready.register(process.stdout, selectors.EVENT_READ)
            if process.stdin is not None:
                if pending:
                    os.set_blocking(process.stdin.fileno(), False)
                    ready.register(process.stdin, selectors.EVENT_WRITE)
                else:
                    process.stdin.close()
            while ready.get_map():
                checkpoint()
                if time.monotonic() >= deadline:
                    if native_exit:
                        return {'exit_code': 124, 'timed_out': True, 'output_truncated': False, 'output': bytes(output)}
                    raise ValueError("worker_container_timed_out")
                for key, _ in ready.select(0.1):
                    if key.fileobj is process.stdin:
                        try:
                            written = os.write(key.fd, pending[:65536])
                        except BrokenPipeError:
                            raise ValueError("worker_container_input_rejected") from None
                        pending = pending[written:]
                        if not pending:
                            ready.unregister(key.fileobj); process.stdin.close()
                    else:
                        raw = os.read(key.fd, min(65536, limit - len(output) + 1))
                        if not raw:
                            ready.unregister(key.fileobj)
                        output.extend(raw)
                        if len(output) > limit:
                            if native_exit:
                                return {'exit_code': 125, 'timed_out': False, 'output_truncated': True,
                                        'output': bytes(output[:limit])}
                            raise ValueError("worker_container_output_limit")
        # EOF does not imply process exit. Keep the same lease/cancellation
        # checkpoints active even when the executable closes both streams.
        while process.poll() is None:
            checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if native_exit:
                    return {'exit_code': 124, 'timed_out': True, 'output_truncated': False, 'output': bytes(output)}
                raise ValueError('worker_container_timed_out')
            try:
                process.wait(timeout=min(0.1, remaining))
            except subprocess.TimeoutExpired:
                continue
        returncode = process.returncode
        if native_exit:
            checkpoint()
            return {'exit_code': returncode, 'timed_out': False, 'output_truncated': False, 'output': bytes(output)}
        if returncode != 0:
            raise ValueError("worker_container_control_failed")
        checkpoint()
        return bytes(output)
    finally:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=5)
        if process.stdin is not None:
            process.stdin.close()
        process.stdout.close()


def _read_input(root_fd, path, remaining):
    """Open every component relative to the owned root without following links."""
    parent = os.dup(root_fd)
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > remaining:
                raise ValueError("worker_input_type_or_budget_invalid")
            return handle.read(remaining + 1)
    finally:
        os.close(parent)


def run_isolated_cppcheck(contract, source: Path, *, checkpoint, timeout_seconds):
    """Use one preprovisioned image by digest; cancellation always removes it."""
    from nico.assessment_worker_receipts import validate_contract
    contract = validate_contract(contract)
    if contract['profile'] in {'cpp-configured-v1', 'cpp-sanitized-v1', 'cpp-runtime-cases-v1'}:
        from nico.assessment_cpp_execution import run_configured
        return run_configured(contract, source, checkpoint=checkpoint, timeout_seconds=timeout_seconds)
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= min(300, contract['limits']['wall_seconds']):
        raise ValueError("worker_execution_budget_invalid")
    image = contract["image_digest"]
    metadata = json.loads(_command(["docker", "image", "inspect", image], checkpoint=checkpoint))
    if len(metadata) != 1 or metadata[0].get("Id") != image:
        raise ValueError("worker_image_identity_mismatch")
    if source.is_symlink() or not source.is_dir() or source.absolute() != source.resolve(strict=True):
        raise ValueError("worker_input_type_invalid")
    actual_paths = set()
    for path in source.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("worker_input_type_invalid")
        if path.is_file():
            actual_paths.add(path.relative_to(source).as_posix())
    if actual_paths != set(contract["targets"]):
        raise ValueError("worker_input_population_mismatch")
    encoded, total = {}, 0
    root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path, expected in sorted(contract["targets"].items()):
            checkpoint()
            raw = _read_input(root_fd, path, 16 * 1024 * 1024 - total)
            total += len(raw)
            if total > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("worker_input_digest_or_budget_mismatch")
            encoded[path] = {"base64": base64.b64encode(raw).decode(), "sha256": expected}
    finally:
        os.close(root_fd)
    data = json.dumps({"inputs": encoded, "tool_version": contract["tool_version"],
        "invocation": invocation(), "timeout_seconds": timeout_seconds,
        "output_limit": max(32, contract["max_receipt_bytes"] // 32)}).encode()
    if len(data) > 24 * 1024 * 1024:
        raise ValueError("worker_input_budget_exceeded")
    name = 'nico-assessment-' + uuid4().hex
    # Reserve cleanup before create: its response or following heartbeat can fail
    # after the daemon has already created the container.
    try:
        _command(["docker", "create", "--name", name, "--interactive", "--network=none",
            "--read-only", "--user=1000:1000", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            *docker_resource_args(contract["profile"]),
            "--log-driver=none",
            "--entrypoint=python", image, "-I", "-S", "-c", PROGRAM], checkpoint=checkpoint)
        output = _command(["docker", "start", "--attach", "--interactive", name], checkpoint=checkpoint,
            input_bytes=data, timeout=timeout_seconds+10, limit=contract['max_receipt_bytes'])
        result = json.loads(output)
        if result.get('tool_version') != contract['tool_version']:
            raise ValueError("worker_tool_identity_mismatch")
        return result
    finally:
        # Cleanup must run even after cancellation/deadline; do not heartbeat.
        # Docker rm is idempotent only after resolving "no such container";
        # other failures deliberately prevent a success result.
        _command(["docker", "rm", "--force", name], checkpoint=lambda: None)
