"""Execute a frozen project plan inside one disposable, non-networked container.

The trusted host owns command outcomes and receipts. No project command runs on
that host, no host mount or credentials enter the container, and every Docker
operation preserves the durable job's heartbeat/cancellation checkpoint.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from nico.assessment_cpp_full_project import PROFILE, MAX_FILE_BYTES, execution_steps
from nico.assessment_worker_capacity_v1 import docker_resource_args
from nico.assessment_worker_container import _command, _read_input
from nico.assessment_cpp_analysis_boundary import (
    ANALYSIS_USER, ANALYSIS_SETUP_PROGRAM, ANALYSIS_INPUT_PROGRAM,
)

BOUNDARY_PROGRAM = r'''
import errno, json, os, pathlib, socket, stat
status = dict(line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
mounts = [line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]
work = next(row for row in mounts if row[4] == '/work')
root = next(row for row in mounts if row[4] == '/')
def cgroup(name): return pathlib.Path('/sys/fs/cgroup', name).read_text().strip()
blocked = False
probe = socket.socket(); probe.settimeout(1)
try: probe.connect(('192.0.2.1', 443))
except OSError as error: blocked = error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
finally: probe.close()
work_stat = pathlib.Path('/work').stat()
analysis = pathlib.Path('/work/analysis')
analysis_info = analysis.stat() if analysis.exists() else None
analysis_private = bool(analysis_info and analysis_info.st_uid == 1001
    and stat.S_IMODE(analysis_info.st_mode) == 0o700
    and not any(os.access(analysis, mode) for mode in (os.R_OK, os.W_OK, os.X_OK)))
analysis_write_denied = False
try:
    write_fd = os.open('/work/analysis/target-write-probe', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except PermissionError:
    analysis_write_denied = True
else:
    os.close(write_fd)
source = pathlib.Path('/work/source')
source_stat = source.stat() if source.exists() else None
source_read_only = bool(source_stat and source_stat.st_uid == 0
    and stat.S_IMODE(source_stat.st_mode) == 0o555 and not os.access(source, os.W_OK))
print(json.dumps({'uid':os.getuid(), 'gid':os.getgid(),
 'work_root_owned_sticky':work_stat.st_uid == 0 and stat.S_IMODE(work_stat.st_mode) == 0o1777,
 'source_read_only':source_read_only, 'analysis_private':analysis_private,
 'analysis_write_denied':analysis_write_denied,
 'no_new_privileges':status['NoNewPrivs'].strip() == '1',
 'effective_capabilities':int(status['CapEff'].strip(),16),
 'cpu_max':cgroup('cpu.max'), 'memory_max':cgroup('memory.max'),
 'pids_max':cgroup('pids.max'), 'swap_max':cgroup('memory.swap.max'),
 'work_mount':work[5].split(','), 'root_read_only':'ro' in root[5].split(','),
 'docker_socket_absent':not pathlib.Path('/var/run/docker.sock').exists(),
 'credential_environment_absent':not any(key.startswith(('NICO_', 'GITHUB_', 'ACTIONS_', 'RAILWAY_')) for key in os.environ),
 'external_network_blocked':blocked}))
'''

INPUT_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, sys
limit = int(sys.argv[1])
raw = sys.stdin.buffer.read(limit + 1)
if len(raw) > limit: raise ValueError('input_limit')
files = json.loads(raw)
if os.getuid() != 0: raise ValueError('provisioning_identity')
root = pathlib.Path('/work/source'); root.mkdir()
result = {}
for name, value in files.items():
    path = pathlib.PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..', '.git') for p in name.split('/')):
        raise ValueError('input_path')
    data = base64.b64decode(value['base64'], validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if digest != value['sha256']: raise ValueError('input_digest')
    output = root / path
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle: handle.write(data)
    output.chmod(0o555 if value['executable'] else 0o444)
    result[name] = digest
# Trusted byte provisioning alone runs as uid 0, before any assessed command.
# Root-owned source under the root-owned sticky /work parent cannot be edited
# or renamed by the subsequent uid-1000 build/test/analyzer processes.
for directory in sorted((p for p in root.rglob('*') if p.is_dir()), reverse=True):
    directory.chmod(0o555)
root.chmod(0o555)
print(json.dumps(result, sort_keys=True))
'''

# Do not follow project-created symlinks or read devices/FIFOs, even while
# collecting a failed build's artifact. Returned content is still untrusted.
READ_PROGRAM = r'''
import base64, json, os, pathlib, stat, sys
path, limit = sys.argv[1], int(sys.argv[2])
parts = pathlib.PurePosixPath(path).parts
if parts[:2] != ('/', 'work') or any(p in ('..', '.') for p in parts):
    raise ValueError('artifact_path')
fd = os.open('/work', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in parts[2:-1]:
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd); fd = child
    leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(leaf, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode): raise ValueError('artifact_type')
        data = handle.read(limit + 1)
    print(json.dumps({'data':base64.b64encode(data[:limit]).decode(), 'truncated':len(data)>limit}))
finally:
    os.close(fd)
'''


def boundary_valid(value, *, source_required=True, profile=PROFILE):
    if not isinstance(value, dict): return False
    from nico.assessment_worker_capacity_v1 import resources_for, BASELINE_QUALIFICATION_PROFILE
    if profile not in {PROFILE, BASELINE_QUALIFICATION_PROFILE}: return False
    try:
        resources = resources_for(profile)
        quota, period = map(int, value['cpu_max'].split())
        return (type(value['uid']) is int and value['uid'] == 1000
            and type(value['gid']) is int and value['gid'] == 1000
            and value['no_new_privileges'] is True
            and value['work_root_owned_sticky'] is True
            and value.get('analysis_private') is True and value.get('analysis_write_denied') is True
            and (not source_required or value['source_read_only'] is True)
            and type(value['effective_capabilities']) is int and value['effective_capabilities'] == 0
            and period > 0 and quota == int(resources['cpus']) * period
            and value['memory_max'] == str(resources['memory_bytes']) and value['pids_max'] == resources['pids']
            and value['swap_max'] == '0' and {'rw', 'nosuid', 'nodev'} <= set(value['work_mount'])
            and 'noexec' not in value['work_mount']
            and all(value[k] is True for k in ('root_read_only', 'docker_socket_absent',
                'credential_environment_absent', 'external_network_blocked')))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _inputs(contract, source, checkpoint):
    if source.is_symlink() or not source.is_dir() or source.absolute() != source.resolve(strict=True):
        raise ValueError('worker_input_type_invalid')
    paths = set()
    for path in source.rglob('*'):
        checkpoint()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('worker_input_type_invalid')
        if path.is_file(): paths.add(path.relative_to(source).as_posix())
    if paths != set(contract['targets']): raise ValueError('worker_input_population_mismatch')
    maximum = contract['configuration']['source_byte_limit']
    total, files = 0, {}
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path, digest in sorted(contract['targets'].items()):
            checkpoint()
            data = _read_input(fd, path, min(MAX_FILE_BYTES, maximum - total))
            total += len(data)
            if total > maximum or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('worker_input_digest_or_budget_mismatch')
            files[path] = {'base64': base64.b64encode(data).decode('ascii'), 'sha256': digest,
                          'executable': bool((source / path).stat().st_mode & 0o111)}
    finally:
        os.close(fd)
    return files



def _capture_limits(contract, specs, empty_native):
    """Partition the existing receipt cap; large evidence is not an ordinary log.

    Reserve the fixed native programs/source inventory, the second target map
    in the receipt envelope, and 64 KiB for identity/provisioning/boundary data.
    Allocate the remaining base64 space once across every possible capture.
    These quotas cannot raise the contract cap or change execution populations.
    """
    from nico.assessment_worker_receipts import canonical_bytes
    slots = {}
    for spec in specs:
        key = spec['id']
        weight, ceiling = 1, 65536
        if key.endswith(('-configure', '-build', '-discover', '-unit', '-integration')) or key == 'static-analysis':
            weight, ceiling = 4, 524288
        if 'compiler_configuration' in spec:
            weight, ceiling = 32, 2097152
        elif 'generated_configuration' in spec:
            weight, ceiling = 8, 524288
        elif 'native_test_configuration' in spec or spec.get('fuzz_execution'):
            weight, ceiling = 16, 1048576
        slots[(key, 'output')] = (weight, ceiling)
        for artifact in spec['artifacts']:
            slots[(key, artifact)] = ({'compilation_database': (16, 1048576),
                'analysis_xml': (8, 1048576), 'junit': (4, 262144)}[artifact])
    reserve = (len(canonical_bytes(empty_native)) + len(canonical_bytes(contract['targets']))
               + 65536 + 8 * len(slots))
    available = (contract['max_receipt_bytes'] - reserve) * 3 // 4
    if available < len(slots) * 1024:
        raise ValueError('worker_full_project_evidence_budget_invalid')
    # Capped weighted allocation redistributes unused small-log capacity to
    # structured evidence. Integer rounding only leaves bytes unallocated.
    pending, limits = dict(slots), {}
    while pending:
        total_weight = sum(weight for weight, _ in pending.values())
        capped = {key: ceiling for key, (weight, ceiling) in pending.items()
                  if available * weight // total_weight >= ceiling}
        if not capped:
            limits.update({key: available * weight // total_weight
                           for key, (weight, _) in pending.items()})
            break
        for key, ceiling in capped.items():
            limits[key] = ceiling
            available -= ceiling
            del pending[key]
    if any(limit < 1024 for limit in limits.values()):
        raise ValueError('worker_full_project_evidence_budget_invalid')
    return limits


def run_full_project(contract, source: Path, *, checkpoint, timeout_seconds, command=None):
    from nico.assessment_worker_receipts import validate_contract
    contract = validate_contract(contract)
    if (contract['profile'] != PROFILE or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= min(300, contract['limits']['wall_seconds'])):
        raise ValueError('worker_full_project_budget_invalid')
    command = _command if command is None else command
    files = _inputs(contract, source, checkpoint)
    specs = execution_steps(contract)
    result = {'schema': 'nico.cpp-full-project-native.v1', 'source_hashes': contract['targets'],
        'steps': [{'id': s['id'], 'invocation': s['invocation'], 'attempted': False,
            'exit_code': None, 'timed_out': False, 'output_truncated': False, 'duration_ms': 0,
            'output': '', 'artifacts': {}} for s in specs],
        'boundary': None, 'boundary_verified': False, 'memory_peak_bytes': None,
        'cleanup_verified': False, 'error': None}
    name = 'nico-full-project-' + uuid4().hex
    deadline = time.monotonic() + timeout_seconds
    capture_limits = _capture_limits(contract, specs, result)
    created = False
    def invoke(args, *, data=None, max_output=65536, seconds=30):
        checkpoint()
        left = deadline - time.monotonic()
        if left <= 0: raise ValueError('worker_full_project_deadline')
        return command(args, checkpoint=checkpoint, input_bytes=data, timeout=min(seconds, left),
                       limit=max_output, native_exit=True)
    def require(args, **kwargs):
        response = invoke(args, **kwargs)
        if response['exit_code'] or response['timed_out'] or response['output_truncated']:
            raise ValueError('worker_full_project_control_failed')
        return response['output']
    try:
        image = contract['image_digest']
        metadata = json.loads(require(['docker', 'image', 'inspect', image]))
        if len(metadata) != 1 or metadata[0].get('Id') != image:
            raise ValueError('worker_image_identity_mismatch')
        # No binds, writable host paths, ambient environment, or network grants.
        created = True  # creation can succeed before an interrupted CLI response.
        require(['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(PROFILE, executable=True), '--log-driver=none',
            '--env=TMPDIR=/work', '--env=HOME=/work', '--env=ASAN_OPTIONS=detect_leaks=0:halt_on_error=1',
            '--env=UBSAN_OPTIONS=halt_on_error=1', '--entrypoint=sleep', image, str(timeout_seconds + 15)])
        require(['docker', 'start', name])
        private = json.loads(require(['docker', 'exec', '--user=' + ANALYSIS_USER, name,
            'python3', '-I', '-S', '-c', ANALYSIS_SETUP_PROGRAM]))
        if private != {'uid': 1001, 'gid': 1001, 'private': True}:
            raise ValueError('worker_full_project_control_failed')
        result['boundary'] = json.loads(require(['docker', 'exec', name, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        result['boundary_verified'] = boundary_valid(result['boundary'], source_required=False)
        if not result['boundary_verified']: raise ValueError('worker_full_project_control_failed')
        payload = json.dumps(files, separators=(',', ':')).encode()
        transferred = json.loads(require(['docker', 'exec', '--user=0:0', '--interactive', name,
            'python3', '-I', '-S', '-c', INPUT_PROGRAM, str(len(payload))], data=payload,
            max_output=contract['max_receipt_bytes']))
        if transferred != contract['targets']: raise ValueError('worker_input_digest_or_budget_mismatch')
        result['boundary'] = json.loads(require(['docker', 'exec', name, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        result['boundary_verified'] = boundary_valid(result['boundary'])
        if not result['boundary_verified']: raise ValueError('worker_full_project_control_failed')
        if contract['configuration'].get('native_test_evidence') == 'bound-binary-replay-v1':
            from nico.assessment_cpp_native_tests import SETUP_PROGRAM
            require(['docker', 'exec', '--user=0:0', name, 'python3', '-I', '-S', '-c', SETUP_PROGRAM])
        if contract['configuration'].get('bounded_fuzz') is not None:
            from nico.assessment_cpp_fuzz_runtime import prepare_workspace
            prepare_workspace(require, name, contract['configuration']['bounded_fuzz'])
        successful = {}
        for spec, row in zip(specs, result['steps']):
            if not all(successful.get(key, False) for key in spec['needs']):
                successful[spec['id']] = False
                continue
            if spec.get('fuzz_execution'):
                from nico.assessment_cpp_fuzz_runtime import run_fuzz
                before = time.monotonic()
                observed = run_fuzz(invoke, name, contract['configuration']['bounded_fuzz'], contract['targets'])
                data = json.dumps(observed, sort_keys=True).encode()
                maximum = capture_limits[(spec['id'], 'output')]
                row.update(attempted=True, exit_code=0, duration_ms=int((time.monotonic() - before) * 1000),
                    output_truncated=len(data) > maximum,
                    output=base64.b64encode(data[:maximum]).decode('ascii'))
                successful[spec['id']] = observed['error'] is None and not row['output_truncated']
                if row['output_truncated']: break
                if observed['error'] == 'worker_fuzz_interrupted': break
                continue
            if 'native_test_configuration' in spec:
                from nico.assessment_cpp_native_tests import run_bound_tests
                group = spec['native_test_configuration']
                discovered = next(r for r in result['steps'] if r['id'] == group + '-discover')
                before = time.monotonic()
                observed = run_bound_tests(invoke, name, group,
                    base64.b64decode(discovered['output'], validate=True), contract['configuration'])
                data = json.dumps(observed, sort_keys=True).encode()
                maximum = capture_limits[(spec['id'], 'output')]
                row.update(attempted=True, exit_code=0, duration_ms=int((time.monotonic() - before) * 1000),
                    output_truncated=len(data) > maximum,
                    output=base64.b64encode(data[:maximum]).decode('ascii'))
                successful[spec['id']] = observed['error'] is None and not row['output_truncated']
                if row['output_truncated']: break
                if observed['error'] == 'worker_native_test_interrupted': break
                continue
            analysis_step = (spec['id'] in {'analyzer-version', 'static-analysis', 'fuzz-compiler-version'}
                             or 'compiler_configuration' in spec or 'generated_configuration' in spec)
            prefix = ['docker', 'exec', *(['--user=' + ANALYSIS_USER] if analysis_step else []), name]
            if spec['id'] == 'static-analysis':
                from nico.assessment_cpp_full_project import _database
                configured = next(r for r in result['steps'] if r['id'] == 'baseline-configure')
                encoded_db = configured['artifacts'].get('compilation_database')
                if not isinstance(encoded_db, str):
                    successful[spec['id']] = False
                    continue
                database = base64.b64decode(encoded_db, validate=True)
                _database(database, contract['configuration']['translation_units'], '/work/build',
                    nested=contract['configuration'].get('cmake_layout') in ('nested-source-v1', 'nested-source-v2-gcc-options'))
                if contract['configuration'].get('generated_headers'):
                    from nico.assessment_cpp_generated_context import configured_database_parser
                    derive = configured_database_parser(contract['configuration'])
                    database = derive(database, contract['configuration']['translation_units'],
                        'baseline', contract['configuration']['generated_headers'])
                    encoded_db = base64.b64encode(database).decode('ascii')
                digest = hashlib.sha256(database).hexdigest()
                transfer = json.dumps({'data': encoded_db, 'sha256': digest}).encode()
                proof = json.loads(require(['docker', 'exec', '--user=' + ANALYSIS_USER, '--interactive',
                    name, 'python3', '-I', '-S', '-c', ANALYSIS_INPUT_PROGRAM, str(len(transfer))], data=transfer))
                if proof != {'sha256': digest, 'uid': 1001}:
                    raise ValueError('worker_full_project_control_failed')
            compiler_input = None
            if 'compiler_configuration' in spec:
                configured = next(r for r in result['steps'] if r['id'] == spec['compiler_configuration'] + '-configure')
                database = configured['artifacts'].get('compilation_database')
                if not isinstance(database, str):
                    successful[spec['id']] = False
                    continue
                from nico.assessment_cpp_full_project import _database
                group = spec['compiler_configuration']
                _database(base64.b64decode(database, validate=True), contract['configuration']['translation_units'],
                          '/work/build' if group == 'baseline' else '/work/' + group,
                          None if group == 'baseline' else group,
                          nested=contract['configuration'].get('cmake_layout') in ('nested-source-v1', 'nested-source-v2-gcc-options'))
                request = {'database': database, 'configuration': group,
                    'units': contract['configuration']['translation_units'], 'targets': contract['targets']}
                if contract['configuration'].get('generated_headers'):
                    captured = next(r for r in result['steps'] if r['id'] == group + '-generated-context')
                    request.update(generated_context=captured['output'],
                                   headers=contract['configuration']['generated_headers'])
                compiler_input = json.dumps(request).encode()
                prefix = ['docker', 'exec', '--user=' + ANALYSIS_USER, '--interactive', name]
            if 'generated_configuration' in spec:
                compiler_input = json.dumps({'configuration': spec['generated_configuration'],
                    'headers': contract['configuration']['generated_headers']}).encode()
                prefix = ['docker', 'exec', '--user=' + ANALYSIS_USER, '--interactive', name]
            before = time.monotonic()
            stream_limit = capture_limits[(spec['id'], 'output')]
            response = invoke([*prefix, *spec['invocation']], data=compiler_input, max_output=stream_limit, seconds=timeout_seconds)
            row.update(attempted=True, exit_code=response['exit_code'], timed_out=response['timed_out'],
                output_truncated=response['output_truncated'], duration_ms=int((time.monotonic() - before) * 1000),
                output=base64.b64encode(response['output']).decode('ascii'))
            successful[spec['id']] = not response['exit_code'] and not response['timed_out'] and not response['output_truncated']
            if row['timed_out'] or row['output_truncated']:
                break  # stopping the Docker CLI alone does not stop the assessed process; remove container next.
            for key, path in spec['artifacts'].items():
                artifact_limit = capture_limits[(spec['id'], key)]
                observed = invoke([*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
                                   path, str(artifact_limit)], max_output=artifact_limit * 2 + 1024)
                if observed['exit_code'] or observed['timed_out'] or observed['output_truncated']:
                    continue  # artifact absent/unreadable remains missing, never successful evidence.
                artifact = json.loads(observed['output'])
                if artifact['truncated']:
                    row['output_truncated'] = True
                    successful[spec['id']] = False
                row['artifacts'][key] = artifact['data']
        # Only inspect the cgroup after completed commands. Failed/timeout capture remains valid evidence.
        peak = invoke(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'], seconds=2)
        if peak['exit_code'] == 0 and not peak['timed_out'] and not peak['output_truncated']:
            result['memory_peak_bytes'] = int(peak['output'].strip())
    except (Exception, KeyboardInterrupt):
        result['error'] = 'worker_full_project_control_failed'
    finally:
        if created:
            try:
                cleanup = command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                    timeout=10, limit=65536, native_exit=True)
                result['cleanup_verified'] = (cleanup['exit_code'] == 0 and not cleanup['timed_out']
                                              and not cleanup['output_truncated'])
            except Exception:
                result['cleanup_verified'] = False
        if not result['cleanup_verified']:
            result['error'] = result['error'] or 'worker_full_project_cleanup_failed'
    return {'native': result, 'tool_version': contract['tool_version']}
