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

# ctest's console log can exceed the controller stream budget while the process
# is still producing the JUnit file. Keep that log on the work tmpfs and let
# the test process finish; retain a bounded copy afterwards.
CTEST_EXEC_PROGRAM = r'''
import os, sys
log_path, argv = sys.argv[1], sys.argv[2:]
if (not argv or os.path.basename(argv[0]) != 'ctest' or not log_path.startswith('/work/build/')
        or os.path.basename(log_path) != 'nico-baseline-ctest.log'):
    raise SystemExit(2)
fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
os.dup2(fd, 1)
os.dup2(fd, 2)
if fd > 2: os.close(fd)
os.execvp(argv[0], argv)
'''

UNIT_TEST_DATA_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, sys
limit = int(sys.argv[1])
raw = sys.stdin.buffer.read(limit + 1)
if len(raw) > limit: raise SystemExit('input_limit')
files = json.loads(raw)
if os.getuid() != 0: raise SystemExit('provisioning_identity')
root = pathlib.Path('/work/unit_test_data')
root.mkdir(mode=0o755)
result = {}
for name, value in files.items():
    if '/' in name or name in ('', '.', '..') or len(name) > 80:
        raise SystemExit('input_path')
    data = base64.b64decode(value['base64'], validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if digest != value['sha256']: raise SystemExit('input_digest')
    output = root / name
    with output.open('xb') as handle: handle.write(data)
    output.chmod(0o444)
    result[name] = digest
print(json.dumps(result, sort_keys=True))
'''


def probe_project_configuration(source, targets, image, *, project_options,
                                retain=lambda result: None, command=None, baseline_execution=None,
                                unit_test_data=None, capture_generated_context=False,
                                retain_artifact=None, project_compiler_evidence=False, project_static_analysis=False):
    """Capture a real CMake plan before freezing a large execution population.

    This is preparation evidence, NOT a worker completion receipt. It cannot
    pass validate_receipt or activate a production profile. All assessed CMake
    commands use the existing disposable boundary. The optional frozen
    baseline contract adds build/test stages without claiming full assessment.
    Returned records survive later failure through the caller's atomic sink.
    """
    import re
    from pathlib import PurePosixPath
    from nico.assessment_cpp_full_project import CMAKE_VERSION, MAX_SOURCE_BYTES, _json, _database
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
    if (type(capture_generated_context) is not bool
            or (capture_generated_context and (baseline_execution is None or not callable(retain_artifact)))):
        raise ValueError('worker_configuration_probe_capture_contract_invalid')
    if type(project_compiler_evidence) is not bool or (project_compiler_evidence and not capture_generated_context):
        raise ValueError('worker_configuration_probe_compiler_contract_invalid')
    if type(project_static_analysis) is not bool or (project_static_analysis and not project_compiler_evidence):
        raise ValueError('worker_configuration_probe_static_contract_invalid')
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
                       for k, maximum in (('build_seconds', 1200), ('test_seconds', 900),
                                          ('test_case_seconds', 300), ('parallel', 4)))):
            raise ValueError('worker_configuration_probe_execution_contract_invalid')
    staged_data = None
    if unit_test_data is not None:
        if (baseline_execution is None or not isinstance(unit_test_data, dict)
                or not 1 <= len(unit_test_data) <= 4
                or any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name) is None
                    or not isinstance(blob, (bytes, bytearray)) or not 1 <= len(blob) <= 20_000_000
                    for name, blob in unit_test_data.items())):
            raise ValueError('worker_configuration_probe_unit_test_data_invalid')
        staged_data = {name: bytes(blob) for name, blob in sorted(unit_test_data.items())}
    profile = BASELINE_QUALIFICATION_PROFILE if baseline_execution is not None else PROFILE
    resources = resources_for(profile)
    execution_seconds = 1800 if baseline_execution is not None else 80
    command = command or _command
    start = time.monotonic()
    deadline = start + execution_seconds
    name = 'nico-project-configure-' + uuid4().hex
    created = False
    result = {'schema': 'nico.cpp-project-configuration-probe.v3', 'status': 'UNPROVEN',
        'preparation_mode': 'baseline_execution' if baseline_execution is not None else 'configuration_only',
        'compilation_contexts': None,
        'image_config_digest': image, 'source_population_sha256': hashlib.sha256(canonical_bytes(targets)).hexdigest(),
        'project_options': dict(project_options), 'operations': [], 'boundary': None,
        'boundary_verified': False, 'memory_peak_bytes': None, 'cleanup_verified': False,
        'compilation_database': None, 'compilation_database_sha256': None,
        'configuration_cache': None, 'configuration_cache_sha256': None, 'effective_project_options': {},
        'configured_translation_units': [], 'configured_generated_units': [], 'configured_invocations': 0,
        'compiled': False, 'tests_executed': False, 'full_project_qualified': False,
        'error': None, 'wall_budget_seconds': 90, 'execution_budget_seconds': 80, 'duration_ms': 0}

    if capture_generated_context:
        result.update(schema='nico.cpp-project-configuration-probe.v4',
            generated_context=None, generated_context_verified=False)

    if project_compiler_evidence:
        result.update(schema='nico.cpp-project-configuration-probe.v5', project_compiler=None)
    if project_static_analysis:
        result.update(schema='nico.cpp-project-configuration-probe.v6', project_static=None,
            project_static_stage=None, aggregate_execution_budget_seconds=2400,
            aggregate_wall_budget_seconds=2420, aggregate_duration_ms=0)

    if baseline_execution is not None:
        result.update(baseline_execution=dict(baseline_execution), tests_discovered=[], tests_passed=False,
            scratch_capacity_verified=False, scratch_capacity_bytes=None,
            tests_result=None, native_test_discovery=None, unit_test_data=None,
            wall_budget_seconds=1810, execution_budget_seconds=execution_seconds)

    def save():
        result['duration_ms'] = int((time.monotonic() - start) * 1000)
        retain(result)

    def checkpoint():
        if time.monotonic() >= deadline:
            raise ValueError('worker_configuration_probe_deadline')

    def observe(key, argv, *, data=None, limit=65536, seconds=15, external=False):
        checkpoint()
        before = time.monotonic()
        observed = command(argv, checkpoint=checkpoint, timeout=min(seconds, deadline-before),
                           input_bytes=data, limit=limit, native_exit=True)
        raw = observed['output']
        entry = {'id': key, 'invocation': argv,
            'exit_code': observed['exit_code'], 'timed_out': observed['timed_out'],
            'output_truncated': observed['output_truncated'], 'duration_ms': int((time.monotonic()-before)*1000),
            'output': None if external else base64.b64encode(raw).decode('ascii'),
            'output_sha256': hashlib.sha256(raw).hexdigest()}
        if external:
            entry['output_artifact'] = None
        result['operations'].append(entry)
        save()  # Preserve the returned native outcome, even if artifact storage fails.
        if external:
            try:
                reference = retain_artifact(key, raw)
            except Exception as exc:
                raise ValueError('worker_configuration_probe_artifact_retention_failed') from exc
            expected = {'path': 'artifacts/' + key + '-' + entry['output_sha256'] + '.json',
                        'sha256': entry['output_sha256'], 'bytes': len(raw)}
            if reference != expected or type(reference.get('bytes')) is not int:
                raise ValueError('worker_configuration_probe_artifact_reference_invalid')
            entry['output_artifact'] = reference
            save()  # Artifact bytes and identity are retained before parsing or promotion.
        return observed

    def invoke(key, argv, *, data=None, limit=65536, seconds=15, allow_failure=False):
        observed = observe(key, argv, data=data, limit=limit, seconds=seconds)
        if ((observed['exit_code'] != 0 and not allow_failure) or observed['timed_out']
                or observed['output_truncated']):
            raise ValueError('worker_configuration_probe_operation_failed')
        return observed['output']

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
        try:
            contexts = _database(raw, None, '/work/build', nested=True, source_targets=targets)
        except ValueError as exc:
            raise ValueError('worker_configuration_probe_contexts_invalid') from exc
        result.update(compilation_database=artifact['data'], compilation_database_sha256=contexts['database_sha256'],
            configured_translation_units=contexts['original_units'], configured_generated_units=contexts['generated_units'],
            configured_invocations=contexts['context_count'], compilation_contexts=contexts)
        result['status'] = 'CONFIGURATION_CAPTURED'
        if baseline_execution is not None:
            if result['compilation_database_sha256'] != baseline_execution['compilation_database_sha256']:
                raise ValueError('worker_configuration_probe_frozen_database_mismatch')
            if staged_data is not None:
                payload = canonical_bytes({name: {
                    'base64': base64.b64encode(blob).decode('ascii'),
                    'sha256': hashlib.sha256(blob).hexdigest()} for name, blob in staged_data.items()})
                transferred = _json(invoke('unit-test-data', ['docker', 'exec', '--user=0:0', '--interactive',
                    name, 'python3', '-I', '-S', '-c', UNIT_TEST_DATA_PROGRAM, str(len(payload))],
                    data=payload, limit=65536, seconds=30))
                expected = {item: hashlib.sha256(blob).hexdigest() for item, blob in staged_data.items()}
                if transferred != expected:
                    raise ValueError('worker_configuration_probe_unit_test_data_invalid')
                result['unit_test_data'] = expected
                save()
                del payload
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
            # Generated CTest includes (secp256k1 discover_tests) only expand
            # after the test binaries exist. Freeze that runnable population
            # before testing. A leftover DISCOVERY_FAILURE is not a test.
            discovered = invoke('baseline-test-discovery', [*prefix, 'ctest', '--test-dir',
                '/work/build', '--show-only=json-v1'], limit=4*1024*1024, seconds=60)
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
            if any('DISCOVERY_FAILURE' in item for item in names):
                raise ValueError('worker_configuration_probe_tests_incomplete')
            result.update(status='UNPROVEN', tests_discovered=names,
                          native_test_discovery=base64.b64encode(discovered).decode('ascii'))
            save()
            # The command is fixed: execute every post-build CTest entry. No
            # regex exclusion, chosen passing subset or arbitrary command.
            # Stdout stays in the container so a verbose failure cannot kill
            # ctest before it writes JUnit.
            test_argv = ['docker', 'exec']
            if result['unit_test_data'] is not None:
                test_argv += ['-e', 'DIR_UNIT_TEST_DATA=/work/unit_test_data']
            test_argv += [name, 'python3', '-I', '-S', '-c', CTEST_EXEC_PROGRAM,
                '/work/build/nico-baseline-ctest.log', 'ctest', '--test-dir', '/work/build',
                '--parallel', str(baseline_execution['parallel']), '--timeout',
                str(baseline_execution['test_case_seconds']), '--output-on-failure',
                '--output-junit', '/work/build/nico-baseline-junit.xml']
            observed = observe('baseline-tests', test_argv, seconds=baseline_execution['test_seconds'],
                               limit=65536)
            result['tests_executed'] = True
            native_success = observed['exit_code'] == 0 and not observed['timed_out'] and not observed['output_truncated']
            save()

            def bounded_artifact(key, path, file_limit, stream_limit):
                artifact_observed = observe(key, [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
                    path, str(file_limit)], limit=stream_limit)
                if (artifact_observed['exit_code'] != 0 or artifact_observed['timed_out']
                        or artifact_observed['output_truncated']):
                    return None
                parsed = _json(artifact_observed['output'])
                if not isinstance(parsed, dict) or set(parsed) != {'data', 'truncated'}:
                    return None
                return parsed

            log = bounded_artifact('baseline-test-log', '/work/build/nico-baseline-ctest.log',
                                   1024*1024, 2*1024*1024)
            junit = bounded_artifact('baseline-junit', '/work/build/nico-baseline-junit.xml',
                                     2*1024*1024, 4*1024*1024)
            log_ok = bool(log and log['truncated'] is False)
            from nico.assessment_cpp_full_project import _junit
            executed, passed, skipped, junit_data = [], [], [], None
            if junit and junit['truncated'] is False:
                junit_data = junit['data']
                try:
                    executed, passed, skipped = _junit(base64.b64decode(junit_data, validate=True), names)
                except ValueError:
                    executed, passed, skipped = [], [], []
            result['tests_result'] = {'executed': executed, 'passed': passed, 'skipped': skipped,
                                      'junit': junit_data, 'log_truncated': not log_ok,
                                      'junit_truncated': junit_data is None}
            result['tests_passed'] = (native_success and log_ok and junit_data is not None
                                      and passed == names and not skipped)
            if not result['tests_passed']:
                raise ValueError('worker_configuration_probe_native_tests_failed')
            if capture_generated_context:
                from nico.assessment_cpp_project_snapshot import (PROJECT_SNAPSHOT_PROGRAM,
                    PROJECT_GENERATED_STREAM_LIMIT, project_snapshot_request, validate_project_snapshot)
                snapshot_observed = observe('project-generated-context',
                    ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name,
                     'python3', '-I', '-S', '-c', PROJECT_SNAPSHOT_PROGRAM],
                    data=canonical_bytes(project_snapshot_request(contexts)),
                    limit=PROJECT_GENERATED_STREAM_LIMIT, seconds=30, external=True)
                if (snapshot_observed['exit_code'] != 0 or snapshot_observed['timed_out']
                        or snapshot_observed['output_truncated']):
                    raise ValueError('worker_configuration_probe_snapshot_failed')
                try:
                    snapshot = validate_project_snapshot(_json(snapshot_observed['output']), contexts)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_snapshot_invalid') from exc
                result['generated_context'] = {
                    **{k: v for k, v in snapshot.items() if k != 'files'},
                    'files': {p: {'sha256': v['sha256'], 'bytes': v['bytes']}
                              for p, v in snapshot['files'].items()},
                    'artifact': result['operations'][-1]['output_artifact']}
                result['generated_context_verified'] = True
                save()
            if project_compiler_evidence:
                from nico.assessment_cpp_project_compiler import (PROGRAM, STREAM_LIMIT,
                    project_compiler_request, validate_project_compiler)
                try:
                    request = project_compiler_request(raw, targets, snapshot)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_compiler_plan_invalid') from exc
                compiler_observed = observe('project-compiler-evidence',
                    ['docker', 'exec', '--user='+ANALYSIS_USER, '--interactive', name,
                     'python3', '-I', '-S', '-c', PROGRAM],
                    data=canonical_bytes(request), limit=STREAM_LIMIT, seconds=550, external=True)
                if (compiler_observed['exit_code'] != 0 or compiler_observed['timed_out']
                        or compiler_observed['output_truncated']):
                    raise ValueError('worker_configuration_probe_compiler_failed')
                try:
                    proof = validate_project_compiler(compiler_observed['output'], request)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError('worker_configuration_probe_compiler_evidence_invalid') from exc
                result['project_compiler'] = {**proof, 'artifact': result['operations'][-1]['output_artifact']}
                save()
                if not proof['complete']:
                    raise ValueError('worker_configuration_probe_compiler_incomplete')
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
    if project_static_analysis and result['status'] == 'BASELINE_EXECUTED':
        # The build sandbox is already destroyed. Its original deadline and
        # duration remain unchanged; static analysis owns a separately bounded
        # noexec sandbox and a distinct receipt. No build code is replayed.
        from nico.assessment_cpp_project_static import run_project_static_stage
        def retain_static(value):
            result.update(project_static_stage=value, project_static=value.get('analysis'),
                          aggregate_duration_ms=int((time.monotonic()-start)*1000))
            if not value.get('complete'):
                result['status'] = 'UNPROVEN'
            retain(result)
        try:
            static = run_project_static_stage(source, targets, image,
                base64.b64decode(result['compilation_database'], validate=True),
                snapshot, compiler_observed['output'], retain=retain_static,
                retain_artifact=retain_artifact, command=command)
            result['status'] = 'BASELINE_EXECUTED' if static['complete'] else 'UNPROVEN'
            if not static['complete']:
                result['error'] = 'worker_configuration_probe_static_incomplete'
        except (Exception, KeyboardInterrupt):
            result.update(status='UNPROVEN', error='worker_configuration_probe_static_failed')
        result['aggregate_duration_ms'] = int((time.monotonic()-start)*1000)
        retain(result)
    return result
