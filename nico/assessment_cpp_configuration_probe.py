"""Isolated configure-first preparation for the existing full-project worker.

Captures a plan, not a completed assessment, and cannot activate production.
All execution uses the existing full-project sandbox primitives. An explicit
baseline contract uses a separate measured-at-runtime qualification envelope.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from nico.assessment_cpp_full_project_execution import (
    PROFILE, docker_resource_args, _command, _inputs, ANALYSIS_USER,
    ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM, READ_PROGRAM,
    boundary_valid,
)

SCRATCH_PROGRAM = "import json, os; s=os.statvfs('/work'); print(json.dumps({'capacity_bytes':s.f_blocks*s.f_frsize,'available_bytes':s.f_bavail*s.f_frsize}))"


def probe_project_configuration(source, targets, image, *, project_options,
                                retain=lambda result: None, command=None, baseline_execution=None):
    """Capture a real CMake plan before freezing a large execution population.

    This is preparation evidence, NOT a worker completion receipt. It cannot
    pass validate_receipt or activate a production profile. All assessed CMake
    commands use the existing disposable boundary. The optional frozen
    baseline contract adds build/test stages without claiming full assessment.
    Returned records survive later failure through the caller's atomic sink.
    """
    import re
    import shlex
    from pathlib import PurePosixPath
    from nico.assessment_cpp_full_project import CMAKE_VERSION, MAX_SOURCE_BYTES, _json
    from nico.assessment_cpp_configuration import COMPILER_VERSION
    from nico.assessment_worker_receipts import canonical_bytes
    if (not isinstance(image, str) or re.fullmatch(r'sha256:[0-9a-f]{64}', image) is None
            or not isinstance(targets, dict) or not 1 <= len(targets) <= 20000
            or 'CMakeLists.txt' not in targets
            or any(not isinstance(path, str) or not path or len(path) > 1000
                or PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path
                or any(part in {'', '.', '..', '.git'} for part in path.split('/'))
                or ':' in path or '\\' in path or any(ord(c) < 32 for c in path)
                or not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None
                for path, digest in targets.items())):
        raise ValueError('worker_configuration_probe_identity_invalid')
    if (not isinstance(project_options, dict) or len(project_options) > 64
            or any(not isinstance(key, str) or re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', key) is None
                or key.startswith('CMAKE_') or not isinstance(value, str)
                or re.fullmatch(r'[A-Za-z0-9_./+-]{1,120}', value) is None
                for key, value in project_options.items())):
        raise ValueError('worker_configuration_probe_options_invalid')
    from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE, resources_for
    if baseline_execution is not None:
        fields = {'schema', 'profile', 'compilation_database_sha256', 'build_seconds',
                  'test_seconds', 'test_case_seconds', 'parallel'}
        if (not isinstance(baseline_execution, dict) or set(baseline_execution) != fields
                or baseline_execution['schema'] != 'nico.cpp-baseline-execution.v1'
                or baseline_execution['profile'] != BASELINE_QUALIFICATION_PROFILE
                or not isinstance(baseline_execution['compilation_database_sha256'], str)
                or re.fullmatch(r'[a-f0-9]{64}', baseline_execution['compilation_database_sha256']) is None
                or any(type(baseline_execution[k]) is not int or not 1 <= baseline_execution[k] <= maximum
                       for k, maximum in (('build_seconds', 1200), ('test_seconds', 480),
                                          ('test_case_seconds', 120), ('parallel', 4)))):
            raise ValueError('worker_configuration_probe_execution_contract_invalid')
    profile = BASELINE_QUALIFICATION_PROFILE if baseline_execution is not None else PROFILE
    resources = resources_for(profile)
    execution_seconds = 1800 if baseline_execution is not None else 80
    command = command or _command
    start = time.monotonic()
    deadline = start + execution_seconds
    name = 'nico-project-configure-' + uuid4().hex
    created = False
    result = {'schema': 'nico.cpp-project-configuration-probe.v1', 'status': 'UNPROVEN',
        'image_config_digest': image, 'source_population_sha256': hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        'project_options': dict(project_options), 'operations': [], 'boundary': None,
        'boundary_verified': False, 'memory_peak_bytes': None, 'cleanup_verified': False,
        'compilation_database': None, 'compilation_database_sha256': None,
        'configuration_cache': None, 'configuration_cache_sha256': None, 'effective_project_options': {},
        'configured_translation_units': [], 'configured_generated_units': [], 'configured_invocations': 0,
        'compiled': False, 'tests_executed': False, 'full_project_qualified': False,
        'error': None, 'wall_budget_seconds': 90, 'execution_budget_seconds': 80, 'duration_ms': 0}

    if baseline_execution is not None:
        result.update(schema='nico.cpp-project-configuration-probe.v2',
            baseline_execution=dict(baseline_execution), tests_discovered=[], tests_passed=False,
            scratch_capacity_verified=False, scratch_capacity_bytes=None,
            tests_result=None, native_test_discovery=None,
            wall_budget_seconds=1810, execution_budget_seconds=execution_seconds)

    def save():
        result['duration_ms'] = int((time.monotonic() - start) * 1000)
        retain(result)

    def checkpoint():
        if time.monotonic() >= deadline:
            raise ValueError('worker_configuration_probe_deadline')

    def invoke(key, argv, *, data=None, limit=65536, seconds=15, allow_failure=False):
        checkpoint()
        before = time.monotonic()
        observed = command(argv, checkpoint=checkpoint, timeout=min(seconds, deadline-before),
                           input_bytes=data, limit=limit, native_exit=True)
        raw = observed['output']
        result['operations'].append({'id': key, 'invocation': argv,
            'exit_code': observed['exit_code'], 'timed_out': observed['timed_out'],
            'output_truncated': observed['output_truncated'], 'duration_ms': int((time.monotonic()-before)*1000),
            'output': base64.b64encode(raw).decode('ascii'), 'output_sha256': hashlib.sha256(raw).hexdigest()})
        save()  # Retain returned bytes before parsing, assertions, or next command.
        if ((observed['exit_code'] != 0 and not allow_failure) or observed['timed_out']
                or observed['output_truncated']):
            raise ValueError('worker_configuration_probe_operation_failed')
        return raw

    save()
    try:
        files = _inputs({'targets': targets, 'configuration': {'source_byte_limit': MAX_SOURCE_BYTES}},
                        Path(source), checkpoint)
        metadata = _json(invoke('image', ['docker', 'image', 'inspect', image]))
        if not isinstance(metadata, list) or len(metadata) != 1 or metadata[0].get('Id') != image:
            raise ValueError('worker_configuration_probe_image_mismatch')
        created = True  # Docker can succeed before its response is interrupted.
        invoke('create', ['docker', 'create', '--name', name, '--network=none', '--read-only',
            '--user=1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            *docker_resource_args(profile, executable=True), '--log-driver=none',
            '--env=HOME=/work', '--env=TMPDIR=/work', '--entrypoint=sleep', image, str(execution_seconds + 15)])
        invoke('start', ['docker', 'start', name])
        setup = _json(invoke('analyst-setup', ['docker', 'exec', '--user='+ANALYSIS_USER,
            name, 'python3', '-I', '-S', '-c', ANALYSIS_SETUP_PROGRAM]))
        if setup != {'uid':1001, 'gid':1001, 'private':True}:
            raise ValueError('worker_configuration_probe_boundary_invalid')
        prefix = ['docker', 'exec', name]
        before = _json(invoke('boundary-before', [*prefix, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        if not boundary_valid(before, source_required=False, profile=profile):
            raise ValueError('worker_configuration_probe_boundary_invalid')
        if baseline_execution is not None:
            scratch = _json(invoke('scratch-capacity', [*prefix, 'python3', '-I', '-S', '-c', SCRATCH_PROGRAM]))
            if (not isinstance(scratch, dict) or set(scratch) != {'capacity_bytes', 'available_bytes'}
                    or type(scratch['capacity_bytes']) is not int
                    or scratch['capacity_bytes'] != resources['tmpfs_bytes']
                    or type(scratch['available_bytes']) is not int
                    or not 0 <= scratch['available_bytes'] <= scratch['capacity_bytes']):
                raise ValueError('worker_configuration_probe_scratch_capacity_invalid')
            result.update(scratch_capacity_verified=True, scratch_capacity_bytes=scratch['capacity_bytes'])
            save()
        payload = canonical_bytes(files)
        transferred = _json(invoke('source-transfer', ['docker', 'exec', '--user=0:0', '--interactive',
            name, 'python3', '-I', '-S', '-c', INPUT_PROGRAM, str(len(payload))], data=payload,
            limit=4*1024*1024, seconds=20))
        if transferred != targets:
            raise ValueError('worker_configuration_probe_source_mismatch')
        # Avoid retaining a second full copy of the already committed source input.
        del files, payload
        result['boundary'] = _json(invoke('boundary-after', [*prefix, 'python3', '-I', '-S', '-c', BOUNDARY_PROGRAM]))
        result['boundary_verified'] = boundary_valid(result['boundary'], profile=profile)
        if not result['boundary_verified']:
            raise ValueError('worker_configuration_probe_boundary_invalid')
        cmake = invoke('cmake-version', [*prefix, 'cmake', '--version'])
        if cmake.splitlines()[0] != ('cmake version '+CMAKE_VERSION).encode():
            raise ValueError('worker_configuration_probe_tool_mismatch')
        for compiler in ('gcc', 'g++'):
            if invoke(compiler+'-version', [*prefix, compiler, '-dumpfullversion']).strip() != COMPILER_VERSION.encode():
                raise ValueError('worker_configuration_probe_tool_mismatch')
        options = ['-D'+key+'='+value for key, value in sorted(project_options.items())]
        invoke('configure', [*prefix, 'cmake', '-S', '/work/source', '-B', '/work/build',
            '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_COMPILER=/usr/local/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
            *options], seconds=50, limit=262144)
        cache = _json(invoke('configuration-cache', [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/CMakeCache.txt', str(1024*1024)], limit=2*1024*1024))
        if not isinstance(cache, dict) or set(cache) != {'data', 'truncated'} or cache['truncated'] is not False:
            raise ValueError('worker_configuration_probe_cache_truncated')
        cache_bytes = base64.b64decode(cache['data'], validate=True)
        if not 0 < len(cache_bytes) <= 1024*1024:
            raise ValueError('worker_configuration_probe_cache_invalid')
        result.update(configuration_cache=cache['data'],
                      configuration_cache_sha256=hashlib.sha256(cache_bytes).hexdigest())
        observed_options = {}
        for line in cache_bytes.decode('utf-8').splitlines():
            # A -D argument alone becomes UNINITIALIZED even when the project
            # never consumes it. Require an observed, typed project cache entry.
            if not line or line.startswith(('#', '//')):
                continue
            match = re.fullmatch(r'([^:]+):([A-Z_]+)=(.*)', line)
            if match and match[1] in project_options:
                key, kind, value = match.groups()
                if (key in observed_options or kind not in {'BOOL', 'STRING', 'PATH', 'FILEPATH'}
                        or value != project_options[key]):
                    raise ValueError('worker_configuration_probe_option_unverified')
                observed_options[key] = value
        if observed_options != project_options:
            raise ValueError('worker_configuration_probe_option_unverified')
        result['effective_project_options'] = observed_options
        save()
        artifact = _json(invoke('compilation-database', [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/compile_commands.json', str(4*1024*1024)], limit=6*1024*1024))
        if not isinstance(artifact, dict) or set(artifact) != {'data', 'truncated'} or artifact['truncated'] is not False:
            raise ValueError('worker_configuration_probe_database_truncated')
        raw = base64.b64decode(artifact['data'], validate=True)
        if not 0 < len(raw) <= 4*1024*1024:
            raise ValueError('worker_configuration_probe_database_invalid')
        rows = _json(raw)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
            raise ValueError('worker_configuration_probe_database_invalid')
        originals, generated = set(), set()
        for row in rows:
            checkpoint()
            if not isinstance(row, dict) or not isinstance(row.get('file'), str):
                raise ValueError('worker_configuration_probe_database_invalid')
            path, directory = row['file'], row.get('directory')
            if (not isinstance(directory, str) or not (directory == '/work/build' or directory.startswith('/work/build/'))
                    or any(part in {'', '.', '..'} for part in directory.split('/')[1:])
                    or any(part in {'', '.', '..'} for part in path.split('/')[1:])):
                raise ValueError('worker_configuration_probe_database_path_invalid')
            if path.startswith('/work/source/') and path.removeprefix('/work/source/') in targets:
                originals.add(path.removeprefix('/work/source/'))
            elif path.startswith('/work/build/'):
                generated.add(path.removeprefix('/work/build/'))
            else:
                raise ValueError('worker_configuration_probe_database_path_invalid')
            arguments = row.get('arguments')
            if arguments is None and isinstance(row.get('command'), str):
                arguments = shlex.split(row['command'])
            if (not isinstance(arguments, list) or not 1 <= len(arguments) <= 4096
                    or any(not isinstance(a, str) or not a or len(a) > 16384 for a in arguments)):
                raise ValueError('worker_configuration_probe_database_invalid')
        result.update(compilation_database=artifact['data'], compilation_database_sha256=hashlib.sha256(raw).hexdigest(),
            configured_translation_units=sorted(originals), configured_generated_units=sorted(generated),
            configured_invocations=len(rows))
        result['status'] = 'CONFIGURATION_CAPTURED'
        if baseline_execution is not None:
            if result['compilation_database_sha256'] != baseline_execution['compilation_database_sha256']:
                raise ValueError('worker_configuration_probe_frozen_database_mismatch')
            # Freeze the entire CTest name population before any project build.
            # Discovery output is retained as target-produced planning evidence.
            discovered = invoke('baseline-test-discovery', [*prefix, 'ctest', '--test-dir',
                '/work/build', '--show-only=json-v1'], limit=2*1024*1024, seconds=30)
            names = _json(discovered)
            rows = names.get('tests') if isinstance(names, dict) else None
            if (not isinstance(rows, list) or not 1 <= len(rows) <= 10000
                    or any(not isinstance(row, dict) or not isinstance(row.get('name'), str)
                        or re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:/+-]{0,249}', row['name']) is None
                        for row in rows)):
                raise ValueError('worker_configuration_probe_tests_invalid')
            names = sorted(row['name'] for row in rows)
            if len(set(names)) != len(names):
                raise ValueError('worker_configuration_probe_tests_duplicate')
            result.update(status='UNPROVEN', tests_discovered=names,
                          native_test_discovery=base64.b64encode(discovered).decode('ascii'))
            save()
            invoke('baseline-build', [*prefix, 'cmake', '--build', '/work/build', '--parallel',
                str(baseline_execution['parallel'])], seconds=baseline_execution['build_seconds'],
                limit=1024*1024)
            result['compiled'] = True
            save()
            # CMake may regenerate as part of the build. It must not change the
            # frozen command population, including generated and repeated units.
            after = _json(invoke('post-build-database', [*prefix, 'python3', '-I', '-S', '-c',
                READ_PROGRAM, '/work/build/compile_commands.json', str(4*1024*1024)], limit=6*1024*1024))
            if (not isinstance(after, dict) or set(after) != {'data','truncated'} or after['truncated']
                    or hashlib.sha256(base64.b64decode(after['data'], validate=True)).hexdigest()
                       != result['compilation_database_sha256']):
                raise ValueError('worker_configuration_probe_frozen_database_mismatch')
            # The command is fixed: execute every predeclared CTest entry. No
            # post-failure exclusion, chosen passing subset or arbitrary command.
            invoke('baseline-tests', [*prefix, 'ctest', '--test-dir', '/work/build',
                '--parallel', str(baseline_execution['parallel']), '--timeout',
                str(baseline_execution['test_case_seconds']), '--output-on-failure',
                '--output-junit', '/work/build/nico-baseline-junit.xml'],
                seconds=baseline_execution['test_seconds'], limit=1024*1024, allow_failure=True)
            result['tests_executed'] = True
            native_success = result['operations'][-1]['exit_code'] == 0
            save()
            junit = _json(invoke('baseline-junit', [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
                '/work/build/nico-baseline-junit.xml', str(2*1024*1024)], limit=3*1024*1024))
            if (not isinstance(junit, dict) or set(junit) != {'data','truncated'} or junit['truncated']):
                raise ValueError('worker_configuration_probe_junit_invalid')
            from nico.assessment_cpp_full_project import _junit
            executed, passed, skipped = _junit(base64.b64decode(junit['data'], validate=True), names)
            result['tests_result'] = {'executed':executed, 'passed':passed, 'skipped':skipped,
                                      'junit':junit['data']}
            result['tests_passed'] = native_success and passed == names and not skipped
            if not result['tests_passed']:
                raise ValueError('worker_configuration_probe_native_tests_failed')
            result['status'] = 'BASELINE_EXECUTED'

    except (Exception, KeyboardInterrupt) as exc:
        # No arbitrary exception/tool text enters an unsanitized controller error.
        allowed = str(exc) if isinstance(exc, ValueError) else ''
        result['error'] = (allowed if re.fullmatch(r'worker_configuration_probe_[a-z_]+', allowed)
                           else 'worker_configuration_probe_interrupted' if isinstance(exc, KeyboardInterrupt)
                           else 'worker_configuration_probe_failed')
    finally:
        if created:
            try:
                raw = command(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'],
                    checkpoint=lambda: None, timeout=2, limit=1024, native_exit=True)
                if raw['exit_code'] == 0 and not raw['timed_out'] and not raw['output_truncated']:
                    peak = int(raw['output'].strip())
                    if 0 <= peak <= resources['memory_bytes']: result['memory_peak_bytes'] = peak
            except (Exception, KeyboardInterrupt):
                pass  # Unavailable measurement remains unknown, not zero.
            try:
                removed = command(['docker', 'rm', '--force', name], checkpoint=lambda: None,
                                  timeout=5, limit=4096, native_exit=True)
                result['cleanup_verified'] = (removed['exit_code'] == 0 and not removed['timed_out']
                                             and not removed['output_truncated'])
            except (Exception, KeyboardInterrupt):
                pass
        if not result['cleanup_verified'] or result['error']:
            result['status'] = 'UNPROVEN'
        save()
    return result
