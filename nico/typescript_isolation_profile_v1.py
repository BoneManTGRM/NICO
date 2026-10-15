"""Disabled TypeScript isolation specification; no launcher or environment switch.

A plan is not observed isolation. Existing tool-specific workers are unchanged.
"""
from copy import deepcopy
import re

_PROFILE = {
    'schema':'nico.typescript.isolation-plan.v1', 'enabled':False,
    'os_isolation_verified':False, 'qualified_for_production':False,
    'network':'none', 'read_only_root':True, 'user':'10001:10001',
    'capabilities':[], 'no_new_privileges':True, 'seccomp':'runtime-default',
    'host_mounts':[], 'controller_credentials':False, 'docker_socket':False,
    'cpus':'0.5', 'memory_bytes':536870912, 'swap_bytes':0, 'pids':32,
    'cpu_seconds':30, 'wall_seconds':60, 'nofile':128, 'node_heap_mb':256,
    'tmpfs_bytes':67108864, 'stdout_bytes':8388608, 'stderr_bytes':32768,
    'input_bytes':67108864, 'concurrency':1, 'cleanup':'kill-container-and-remove',
    'entrypoint':'/usr/local/bin/node', 'entry':'/opt/nico/trusted-typescript-entry.cjs',
}


def disabled_profile():
    return deepcopy(_PROFILE)


def validate_profile(profile):
    # Strict equality includes types; booleans cannot masquerade as integer limits.
    if (not isinstance(profile, dict) or set(profile) != set(_PROFILE)
            or any(type(profile[k]) is not type(v) or profile[k] != v for k,v in _PROFILE.items())):
        raise ValueError('typescript_profile_changed_or_enabled')
    return deepcopy(profile)


def planned_container_arguments(profile, image):
    """For review only: return arguments, never call Docker or authorize execution."""
    p = validate_profile(profile)
    if not isinstance(image, str) or not re.fullmatch(r'ghcr\.io/bonemantgrm/nico/assessment-typescript@sha256:[a-f0-9]{64}',image):
        raise ValueError('typescript_image_identity_required')
    return ['docker','create','--pull=never','--interactive','--network=none','--read-only',
        '--user='+p['user'],'--cap-drop=ALL','--security-opt=no-new-privileges',
        '--cpus='+p['cpus'],'--memory=512m','--memory-swap=512m','--pids-limit=32',
        '--ulimit=cpu=30:30','--ulimit=nofile=128:128', '--ulimit=core=0:0',
        '--tmpfs=/work:rw,nosuid,nodev,noexec,size=67108864,mode=0700,uid=10001,gid=10001',
        '--workdir=/work','--log-driver=none','--entrypoint='+p['entrypoint'],
        image,'--max-old-space-size=256',p['entry']]
