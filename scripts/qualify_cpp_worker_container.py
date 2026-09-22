"""Trusted, bounded execution-boundary probe; never assesses repository code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess


PROBE = r'''
import errno, json, os, signal, socket
signal.alarm(10)
def ceiling(name):
    with open('/sys/fs/cgroup/' + name) as stream:
        return stream.read(128).strip()
with open('/proc/self/status') as stream:
    status = dict(line.split(':', 1) for line in stream if ':' in line)
checks = {
    'nonroot': os.getuid() == 1000 and os.getgid() == 1000,
    'no_new_privileges': status['NoNewPrivs'].strip() == '1',
    'no_effective_capabilities': int(status['CapEff'].strip(), 16) == 0,
    'no_docker_socket': not os.path.exists('/var/run/docker.sock'),
    'no_host_workspace': not os.path.exists('/github/workspace'),
    'no_forwarded_credentials': not any(
        key.startswith(('GITHUB_', 'ACTIONS_', 'RAILWAY_', 'NICO_'))
        for key in os.environ
    ),
}
try:
    with open('/nico-readonly-probe', 'w') as stream:
        stream.write('unexpected')
    checks['readonly_root'] = False
except OSError as exc:
    checks['readonly_root'] = exc.errno in (errno.EROFS, errno.EACCES)
with open('/work/writable-control', 'w') as stream:
    stream.write('bounded local control')
checks['writable_workspace'] = True
sock = socket.socket()
sock.settimeout(1)
try:
    sock.connect(('192.0.2.1', 443))
    checks['network_denied'] = False
except OSError as exc:
    checks['network_denied'] = exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH)
finally:
    sock.close()
limits = {key: ceiling(key) for key in ('cpu.max', 'memory.max', 'pids.max')}
quota, period = map(int, limits['cpu.max'].split())
checks['cpu_ceiling'] = 0 < quota / period <= 0.5
checks['memory_ceiling'] = 0 < int(limits['memory.max']) <= 268435456
checks['process_ceiling'] = 0 < int(limits['pids.max']) <= 32
print(json.dumps({'checks': checks, 'observed_limits': limits}, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
'''


def run(*args: str, timeout: int = 30) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise RuntimeError('Trusted probe command exceeded output budget')
    return result.stdout.strip()


def main() -> None:
    # Controller holds CI authentication; it is never passed into the container.
    image = 'python:3.13-slim'
    name = 'nico-boundary-' + str(os.getpid())
    output = Path('cpp-worker-boundary-evidence.json')
    receipt = {
        'schema': 'nico.cpp_worker_boundary_qualification.v1',
        'status': 'UNPROVEN',
        'repository_executed': False,
        'source_sha': run('git', 'rev-parse', 'HEAD'),
        'probe_sha256': hashlib.sha256(PROBE.encode()).hexdigest(),
        'limits': {'cpu': 0.5, 'memory_bytes': 268435456, 'pids': 32,
                   'workspace_bytes': 16777216, 'container_timeout_seconds': 20},
        'remaining': ['production job dispatch and durable recovery',
                      'production evidence ingestion and artifact trust',
                      'build/test/fuzz scope and aggregate resource qualification'],
    }
    created = False
    try:
        run('docker', 'pull', image, timeout=120)
        metadata = json.loads(run('docker', 'image', 'inspect', image))[0]
        receipt['image_id'] = metadata['Id']
        receipt['image_repo_digests'] = metadata['RepoDigests']
        run('docker', 'create', '--name', name, '--interactive', '--network=none',
            '--read-only', '--user=1000:1000', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=0.5', '--memory=256m',
            '--memory-swap=256m', '--pids-limit=32',
            '--tmpfs=/work:rw,nosuid,nodev,size=16777216,mode=1777',
            '--log-driver=none', metadata['Id'], 'python', '-I', '-S', '-')
        created = True
        result = subprocess.run(['docker', 'start', '--attach', '--interactive', name],
                                input=PROBE, text=True, capture_output=True, timeout=20)
        if len(result.stdout) + len(result.stderr) > 65536:
            raise RuntimeError('Trusted probe exceeded output budget')
        receipt['exit_code'] = result.returncode
        receipt['result'] = json.loads(result.stdout)
        if result.returncode or not all(receipt['result']['checks'].values()):
            raise RuntimeError('Runtime isolation check failed')
        receipt['status'] = 'boundary_probe_passed_not_production_qualified'
    except Exception as exc:
        receipt['status'] = 'FAIL'
        receipt['error_type'] = type(exc).__name__
        raise
    finally:
        try:
            if created:
                run('docker', 'rm', '--force', name)
                receipt['container_removed'] = True
        except Exception:
            receipt['status'] = 'FAIL'
            receipt['container_removed'] = False
            raise
        finally:
            output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
            print(json.dumps(receipt, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
