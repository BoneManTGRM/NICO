"""Local owned-fixture controller. NOT wired into any production scanner.

Process limits and an immutable CompilerHost do not establish OS isolation.
Do not call this with customer/repository inputs without a separately qualified
boundary. Dependency and generated-input provenance are intentionally unsupported.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

PROGRAM = Path(__file__).resolve().parents[1] / 'scripts/trusted_typescript_prototype.cjs'
HARNESS = """const p=require(process.argv[1]); const fs=require('node:fs');
const runner=p.createTrustedRunner(process.argv[2],JSON.parse(process.argv[3]));
const result=runner(JSON.parse(fs.readFileSync(0,'utf8')));
process.stdout.write(JSON.stringify(result));"""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class FixtureTools:
    node: Path
    node_sha256: str
    compiler_root: Path
    compiler_anchors: dict[str, str]


@dataclass(frozen=True)
class FixtureLimits:
    wall_seconds: float = 15
    output_bytes: int = 8 * 1024 * 1024
    stderr_bytes: int = 32 * 1024
    input_bytes: int = 4 * 1024 * 1024
    heap_mb: int = 256


def _capture(command, raw, limits):
    """Bound every stream while running; kill the whole group on terminal failure."""
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={'PATH': '/nonexistent', 'NODE_OPTIONS': '', 'NODE_PATH': '', 'LANG': 'C.UTF-8'},
                            cwd='/', start_new_session=True, close_fds=True)
    output, errors = bytearray(), bytearray()
    deadline = time.monotonic() + limits.wall_seconds
    reason = ''
    selector = selectors.DefaultSelector()
    pending = memoryview(raw)
    try:
        for stream, mode in ((proc.stdin, selectors.EVENT_WRITE), (proc.stdout, selectors.EVENT_READ), (proc.stderr, selectors.EVENT_READ)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, mode)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = 'wall_timeout'
                break
            for key, event in selector.select(min(remaining, .1)):
                stream = key.fileobj
                if stream is proc.stdin:
                    try:
                        sent = os.write(stream.fileno(), pending[:65536])
                        pending = pending[sent:]
                    except BrokenPipeError:
                        pending = pending[len(pending):]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                else:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    target, cap = (output, limits.output_bytes) if stream is proc.stdout else (errors, limits.stderr_bytes)
                    remaining_bytes = max(0, cap - len(target))
                    target.extend(chunk[:remaining_bytes])
                    if len(chunk) > remaining_bytes:
                        reason = 'output_budget_exceeded'
                        break
            if reason:
                break
        if not reason:
            try:
                proc.wait(timeout=max(.001, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                reason = 'wall_timeout'
    finally:
        selector.close()
        # A descendant retaining pipes must not outlive timeout or completion.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if not stream.closed:
                stream.close()
    return proc.returncode, bytes(output), bytes(errors), reason


def _unique(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate_output_key')
        output[key] = value
    return output


def _validate_result(raw, request, expected_compiler):
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
    if not isinstance(value, dict) or value.get('schema') != 'nico.trusted-typescript.prototype.v1':
        raise ValueError('result_schema')
    if value.get('status') not in {'complete', 'incomplete'} or type(value.get('clean')) is not bool:
        raise ValueError('result_status')
    if not isinstance(value.get('diagnostics'), list) or value.get('findings') != value['diagnostics']:
        raise ValueError('diagnostic_parity')
    if value['status'] == 'incomplete':
        if value['clean']:
            raise ValueError('incomplete_clean')
    receipt = value.get('receipt')
    if value['status'] == 'incomplete' and receipt is None:
        return value
    if not isinstance(receipt, dict):
        raise ValueError('missing_receipt')
    expected_result = {k: v for k, v in value.items() if k != 'receipt'}
    expected_hash = digest({k: v for k, v in receipt.items() if k != 'receipt_sha256'})
    if (receipt.get('receipt_sha256') != expected_hash or receipt.get('result_sha256') != digest(expected_result)
            or receipt.get('diagnostics_sha256') != digest(value['diagnostics'])
            or receipt.get('identity') != request['manifest']['identity']
            or receipt.get('manifest_sha256') != request['manifest_sha256']
            or receipt.get('compiler') != {'version': '6.0.3', **expected_compiler}
            or receipt.get('qualified_for_production') is not False
            or receipt.get('os_isolation_verified') is not False
            or receipt.get('emitted_files') != 0
            or (value['status'] == 'complete' and value.get('closure_failures') != [])
            or value['clean'] != (value['status'] == 'complete' and len(value['diagnostics']) == 0)):
        raise ValueError('result_receipt_mismatch')
    return value


def run_owned_fixture(request, *, tools: FixtureTools, expected_identity: dict, limits: FixtureLimits = FixtureLimits()):
    """Caller owns every input. No production authority is implied by this API."""
    raw = b''
    stderr = b''
    execution = {'os_isolation_verified': False, 'qualified_for_production': False}
    try:
        if request.get('manifest', {}).get('identity') != expected_identity:
            raise ValueError('controller_identity_mismatch')
        if not (0 < limits.wall_seconds <= 15 and 0 < limits.output_bytes <= 8*1024*1024
                and 0 < limits.stderr_bytes <= 32768 and 0 < limits.input_bytes <= 4*1024*1024
                and 16 <= limits.heap_mb <= 256):
            raise ValueError('controller_limits')
        encoded = json.dumps(request, ensure_ascii=False).encode()
        if len(encoded) > limits.input_bytes:
            raise ValueError('controller_input_budget')
        node = tools.node
        if not node.is_absolute() or node.resolve(strict=True) != node or not node.is_file():
            raise ValueError('controller_node_boundary')
        if hashlib.sha256(node.read_bytes()).hexdigest() != tools.node_sha256:
            raise ValueError('controller_node_identity')
        command = [str(node), f'--max-old-space-size={limits.heap_mb}', '-e', HARNESS,
                   str(PROGRAM), str(tools.compiler_root), json.dumps(tools.compiler_anchors)]
        execution.update(node_sha256=tools.node_sha256, runner_sha256=hashlib.sha256(PROGRAM.read_bytes()).hexdigest(),
                         limits=vars(limits), cpu_limit_verified=False, address_space_limit_verified=False)
        code, raw, stderr, reason = _capture(command, encoded, limits)
        execution.update(returncode=code, stdout_sha256=hashlib.sha256(raw).hexdigest(),
                         stderr_sha256=hashlib.sha256(stderr).hexdigest(), capture_complete=not bool(reason))
        if reason or code or stderr:
            raise ValueError(reason or 'native_execution_failed')
        result = _validate_result(raw, request, tools.compiler_anchors)
        execution['execution_sha256'] = digest(execution)
        return {**result, 'execution': execution, 'native_stdout': raw, 'native_stderr': stderr}
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        return {'status': 'incomplete', 'clean': False, 'reason': str(exc), 'receipt': None,
                'execution': execution, 'native_stdout': raw, 'native_stderr': stderr}
